"""All inputs in this suite are mocks, never live-provider schema evidence."""
import asyncio
from hashlib import sha256
import json
import runpy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from src.observe import ObservationConfig, capture_migrations, migration_from_event, research_verdict
from src.stream_evidence import MAX_COUNTER_KEYS, MAX_SAMPLE_BYTES, MAX_SAMPLES, StreamEvidence

ROOT = Path(__file__).resolve().parents[1]
MOCKS = json.loads((ROOT / 'fixtures/stream_diagnostic_mocks.json').read_text())
LEGACY = json.loads((ROOT / 'fixtures/provider_mocks.json').read_text())['migration']
NOW = '2026-11-02T18:00:00+00:00'


class FakeSocket:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.recv_count = 0

    async def recv(self):
        self.recv_count += 1
        item = next(self.frames)
        if isinstance(item, Exception):
            raise item
        return item


class FakeConnection:
    def __init__(self, socket, error=None):
        self.socket = socket
        self.error = error
        self.closed = False

    async def __aenter__(self):
        if self.error:
            raise self.error
        return self.socket

    async def __aexit__(self, *args):
        self.closed = True


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    async def capture(self, frames, **kwargs):
        socket = FakeSocket(frames)
        connection = FakeConnection(socket)
        cfg = ObservationConfig(**kwargs)
        with tempfile.TemporaryDirectory() as temp:
            with patch('websockets.connect', return_value=connection) as connect:
                migrations, status = await capture_migrations(cfg, Path(temp))
            evidence = json.loads(Path(status['evidence']['file']).read_text())
            self.assertEqual(status['evidence']['sha256'],
                             sha256(Path(status['evidence']['file']).read_bytes()).hexdigest())
        connect.assert_called_once()
        self.assertTrue(connection.closed)
        return migrations, status, evidence, socket

    async def test_reproduce_15000_nonmatching_frames_without_claiming_cause(self):
        # Synthetic reproduction of the count, NOT reconstruction of Colab traffic.
        migrations, status, evidence, socket = await self.capture(
            ['{"action":"buy"}'] * 15001)
        self.assertEqual(status['events_seen'], 15000)
        self.assertEqual(socket.recv_count, 15000)
        self.assertEqual(status['reason'], 'event_limit')
        self.assertEqual(migrations, [])
        self.assertEqual(evidence['event_type_probes'], {'action=buy': 15000})
        self.assertEqual(evidence['parser_outcomes'], {'not_legacy_migrate_action': 15000})
        self.assertEqual(len(evidence['samples']), 2)

    async def test_malformed_missing_nested_and_unrelated_messages(self):
        frames = MOCKS['frames']
        migrations, status, evidence, _ = await self.capture(frames, max_events=len(frames))
        self.assertEqual(migrations, [])
        self.assertEqual(evidence['parser_outcomes'], {
            'invalid_json': 1, 'non_object': 2, 'not_legacy_migrate_action': 3, 'invalid_mint': 2})
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence))
        self.assertNotIn('secret text', json.dumps(evidence))
        self.assertEqual(status['independent_migration_proof'], 'UNKNOWN')

    async def test_duplicate_mint_and_sample_goal(self):
        other = {**LEGACY, 'mint': 'A' * 32}
        migrations, status, evidence, socket = await self.capture(
            [json.dumps(x) for x in (LEGACY, LEGACY, other, other)], max_migrations=2)
        self.assertEqual(status['reason'], 'sample_goal')
        self.assertEqual(socket.recv_count, 3)
        self.assertEqual(len(migrations), 2)
        self.assertEqual(evidence['parser_outcomes']['duplicate_mint'], 1)
        self.assertTrue(all(x[0]['schema_status'] == 'UNVALIDATED' for x in migrations))

    async def test_pool_or_token_creation_never_promoted(self):
        frames = [json.dumps({**LEGACY, 'action': action}) for action in
                  ('create', 'pool_create', 'sell', 'heartbeat')]
        migrations, _, _, _ = await self.capture(frames, max_events=4)
        self.assertEqual(migrations, [])

    async def test_disconnect_keeps_partial_evidence_without_reconnecting(self):
        from websockets.exceptions import ConnectionClosedError
        _, status, evidence, _ = await self.capture(
            ['{"action":"buy"}', ConnectionClosedError(None, None)])
        self.assertEqual(status['reason'], 'stream_error')
        self.assertEqual(status['error']['category'], 'connection_closed')
        self.assertEqual(evidence['events_seen'], 1)

    async def test_separate_connections_have_no_leaked_dedup_state(self):
        for _ in range(2):
            migrations, status, _, _ = await self.capture([json.dumps(LEGACY)], max_migrations=1)
            self.assertEqual(len(migrations), 1)
            self.assertEqual(status['reason'], 'sample_goal')

    async def test_rate_limit_is_reported_without_retry_or_sensitive_text(self):
        class Rejected(Exception):
            status_code = 429
        connection = FakeConnection(None, Rejected('https://provider/?key=SECRET_SENTINEL'))
        with tempfile.TemporaryDirectory() as temp, patch('websockets.connect', return_value=connection) as connect:
            _, status = await capture_migrations(ObservationConfig(), Path(temp))
            evidence = json.loads(Path(status['evidence']['file']).read_text())
        connect.assert_called_once()
        self.assertEqual(status['error']['http_status'], 429)
        self.assertEqual(status['events_seen'], 0)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence))

    async def test_idle_connected_stream_obeys_duration(self):
        socket = FakeSocket([])
        async def wait_forever():
            await asyncio.Future()
        socket.recv = wait_forever
        with tempfile.TemporaryDirectory() as temp, patch('websockets.connect', return_value=FakeConnection(socket)):
            _, status = await asyncio.wait_for(
                capture_migrations(ObservationConfig(duration_s=1), Path(temp)), timeout=2)
        self.assertTrue(status['connected'])
        self.assertEqual(status['reason'], 'time_limit')
        self.assertEqual(status['events_seen'], 0)

    async def test_connect_timeout_is_not_a_successful_empty_observation(self):
        connection = FakeConnection(None, TimeoutError())
        with tempfile.TemporaryDirectory() as temp, patch('websockets.connect', return_value=connection):
            _, status = await capture_migrations(ObservationConfig(), Path(temp))
        self.assertFalse(status['connected'])
        self.assertEqual(status['error']['category'], 'connection_timeout')

    async def test_bad_config_fails_before_network_access(self):
        for kwargs in ({'max_events': 0}, {'max_events': 15001}, {'duration_s': 181},
                       {'duration_s': -1}, {'max_migrations': 0}, {'max_migrations': True}):
            with tempfile.TemporaryDirectory() as temp, patch('websockets.connect') as connect:
                with self.assertRaises(ValueError):
                    await capture_migrations(ObservationConfig(**kwargs), Path(temp))
                connect.assert_not_called()

    async def test_capture_only_never_evaluates_candidates(self):
        from run_live import run
        status = {'reason': 'sample_goal', 'migrations': 1}
        with tempfile.TemporaryDirectory() as temp, \
             patch('run_live.capture_migrations', new=AsyncMock(return_value=([(LEGACY, LEGACY)], status))), \
             patch('run_live.evaluate_mint') as evaluate, \
             patch('requests.Session.get') as get, patch('requests.Session.post') as post:
            await run(capture_only=True, output=temp)
            evaluate.assert_not_called()
            get.assert_not_called()
            post.assert_not_called()
            summary = json.loads((Path(temp) / 'run_summary.json').read_text())
            self.assertEqual(summary['results'], [])


class EvidenceTests(unittest.TestCase):
    def test_hashes_sanitization_and_distinct_timestamps(self):
        data = {**LEGACY, 'timestamp': 1793642400, 'time': NOW,
                'apiKey': 'SECRET_SENTINEL', 'nested': {'authorization': 'SECRET_SENTINEL'}}
        message = json.dumps(data)
        evidence = StreamEvidence('wss://stream.pumpapi.io/', NOW)
        evidence.observe(message, data, 'legacy_parser_match_unvalidated', NOW)
        sample = evidence.samples[0]
        self.assertEqual(sample['wire_sha256'], sha256(message.encode()).hexdigest())
        self.assertEqual(sample['observed_at'], NOW)
        self.assertEqual(sample['sanitized_message']['timestamp'], data['timestamp'])
        self.assertEqual(sample['sanitized_message']['time'], NOW)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(sample))
        self.assertEqual(sample['sanitized_message']['name']['redacted'], True)

    def test_cardinality_sample_and_byte_limits(self):
        evidence = StreamEvidence('mock', NOW)
        for i in range(1000):
            data = {f'field{i}': 'SECRET_SENTINEL', 'action': f'type{i}'}
            evidence.observe(json.dumps(data), data, 'not_legacy_migrate_action', NOW)
        self.assertLessEqual(len(evidence.samples), MAX_SAMPLES)
        self.assertLessEqual(evidence.sample_bytes, MAX_SAMPLE_BYTES)
        self.assertLessEqual(len(evidence.shapes), MAX_COUNTER_KEYS)
        self.assertLessEqual(len(evidence.event_types), MAX_COUNTER_KEYS)
        self.assertEqual(sum(evidence.shapes.values()), 1000)
        self.assertEqual(sum(evidence.event_types.values()), 1000)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence.samples))

    def test_hostile_labels_and_binary_invalid_json_are_not_logged(self):
        evidence = StreamEvidence('mock', NOW)
        data = {'action': 'https://secret.example/?key=SECRET_SENTINEL'}
        evidence.observe(json.dumps(data), data, 'not_legacy_migrate_action', NOW)
        evidence.observe(b'\xffSECRET_SENTINEL', None, 'invalid_json', NOW)
        self.assertTrue(next(iter(evidence.event_types)).startswith('action=sha256:'))
        self.assertEqual(evidence.samples[-1]['frame_kind'], 'binary')
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence.samples))

    def test_repeated_runs_use_distinct_files(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence = StreamEvidence('mock', NOW)
            first = evidence.write(Path(temp), NOW, {})
            second = evidence.write(Path(temp), NOW, {})
            self.assertNotEqual(first['file'], second['file'])
            self.assertTrue(Path(first['file']).exists())

    def test_unvalidated_contract_is_explicit(self):
        migration = migration_from_event(LEGACY)
        self.assertEqual(migration['independent_migration_proof'], 'UNKNOWN')
        self.assertEqual(migration['schema_status'], 'UNVALIDATED')

    def test_arbitrary_secret_in_type_field_is_hashed(self):
        evidence = StreamEvidence('mock', NOW)
        data = {'action': 'SECRET_SENTINEL'}
        evidence.observe(json.dumps(data), data, 'not_legacy_migrate_action', NOW)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence.samples))
        self.assertNotIn('SECRET_SENTINEL', json.dumps(evidence.event_types))

    def test_even_passing_layers_cannot_clear_unverified_candidates(self):
        self.assertEqual(research_verdict([{'status': 'PASS'}] * 8), 'UNVERIFIED_DO_NOT_TRADE')

    def test_cli_returns_nonzero_for_stream_error(self):
        with tempfile.TemporaryDirectory() as temp, \
             patch('sys.argv', ['run_live.py', '--capture-only', '--output', temp]), \
             patch('src.observe.capture_migrations', new=AsyncMock(return_value=([], {'reason': 'stream_error'}))), \
             patch('builtins.print'):
            with self.assertRaises(SystemExit) as result:
                runpy.run_path(str(ROOT / 'run_live.py'), run_name='__main__')
            self.assertEqual(result.exception.code, 2)

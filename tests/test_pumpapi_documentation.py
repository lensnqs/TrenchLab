"""ORBIT-reported documentation structure, with synthetic identifier substitutions.

Neither literal documentation examples nor live/on-chain evidence. Mutations in
negative tests are test inputs, never assertions about actual provider messages.
"""
import json
from datetime import datetime
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.observe import migration_from_event, research_verdict


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'fixtures/pumpapi_documentation_derived.json').read_text())
CLAIMS = FIXTURE['migration_claims']


class DocumentationContractTests(unittest.TestCase):
    def test_fixture_separates_reported_structure_from_synthetic_values(self):
        self.assertEqual(FIXTURE['data_kind'], 'DOCUMENTATION_DERIVED_SCHEMA_REPORTED_BY_ORBIT')
        self.assertEqual(FIXTURE['provenance']['documentation_url'], 'https://pumpapi.io/stream')
        self.assertFalse(FIXTURE['provenance']['verbatim_documentation_example'])
        self.assertFalse(FIXTURE['provenance']['live_capture'])
        self.assertEqual(FIXTURE['provenance']['independent_onchain_verification'], 'UNKNOWN')
        self.assertIn('SYNTHETIC', FIXTURE['provenance']['identifier_values'])

    def test_minimal_documentation_derived_claim_preserves_mint_pool_signature(self):
        for payload in CLAIMS:
            with self.subTest(mint=payload['mint']):
                self.assertEqual(set(payload), {'action', 'mint', 'poolId', 'signature'})
                record = migration_from_event(payload)
                self.assertEqual(record['mint'], payload['mint'])
                self.assertEqual(record['pool'], payload['poolId'])
                self.assertEqual(record['signature'], payload['signature'])
                self.assertIsNone(record['name'])
                self.assertIsNone(record['symbol'])
                self.assertEqual(record['source'], 'pumpapi_stream')
                self.assertEqual(record['independent_migration_proof'], 'UNKNOWN')
                # Runtime remains conservative; Stage A does not relabel it live-validated.
                self.assertEqual(record['schema_status'], 'UNVALIDATED')
                self.assertEqual(research_verdict([{'status': 'PASS'}] * 8),
                                 'UNVERIFIED_DO_NOT_TRADE')

    def test_missing_or_invalid_mint_cannot_become_a_claim(self):
        missing = {k: v for k, v in CLAIMS[0].items() if k != 'mint'}
        self.assertIsNone(migration_from_event(missing))
        for value in (None, '', 'invalid!', 123, True, {}, [], '0' * 32):
            with self.subTest(mint=value):
                self.assertIsNone(migration_from_event({**CLAIMS[0], 'mint': value}))

    def test_missing_or_different_action_is_not_migration(self):
        missing = {k: v for k, v in CLAIMS[0].items() if k != 'action'}
        self.assertIsNone(migration_from_event(missing))
        for value in (None, 'create', 'pool_create', 'buy', 'sell', 'MIGRATE'):
            with self.subTest(action=value):
                self.assertIsNone(migration_from_event({**CLAIMS[0], 'action': value}))

    def test_missing_or_malformed_pool_and_signature_do_not_supply_proof(self):
        # Existing parser allows partial claims. These are synthetic omissions,
        # not a statement that the documentation makes either field optional.
        for values in ({}, {'poolId': 'invalid!', 'signature': 123}):
            payload = {k: v for k, v in CLAIMS[0].items() if k not in ('poolId', 'signature')}
            record = migration_from_event({**payload, **values})
            self.assertIsNone(record['pool'])
            self.assertIsNone(record['signature'])
            self.assertEqual(record['independent_migration_proof'], 'UNKNOWN')
        # A string signature is retained, not decoded, fetched or authenticated.
        record = migration_from_event({**CLAIMS[0], 'signature': 'synthetic-invalid-signature'})
        self.assertEqual(record['signature'], 'synthetic-invalid-signature')
        self.assertEqual(record['independent_migration_proof'], 'UNKNOWN')

    def test_no_guessed_nested_or_alternate_discriminator_contract(self):
        for payload in ({'data': CLAIMS[0]}, [CLAIMS[0]],
                        {**CLAIMS[0], 'action': None, 'type': 'migrate'}):
            with self.subTest(payload=payload):
                self.assertIsNone(migration_from_event(payload))

    def test_missing_provider_timestamp_is_not_fabricated_from_observation(self):
        with patch('src.observe.utcnow', return_value='2026-11-02T18:00:00+00:00'):
            record = migration_from_event(CLAIMS[0])
        self.assertIsNotNone(datetime.fromisoformat(record['observed_at']).tzinfo)
        self.assertNotIn('timestamp', record)
        self.assertNotIn('provider_timestamp', record)
        self.assertNotIn('timestamp', CLAIMS[0])


class DocumentationReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_events_replay_sends_no_subscription_and_keeps_claims_unverified(self):
        from run_live import run
        ws = AsyncMock()
        ws.recv.side_effect = [json.dumps(p) for p in (CLAIMS[0], CLAIMS[1], CLAIMS[0])]
        connection = MagicMock()
        connection.__aenter__ = AsyncMock(return_value=ws)
        connection.__aexit__ = AsyncMock(return_value=False)
        with tempfile.TemporaryDirectory() as temp, \
             patch('websockets.connect', return_value=connection) as connect, \
             patch('requests.Session.get') as get, patch('requests.Session.post') as post, \
             patch('run_live.evaluate_mint') as evaluate, patch('builtins.print'):
            status = await run(duration=45, events=3, limit=3, capture_only=True, output=temp)
            evidence = json.loads(Path(status['evidence']['file']).read_text())
            summary = json.loads((Path(temp) / 'run_summary.json').read_text())
        connect.assert_called_once()
        self.assertEqual(connect.call_args.args[0], 'wss://stream.pumpapi.io/')
        ws.send.assert_not_called()
        get.assert_not_called()
        post.assert_not_called()
        evaluate.assert_not_called()
        self.assertEqual(status['reason'], 'event_limit')
        self.assertEqual(status['events_seen'], 3)
        self.assertEqual(status['legacy_parser_matches'], 2)
        self.assertEqual(status['parser_outcomes']['duplicate_mint'], 1)
        self.assertEqual(status['independent_migration_proof'], 'UNKNOWN')
        self.assertEqual(evidence['event_type_probes'], {'action=migrate': 3})
        self.assertEqual(evidence['subscription']['messages_sent'], 0)
        self.assertEqual(evidence['independent_migration_proof'], 'UNKNOWN')
        self.assertEqual(summary['results'], [])
        self.assertEqual(evidence['samples'][0]['sanitized_message'], CLAIMS[0])

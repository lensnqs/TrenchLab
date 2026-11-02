"""ORBIT-supplied published excerpt; no live stream or on-chain verification.

Any createPool/other-origin variant below is a synthetic negative test mutation,
not another purported provider example.
"""
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from src.observe import ObservationConfig, capture_migrations, migration_from_event, research_verdict
from src.stream_evidence import StreamEvidence


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / 'fixtures/pumpapi_docs_example.json').read_text())
EXAMPLE = FIXTURE['migration']
OBSERVED_AT = '2026-11-02T20:00:00+00:00'  # Offline replay observation time only.


class PublishedExcerptTests(unittest.TestCase):
    def test_excerpt_is_attributed_documentation_and_never_live_evidence(self):
        self.assertEqual(FIXTURE['data_kind'], 'DOCS_EXAMPLE_NOT_LIVE_EVIDENCE')
        self.assertEqual(FIXTURE['evidence_classification'],
                         'PROVIDER_DOCUMENTATION_EXAMPLE_NOT_LIVE_EVIDENCE')
        provenance = FIXTURE['provenance']
        self.assertEqual(provenance['documentation_url'], 'https://pumpapi.io/stream')
        self.assertTrue(provenance['excerpt_abbreviated'])
        self.assertTrue(provenance['included_field_values_preserved'])
        self.assertFalse(provenance['codex_direct_page_retrieval'])
        self.assertFalse(provenance['live_capture'])
        self.assertEqual(provenance['independent_onchain_verification'], 'UNKNOWN')
        self.assertEqual(EXAMPLE['pool'], 'pump-amm')
        self.assertEqual(EXAMPLE['poolCreatedBy'], 'pump')
        self.assertEqual(EXAMPLE['block'], 462541749)
        self.assertEqual(EXAMPLE['timestamp'], 1793204432648)

    def test_documented_pumpfun_claim_maps_pool_id_without_certification(self):
        record = migration_from_event(EXAMPLE)
        self.assertEqual(record['mint'], EXAMPLE['mint'])
        self.assertEqual(record['pool'], EXAMPLE['poolId'])
        # The parser's normalized pool is the address, not the provider's AMM label.
        self.assertNotEqual(record['pool'], EXAMPLE['pool'])
        self.assertEqual(record['signature'], EXAMPLE['signature'])
        self.assertEqual(record['source'], 'pumpapi_stream')
        self.assertEqual(record['schema_status'], 'UNVALIDATED')
        self.assertEqual(record['independent_migration_proof'], 'UNKNOWN')
        # A published burnedLiquidity claim cannot clear a candidate or its LP.
        self.assertEqual(EXAMPLE['burnedLiquidity'], '100%')
        self.assertEqual(research_verdict([{'status': 'PASS'}] * 8), 'UNVERIFIED_DO_NOT_TRADE')

    def test_create_pool_is_not_migration_despite_other_matching_fields(self):
        self.assertIsNone(migration_from_event({**EXAMPLE, 'action': 'createPool'}))

    def test_other_origin_migrate_remains_generic_provider_claim(self):
        # Synthetic variant: action=migrate alone does not imply Pump.fun origin.
        other = {**EXAMPLE, 'pool': 'synthetic-other-amm',
                 'poolCreatedBy': 'synthetic-other-launchpad'}
        record = migration_from_event(other)
        self.assertIsNotNone(record)
        self.assertEqual(record['source'], 'pumpapi_stream')
        self.assertNotIn('poolCreatedBy', record)
        self.assertNotIn('launchpad', record)
        self.assertEqual(record['independent_migration_proof'], 'UNKNOWN')

    def test_original_provider_timestamp_survives_sanitization_separately(self):
        frame = json.dumps(EXAMPLE)
        evidence = StreamEvidence('wss://stream.pumpapi.io/', OBSERVED_AT)
        evidence.observe(frame, EXAMPLE, 'legacy_parser_match_unvalidated', OBSERVED_AT)
        sample = evidence.samples[0]
        self.assertEqual(sample['observed_at'], OBSERVED_AT)
        self.assertEqual(sample['sanitized_message']['timestamp'], 1793204432648)
        self.assertIsInstance(sample['sanitized_message']['timestamp'], int)
        self.assertEqual(sample['sanitized_message']['signature'], EXAMPLE['signature'])
        self.assertEqual(sample['wire_sha256'], sha256(frame.encode()).hexdigest())
        with patch('src.observe.utcnow', return_value=OBSERVED_AT):
            record = migration_from_event(EXAMPLE)
        self.assertEqual(record['observed_at'], OBSERVED_AT)
        self.assertEqual(EXAMPLE['timestamp'], 1793204432648)


class PublishedExcerptReplayTests(unittest.IsolatedAsyncioTestCase):
    async def test_mock_capture_distinguishes_migration_create_pool_and_duplicate(self):
        ws = AsyncMock()
        ws.recv.side_effect = [json.dumps(p) for p in
                               (EXAMPLE, {**EXAMPLE, 'action': 'createPool'}, EXAMPLE)]
        connection = MagicMock()
        connection.__aenter__ = AsyncMock(return_value=ws)
        connection.__aexit__ = AsyncMock(return_value=False)
        with tempfile.TemporaryDirectory() as temp, \
             patch('websockets.connect', return_value=connection) as connect:
            matches, status = await capture_migrations(
                ObservationConfig(duration_s=10, max_events=3, max_migrations=3), Path(temp))
            evidence = json.loads(Path(status['evidence']['file']).read_text())
        connect.assert_called_once()
        ws.send.assert_not_called()
        self.assertEqual(status['events_seen'], 3)
        self.assertEqual(status['legacy_parser_matches'], 1)
        self.assertEqual(status['reason'], 'event_limit')
        self.assertEqual(status['parser_outcomes'], {'legacy_parser_match_unvalidated': 1,
                         'not_legacy_migrate_action': 1, 'duplicate_mint': 1})
        self.assertEqual(matches[0][1], EXAMPLE)
        self.assertEqual(status['independent_migration_proof'], 'UNKNOWN')
        self.assertEqual(evidence['subscription']['messages_sent'], 0)
        self.assertEqual(evidence['samples'][0]['sanitized_message']['timestamp'], EXAMPLE['timestamp'])
        self.assertEqual(evidence['event_type_probes']['action=migrate'], 2)

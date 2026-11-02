import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from src.observe import (ObservationConfig, audit_layers, capture_migrations,
                         dex_summary, evaluate_mint, init_db, is_mint,
                         migration_from_event, mint_authorities, pair_for_migration,
                         research_verdict, save_raw)

ROOT = Path(__file__).resolve().parent.parent
M = json.loads((ROOT/'fixtures/provider_mocks.json').read_text())
MINT = M['migration']['mint']
POOL = M['migration']['poolId']

class MockResp:
    def __init__(self, data, status=200):
        self.status_code = status
        self.data = data
    def json(self): return self.data

class MockSession:
    def get(self,url,**kwargs):
        if 'dexscreener' in url:
            return MockResp(M['dex'])
        return MockResp({'markets': []})
    def post(self,url,**kwargs):
        method=kwargs['json']['method']
        if method == 'getAccountInfo':
            return MockResp(M['rpc_mint'])
        return MockResp({'result':{'value':[]}})

class ObserveTests(unittest.TestCase):
    def test_valid_migration(self):
        record=migration_from_event(M['migration'])
        self.assertEqual(record['mint'], MINT)
        self.assertEqual(record['pool'], POOL)
    def test_no_buy_event_as_migration(self):
        self.assertIsNone(migration_from_event({**M['migration'],'action':'buy'}))
    def test_no_invalid_mint(self):
        self.assertIsNone(migration_from_event({**M['migration'],'mint':'nope'}))
    def test_mint_base58_validation(self):
        self.assertTrue(is_mint(MINT)); self.assertFalse(is_mint('not_base58!!'))
    def test_exact_pool_match(self):
        self.assertEqual(pair_for_migration(M['dex'], POOL)['pairAddress'],POOL)
        self.assertIsNone(pair_for_migration(M['dex'], 'A' * 36))
    def test_no_pool_no_dex_certificate(self):
        self.assertEqual(dex_summary(M['dex'],None)['status'],'UNKNOWN')
    def test_authorities_parsed(self):
        auth = mint_authorities(M['rpc_mint'])
        self.assertTrue(auth['mint_revoked']);self.assertTrue(auth['freeze_revoked'])
    def test_authorities_malformed_fail_closed(self):
        self.assertIsNone(mint_authorities({'result':{'value':{'data':'garbage'}}})['mint_revoked'])
    def test_mint_authority_present_fails(self):
        bad=json.loads(json.dumps(M['rpc_mint']))
        bad['result']['value']['data']['parsed']['info']['mintAuthority']='active'
        auth=mint_authorities(bad)
        self.assertFalse(auth['mint_revoked'])
    def test_unknown_layers_never_pass(self):
        summary=dex_summary(M['dex'],POOL)
        layers=audit_layers(mint_authorities(M['rpc_mint']),summary,None,None,None)
        self.assertEqual(len(layers),8)
        self.assertEqual(layers[0]['status'],'PASS')
        self.assertEqual(layers[1]['status'],'PASS')
        self.assertEqual(layers[2]['status'],'UNKNOWN')
        self.assertEqual(research_verdict(layers),'UNVERIFIED_DO_NOT_TRADE')
    def test_missing_pair_not_approved(self):
        summary=dex_summary([],POOL)
        layers=audit_layers({},summary,None,None,None)
        self.assertEqual(layers[5]['status'],'UNKNOWN')
        self.assertEqual(research_verdict(layers),'UNVERIFIED_DO_NOT_TRADE')
    def test_real_adapter_mocked_evidence_and_sqlite(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            db=init_db(out)
            rec=evaluate_mint(migration_from_event(M['migration']), M['migration'],out,
                              db,MockSession(),ObservationConfig())
            self.assertEqual(rec['auditor'],'UNVERIFIED_DO_NOT_TRADE')
            self.assertEqual(len(list((out/'raw').glob('*.json'))),6)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM observations').fetchone()[0],6)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM decisions').fetchone()[0],3)
            self.assertEqual(db.execute('SELECT status FROM decisions ORDER BY id DESC LIMIT 1').fetchone()[0],
                             'UNVERIFIED_DO_NOT_TRADE')
            db.close()
    def test_rpc_error_not_clearance(self):
        with tempfile.TemporaryDirectory() as temp:
            class ErrorSession(MockSession):
                def post(self,url,**kwargs): return MockResp({'error':{'message':'rate limited'}},429)
            out=Path(temp);db=init_db(out)
            rec=evaluate_mint(migration_from_event(M['migration']),M['migration'],out,db,
                              ErrorSession(),ObservationConfig())
            self.assertEqual(rec['layers'][0]['status'],'UNKNOWN')
            db.close()
    def test_raw_preserves_data(self):
        with tempfile.TemporaryDirectory() as temp:
            output=save_raw(Path(temp),'migration',MINT,M['migration'])
            self.assertEqual(json.loads(Path(output).read_text())['payload'], M['migration'])

if __name__ == '__main__':unittest.main()

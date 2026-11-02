import unittest
from datetime import datetime,timedelta,timezone
from src.desk import Config,scan,audit,analyze,propose,paper_open,observe_risk,run_fixture
from pathlib import Path
import json
import tempfile

C=Config()
F=Path(__file__).resolve().parents[1]/'fixtures'/'synthetic_night.json'
COINS=json.loads(F.read_text())['coins']

class TestDesk(unittest.TestCase):
    def test_good_synthetic_scanner(self): self.assertTrue(scan(COINS[0],C)['passed'])
    def test_scanner_low_liquidity(self): self.assertFalse(scan(COINS[2],C)['passed'])
    def test_audit_freeze_reject(self): self.assertIn('freeze',audit(COINS[1],C)['reason'])
    def test_audit_all_pass(self): self.assertEqual(len(audit(COINS[0],C)['layers']),8)
    def test_audit_missing_data_fails(self):
        d={**COINS[0]};d.pop('max_delegate_holders');self.assertFalse(audit(d,C)['passed'])
    def test_no_minimum_ticket_bump(self): self.assertEqual(propose(COINS[0],200,C)['size_usd'],4.0)
    def test_analyst_proxy_not_llm(self): self.assertTrue(analyze(COINS[0])['passed'])
    def test_stop(self):
        t=datetime(2026,11,1,tzinfo=timezone.utc);p=paper_open({'signal_price':.001,'size_usd':4},t,C)
        r=observe_risk(p,.0009,60000,t+timedelta(minutes=2),C)
        self.assertEqual(r['action'],'PAPER_EXIT')
    def test_missing_liquidity_never_mark_last_as_fill(self):
        t=datetime(2026,11,1,tzinfo=timezone.utc);p=paper_open({'signal_price':.001,'size_usd':4},t,C)
        r=observe_risk(p,.0009,0,t+timedelta(minutes=2),C)
        self.assertEqual(r['action'],'UNKNOWN_EXIT')
        self.assertNotIn('hypothetical_pnl_usd',r)
    def test_stop_never_loosened(self):
        t=datetime(2026,11,1,tzinfo=timezone.utc);p=paper_open({'signal_price':.001,'size_usd':4},t,C)
        first=p['stop'];observe_risk(p,.00120,60000,t+timedelta(minutes=2),C)
        self.assertGreaterEqual(p['stop'],first)
    def test_fixture_run_records_database(self):
        with tempfile.TemporaryDirectory() as d:
            events=run_fixture(F,d)
            self.assertTrue(events)
            self.assertTrue((Path(d)/'journal.sqlite3').exists())

if __name__=='__main__':unittest.main()

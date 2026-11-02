from pathlib import Path
from src.desk import run_fixture
root=Path(__file__).resolve().parent
rows=run_fixture(root/'fixtures'/'synthetic_night.json',root/'output')
for row in rows:
    d={k:v for k,v in row.items() if k in ('mint','stage','passed','score','action','reason','size_usd','hypothetical_pnl_usd')}
    print(d)
print('\nSaved synthetic outputs to output/decisions.json and output/journal.sqlite3')

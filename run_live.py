"""Optional standalone read-only run (Colab uses await in a notebook instead)."""
import argparse
import asyncio
import sys
from pathlib import Path
import requests
from src.observe import (ObservationConfig, capture_migrations, evaluate_mint,
                         init_db, is_mint, write_summary)

async def run(duration=None, limit=3, manual_mint=None, *, events=None,
              capture_only=False, output='output', time_priority=False):
    if time_priority and not capture_only:
        raise ValueError('--time-priority requires --capture-only')
    duration = duration if duration is not None else (180 if time_priority else 45)
    events = events if events is not None else (1_000_000 if time_priority else 15000)
    cfg = ObservationConfig(duration_s=duration, max_migrations=limit, max_events=events,
                            time_priority=time_priority)
    cfg.validate_capture()
    if capture_only and manual_mint:
        raise ValueError('--capture-only cannot be combined with --mint')
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    db = None if capture_only else init_db(out)
    if manual_mint:
        if not is_mint(manual_mint):
            raise ValueError('Manual mint must be a valid Solana base58 address')
        migration = {'mint':manual_mint,'pool':None,'name':None,'symbol':None,
                     'source':'manual_mint_no_migration_proof'}
        observations = [(migration, {'note':'user-selected mint; migration not proved'})]
        status = {'connected':False,'events_seen':0,'migrations':0,'reason':'manual_mint'}
    else:
        observations, status = await capture_migrations(cfg,out)
    print('Stream:', status)
    results=[]
    with requests.Session() as session:
        for migration, raw in ([] if capture_only else observations):
            record = evaluate_mint(migration,raw,out,db,session,cfg)
            results.append(record)
            print(record['mint'], 'dex:', record['scanner']['status'],
                  'audit:', record['auditor'])
    if db is not None:
        db.close()
    write_summary(out,results,status)
    print(f'Saved {len(results)} evaluations to {out / "run_summary.json"}')
    if not results:
        print('No candidate evaluated. Parser matches are unvalidated; independent migration proof is UNKNOWN.')
    return status

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='TrenchLab v0.2 READ-ONLY observer')
    parser.add_argument('--seconds',type=int,default=None, help='1..180; default 180 in time-priority mode, otherwise 45')
    parser.add_argument('--limit',type=int,default=3, help='Legacy evaluation goal; does not end time-priority captures')
    parser.add_argument('--mint',default=None)
    parser.add_argument('--events', type=int, default=None, help='Emergency frame cap: default 1,000,000 in time-priority mode, otherwise 15,000')
    parser.add_argument('--capture-only', action='store_true', help='Stream diagnostics only; no Dex/Rug/RPC calls')
    parser.add_argument('--time-priority', action='store_true', help='Capture-only: target elapsed connected time, not sample/claim goals')
    parser.add_argument('--output', default='output', help='Local evidence directory')
    args=parser.parse_args()
    status = asyncio.run(run(args.seconds,args.limit,args.mint,events=args.events,
                            capture_only=args.capture_only,output=args.output,time_priority=args.time_priority))
    sys.exit(2 if status.get('reason') == 'stream_error' else 0)

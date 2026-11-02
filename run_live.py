"""Optional standalone read-only run (Colab uses await in a notebook instead)."""
import argparse
import asyncio
import sys
from pathlib import Path
import requests
from src.observe import (ObservationConfig, capture_migrations, evaluate_mint,
                         init_db, is_mint, write_summary)

async def run(duration=45, limit=3, manual_mint=None, *, events=15000,
              capture_only=False, output='output'):
    cfg = ObservationConfig(duration_s=duration, max_migrations=limit, max_events=events)
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
    parser.add_argument('--seconds',type=int,default=45)
    parser.add_argument('--limit',type=int,default=3)
    parser.add_argument('--mint',default=None)
    parser.add_argument('--events', type=int, default=15000, help='Frame cap, 1..15000')
    parser.add_argument('--capture-only', action='store_true', help='Stream diagnostics only; no Dex/Rug/RPC calls')
    parser.add_argument('--output', default='output', help='Local evidence directory')
    args=parser.parse_args()
    status = asyncio.run(run(args.seconds,args.limit,args.mint,events=args.events,
                            capture_only=args.capture_only,output=args.output))
    sys.exit(2 if status.get('reason') == 'stream_error' else 0)

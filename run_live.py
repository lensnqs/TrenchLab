"""Optional standalone read-only run (Colab uses await in a notebook instead)."""
import argparse
import asyncio
from pathlib import Path
import requests
from src.observe import (ObservationConfig, capture_migrations, evaluate_mint,
                         init_db, is_mint, write_summary)

async def run(duration=45, limit=3, manual_mint=None):
    cfg = ObservationConfig(duration_s=duration, max_migrations=limit)
    out = Path('output')
    db = init_db(out)
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
        for migration, raw in observations:
            record = evaluate_mint(migration,raw,out,db,session,cfg)
            results.append(record)
            print(record['mint'], 'dex:', record['scanner']['status'],
                  'audit:', record['auditor'])
    db.close()
    write_summary(out,results,status)
    print(f'Saved {len(results)} observations to output/run_summary.json and output/raw/')
    if not results:
        print('No migrations captured. Not proof the stream was broken; try a longer bounded window.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='TrenchLab v0.2 READ-ONLY observer')
    parser.add_argument('--seconds',type=int,default=45)
    parser.add_argument('--limit',type=int,default=3)
    parser.add_argument('--mint',default=None)
    args=parser.parse_args()
    asyncio.run(run(args.seconds,args.limit,args.mint))

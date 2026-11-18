"""One-off diagnostics; does not alter source configuration."""
import concurrent.futures
import json
from pathlib import Path
from core import http_fetch, read_json

ROOT = Path(__file__).resolve().parents[1]

def probe(s):
    try:
        data,headers=http_fetch(s,read_json(ROOT/'config/site.json'))
        out=ROOT/'runtime'/'probe';out.mkdir(parents=True,exist_ok=True)
        (out/(s['id']+'.txt')).write_bytes(data)
        return {'id':s['id'],'status':200,'bytes':len(data),'type':headers.get('Content-Type')}
    except Exception as e:
        return {'id':s['id'],'error':str(e)}

if __name__ == '__main__':
    sources=json.loads((ROOT/'config/sources.json').read_text(encoding='utf-8'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        for result in pool.map(probe, [s for s in sources if s['enabled']]):
            print(json.dumps(result, ensure_ascii=True), flush=True)

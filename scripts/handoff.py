"""Create a portable owner-only handoff archive, using a consistent SQLite backup."""
import argparse
from contextlib import closing
import datetime as dt
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import zipfile
from core import ROOT, now, run_lock, write_json

def create_archive(state_only=False):
    output=ROOT/'artifacts';output.mkdir(exist_ok=True)
    name='lexatlas-private-state-'+dt.datetime.now().strftime('%Y%m%d-%H%M%S')+'.zip' if state_only else 'LexAtlas-完整交接包.zip'
    destination=output/name
    with run_lock(), tempfile.TemporaryDirectory(prefix='handoff-',dir=ROOT/'runtime') as temporary:
        snapshot=Path(temporary)/'lexatlas.sqlite3'
        source=ROOT/'runtime/lexatlas.sqlite3'
        if source.exists():
            with closing(sqlite3.connect(source)) as live, closing(sqlite3.connect(snapshot)) as backup:
                live.backup(backup)
                for batch,path in backup.execute('SELECT id,path FROM batches').fetchall():
                    parsed=Path(path)
                    if parsed.is_absolute() and parsed.is_relative_to(ROOT):
                        backup.execute('UPDATE batches SET path=? WHERE id=?',(str(parsed.relative_to(ROOT)).replace('\\','/'),batch))
                backup.commit()
                backup.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        with zipfile.ZipFile(destination,'w',zipfile.ZIP_DEFLATED) as archive:
            prefix=Path('lexatlas')
            if not state_only:
                excluded={'.git','.qa','__pycache__','node_modules','.venv','runtime','artifacts','dist.previous','.sites-workflow','.wrangler'}
                for path in ROOT.rglob('*'):
                    relative=path.relative_to(ROOT)
                    if not path.is_file() or any(part in excluded or part.startswith('.dist-stage-') for part in relative.parts):continue
                    if path.name.startswith('.env') or path.suffix in ('.pyc','.log','.zip') or path.name.endswith('.tar.gz'):continue
                    archive.write(path,str(prefix/relative))
            if snapshot.exists():archive.write(snapshot,str(prefix/'runtime/lexatlas.sqlite3'))
            for folder in ('workbuddy','cache','logs','cfp'):
                directory=ROOT/'runtime'/folder
                if directory.exists():
                    for path in directory.rglob('*'):
                        if path.is_file():archive.write(path,str(prefix/path.relative_to(ROOT)))
            marker={'created_at':now(),'private_state_included':True,'codex_runtime_required':False,
                    'notice':'包含本机数据库、来源证据与模型任务，仅交付网站所有者；不要当作公开网站上传。'}
            archive.writestr(str(prefix/'HANDOFF-MANIFEST.json'),json.dumps(marker,ensure_ascii=False,indent=2))
    digest=hashlib.sha256(destination.read_bytes()).hexdigest()
    write_json(destination.with_suffix('.sha256.json'),{'file':destination.name,'sha256':digest,'bytes':destination.stat().st_size,'created_at':now()})
    print(json.dumps({'archive':str(destination),'sha256':digest,'bytes':destination.stat().st_size},ensure_ascii=True))
    return destination

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--state-only',action='store_true')
    create_archive(parser.parse_args().state_only)

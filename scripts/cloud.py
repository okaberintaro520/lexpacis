"""Cloud metadata runner and sanitized handoff. No model, proxy, or paid API."""
import argparse
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import zipfile
from core import ROOT, database, identity, now, plain, read_json, run_lock, safe_url, upsert_item, write_json
import pipeline


def restore_snapshot(conn, snapshot, config, sources):
    """Reconstruct ephemeral state from this repository's already-public release only."""
    if conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]:
        raise ValueError('云端恢复只能写入空数据库，不能覆盖本机运营状态')
    by_source={s['id']:s for s in sources}
    if not isinstance(snapshot,dict) or len(snapshot.get('items',[]))>config['max_public_items']:
        raise ValueError('公开快照格式或大小异常')
    for item in snapshot.get('items',[]):
        source=by_source.get(item.get('source_id'))
        if not source or not safe_url(item.get('url','')) or item.get('id')!=identity(item['url'],item.get('doi','')):
            raise ValueError('公开快照含未登记来源、不安全链接或不匹配的 ID')
        entry={k:item.get(k) for k in ('title','url','doi','authors','published_at','date_precision','bibliography','evidence_basis')}
        entry['evidence']=''
        upsert_item(conn,entry,source,config)
        conn.execute('UPDATE items SET discovered_at=?,updated_at=? WHERE id=?',(item['discovered_at'],item['updated_at'],item['id']))
        revision=item.get('source_revision')
        if isinstance(revision,str) and re.fullmatch(r'[0-9a-f]{64}',revision):
            conn.execute('UPDATE items SET content_hash=? WHERE id=?',(revision,item['id']))
        for provenance in item.get('provenance',[]):
            if provenance.get('source_id') in by_source and safe_url(provenance.get('url','')) and provenance.get('seen_at'):
                conn.execute('INSERT OR REPLACE INTO provenance VALUES(?,?,?,?)',
                             (item['id'],provenance['source_id'],provenance['url'],provenance['seen_at']))
    for source in snapshot.get('sources',[]):
        if source.get('id') not in by_source:continue
        failures=source.get('consecutive_failures',0)
        failures=max(0,min(failures,999)) if isinstance(failures,int) else 0
        conn.execute('INSERT OR REPLACE INTO source_state(id,attempted_at,success_at,status,error,item_count,next_attempt_at,failures) VALUES(?,?,?,?,?,?,?,?)',
                     (source['id'],source.get('attempted_at'),source.get('success_at'),source.get('status','unverified'),source.get('error'),source.get('item_count',0),source.get('next_attempt_at'),failures))
    conn.commit()


def retain_translations(conn,snapshot,config,sources):
    """Carry already validated publication fields forward through unchanged source revisions."""
    by_source={s['id']:s for s in sources}
    for old in snapshot.get('items',[]):
        if not old.get('title_zh'):continue
        row=conn.execute('SELECT * FROM items WHERE id=?',(old['id'],)).fetchone()
        if not row or row['title']!=old['title'] or row['source_id']!=old['source_id']:continue
        source=by_source[row['source_id']]
        item={'id':row['id'],'content_hash':row['content_hash'],'title':row['title'],'module':row['module'],
              'authority':source['authority'],'source_excerpt':row['evidence'],'evidence_basis':row['evidence_basis']}
        result={'id':row['id'],'content_hash':row['content_hash'],'title_zh':old['title_zh'],'summary_zh':'',
                'module':row['module'],'topics':json.loads(row['topics']),'evidence_quotes':[],'event':None,'deadline':None}
        same_revision=bool(old.get('source_revision') and old['source_revision']==row['content_hash'])
        if same_revision:
            dates=[old[key].get('date_text','') for key in ('event','deadline') if isinstance(old.get(key),dict)]
            item['source_excerpt']+='\n'+'\n'.join(value for value in dates if isinstance(value,str) and len(value)<=100)
        for key in ('event','deadline'):
            if old.get(key):
                trial={**result,key:old[key]}
                try:pipeline.validate_enrichment(trial,item,config)
                except ValueError:continue
                result=trial
        # Titles and individual date fields were validated above. The summary is
        # original published content and is copied only for the identical revision.
        result=pipeline.validate_enrichment(result,item,config)
        summary=old.get('summary_zh','')
        if same_revision and isinstance(summary,str) and 0<len(summary)<=600 and plain(summary)==summary:
            result['summary_zh']=summary
        valid=result
        ai=old.get('ai') or {}
        conn.execute('INSERT OR REPLACE INTO enrichments VALUES(?,?,?,?,?)',
                     (row['id'],row['content_hash'],json.dumps(valid,ensure_ascii=False),ai.get('model','既有公开标题译名'),ai.get('processed_at',old['updated_at'])))
    conn.commit()


def restore_monitors(snapshot):
    from cfp import approved_targets
    journals,seeds,targets=approved_targets();approved={t['id']:t for t in targets}
    pages={}
    public=snapshot.get('cfp',{})
    for row in public.get('journals',[]):
        key='journal:'+row['id']
        if key in approved:
            pages[key]={'id':key,'url':approved[key]['url'],'checked_at':row.get('checked_at'),
                        'success_at':row.get('success_at'),'status':row.get('check_status','unverified'),'error':row.get('error')}
    for row in public.get('calls',[]):
        key='call:'+row['id']
        if key in approved:
            pages[key]={'id':key,'url':approved[key]['url'],'checked_at':row.get('last_monitor_at'),
                        'status':row.get('monitor_status','unverified')}
    write_json(ROOT/'runtime/cfp/state.json',{'pages':pages,'updated_at':public.get('updated_at')})


def github_base_url(repository):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):raise ValueError('无效仓库标识')
    owner,name=repository.split('/')
    return 'https://'+owner.lower()+'.github.io'+('' if name.lower()==owner.lower()+'.github.io' else '/'+name)


def run(offline=False):
    if not offline and os.environ.get('GITHUB_ACTIONS')!='true':
        raise ValueError('此命令的联网模式用于 GitHub 云端；本机验收请用 --offline，不修改本机网络设置')
    config,sources=pipeline.configuration();config=copy.deepcopy(config)
    snapshot=read_json(ROOT/'dist/data.json',{})
    if not snapshot.get('items'):raise ValueError('缺少已发布的公开资料快照')
    repository=os.environ.get('GITHUB_REPOSITORY','')
    if not offline:config['base_url']=github_base_url(repository)
    with run_lock():
        conn=database(ROOT)
        try:
            restore_snapshot(conn,snapshot,config,sources)
            restore_monitors(snapshot)
            stats={'successes':0,'failures':0,'offline_validation':True}
            if not offline:
                from cfp import refresh
                stats=pipeline.collect(conn,config,sources)
                refresh(config,limit=40)
            retain_translations(conn,snapshot,config,sources)
            previous=snapshot.get('operations',{})
            last=previous.get('last_effective_run') or previous.get('last_run')
            if not last or not (last.get('successes') or last.get('failures')):last=None
            write_json(ROOT/'runtime/cloud/operation.json',{'runner':'offline-validation' if offline else 'github-actions',
                       'event':'offline' if offline else os.environ.get('GITHUB_EVENT_NAME','unknown'),'last_cloud_run':now() if not offline else None,
                       'scheduled_run_verified':previous.get('scheduled_run_verified',False),'previous_effective_run':last})
            data=pipeline.build(conn,config,sources)
            from security_audit import audit
            if audit()['issues']:raise ValueError('发布目录安全检查失败')
            # This is the only upload artifact: public static files, never SQLite/cache/agent tasks.
            artifact=ROOT/'runtime/cloud/artifact.tar'
            if offline:
                artifact.parent.mkdir(parents=True,exist_ok=True)
                with tarfile.open(artifact,'w') as archive:
                    for path in sorted((ROOT/'dist').rglob('*')):
                        if path.is_symlink():raise ValueError('发布产物不接受符号链接')
                        if path.is_file():archive.add(path,arcname=path.relative_to(ROOT/'dist').as_posix(),recursive=False)
            report={'runner':'offline' if offline else 'github-actions','items':len(data['items']),'collection':stats,'model_calls':0,
                    'deployment_confirmed':False,'artifact':'runtime/cloud/artifact.tar' if offline else 'dist/'}
            write_json(ROOT/'runtime/cloud/result.json',report);print(json.dumps(report,ensure_ascii=True));return report
        finally:conn.close()


def export_source():
    """New ZIP without git history, local state, credentials or original hosting identity."""
    folders=('scripts','config','web','tests','docs','dist','.github')
    singles=('README.md','package.json','.gitignore')
    output=ROOT/'artifacts/LexAtlas-云端部署源码.zip';output.parent.mkdir(exist_ok=True)
    names=[]
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        for folder in folders:
            for path in sorted((ROOT/folder).rglob('*')):
                if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts or path.suffix=='.pyc':continue
                name=path.relative_to(ROOT).as_posix()
                if '/.openai/' in name or path.name.startswith('.env'):continue
                if folder=='docs' and name!='docs/LEXPACIS_MANUAL.md':continue
                if name=='config/news-initial.json':continue
                archive.write(path,name);names.append(name)
        for name in singles:
            if (ROOT/name).exists():archive.write(ROOT/name,name);names.append(name)
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    write_json(output.with_suffix('.sha256.json'),{'sha256':digest,'files':len(names),'private_runtime_included':False,'git_history_included':False})
    print(json.dumps({'archive':str(output),'sha256':digest,'files':len(names)},ensure_ascii=True));return output


def commit_public_release():
    """Persist the public snapshot; the complete website travels as a Pages artifact."""
    if os.environ.get('GITHUB_ACTIONS')!='true':raise ValueError('仅供 GitHub 云端使用')
    token=os.environ.get('GITHUB_TOKEN','');repository=os.environ.get('GITHUB_REPOSITORY','');github_base_url(repository)
    if not token:raise ValueError('缺少 GitHub 自动提供的任务令牌')
    def git(*args,env=None):return subprocess.run(['git',*args],cwd=ROOT,env=env,check=True,capture_output=True,text=True)
    snapshot='dist/data.json'
    git('add','--',snapshot)
    if not git('diff','--cached','--name-only').stdout.strip():return
    staged=git('diff','--cached','--name-only').stdout.splitlines()
    if staged!=[snapshot]:raise ValueError('暂存区存在公开数据快照以外的变更')
    git('-c','user.name=LexAtlas updater','-c','user.email=lexatlas-updater@users.noreply.github.com','commit','-m','Update public metadata snapshot')
    env=os.environ.copy();env.pop('GITHUB_TOKEN',None)
    env.update(GIT_CONFIG_COUNT='2',GIT_CONFIG_KEY_0='http.https://github.com/.extraheader',
               GIT_CONFIG_VALUE_0='AUTHORIZATION: basic '+base64.b64encode(('x-access-token:'+token).encode()).decode(),
               GIT_CONFIG_KEY_1='http.followRedirects',GIT_CONFIG_VALUE_1='false',GIT_TERMINAL_PROMPT='0')
    for key in list(env):
        if key.startswith('GIT_TRACE') or key=='GIT_CURL_VERBOSE':env.pop(key)
    branch=os.environ.get('GITHUB_REF_NAME','')
    if not branch:raise ValueError('缺少任务分支标识')
    git('check-ref-format','refs/heads/'+branch)
    git('push','https://github.com/'+repository+'.git','HEAD:refs/heads/'+branch,env=env)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);commands=parser.add_subparsers(dest='command',required=True)
    p=commands.add_parser('run');p.add_argument('--offline',action='store_true')
    commands.add_parser('export');commands.add_parser('commit')
    args=parser.parse_args()
    if args.command=='run':run(args.offline)
    elif args.command=='export':export_source()
    else:commit_public_release()

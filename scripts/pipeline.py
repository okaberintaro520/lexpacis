"""LexAtlas operational CLI. Python >=3.10; no dependencies and no paid calls."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import http.server
import json
from pathlib import Path
import re
import shutil
import sys
import urllib.error
import uuid
import webbrowser
from core import ROOT, UTC, atomic_write, database, fingerprint, http_fetch, log, now, parse_crossref, parse_date, parse_feed, parse_listing, plain, read_json, run_lock, safe_url, upsert_item, write_json
from publication_policy import restricted_content, source_paused

def configuration():
    return read_json(ROOT/'config/site.json'),read_json(ROOT/'config/sources.json')

def visible(row, sources, rules):
    source=next((s for s in sources if s['id']==row['source_id']),None)
    return bool(source and source.get('reuse')=='metadata_only' and row['visibility']=='public'
                and not source_paused(source,rules)
                and row['id'] not in rules.get('hidden_items',[])
                and row['module'] not in rules.get('paused_modules',[])
                and not restricted_content([row['title'],row['url'],row['doi'],row['evidence'],
                                            json.loads(row['bibliography'])],rules))

def collect(conn,config,sources,force=False):
    started=now(); stats={'successes':0,'failures':0,'added':0,'changed':0,'skipped':0}
    rules=read_json(ROOT/'config/visibility.json',{})
    for source in sources:
        if not source.get('enabled') or source_paused(source,rules): continue
        state=conn.execute('SELECT * FROM source_state WHERE id=?',(source['id'],)).fetchone()
        if state and not force:
            if state['next_attempt_at'] and state['next_attempt_at']>now():
                stats['skipped']+=1; continue
            if state['success_at']:
                age=(dt.datetime.now(UTC)-dt.datetime.fromisoformat(state['success_at'])).total_seconds()
                if age<source['poll_hours']*3600: stats['skipped']+=1; continue
        print(f"[collect] {source['id']} ...",flush=True)
        try:
            data,headers=http_fetch(source,config,state)
            if data is None:
                conn.execute("UPDATE source_state SET attempted_at=?,success_at=?,status='ok',error=NULL,failures=0,next_attempt_at=NULL WHERE id=?",(now(),now(),source['id']))
                conn.commit(); stats['successes']+=1; continue
            if source['kind']=='rss': entries=parse_feed(data,source)
            elif source['kind']=='crossref': entries=parse_crossref(data,source)
            elif source['kind']=='html': entries=parse_listing(data,source)
            else: raise ValueError('不支持的采集器类型')
            if not entries: raise ValueError('没有解析到条目；请检查信源结构，未覆盖旧数据')
            # Keep source evidence private. Raw responses never enter dist/.
            cache=ROOT/'runtime'/'cache'/source['id']; cache.mkdir(parents=True,exist_ok=True)
            (cache/'latest.response').write_bytes(data)
            for entry in entries[:config['max_entries_per_source']]:
                # Future publication dates are valid index metadata, not current events.
                result=upsert_item(conn,entry,source,config)
                if result in stats: stats[result]+=1
            conn.execute('''INSERT INTO source_state VALUES(?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET attempted_at=excluded.attempted_at,success_at=excluded.success_at,
                status=excluded.status,error=NULL,etag=excluded.etag,last_modified=excluded.last_modified,
                item_count=excluded.item_count,failures=0,next_attempt_at=NULL''',
                (source['id'],now(),now(),'ok',None,headers.get('ETag'),headers.get('Last-Modified'),len(entries),0,None))
            conn.commit(); stats['successes']+=1
            log('source_success',source=source['id'],parsed=len(entries))
            print(f"  OK {len(entries)}",flush=True)
        except Exception as error:
            conn.rollback()
            failures=(state['failures'] if state else 0)+1
            delay=min(24*3600,900*2**min(failures-1,6))
            if isinstance(error,urllib.error.HTTPError):
                retry=error.headers.get('Retry-After','')
                if retry.isdigit(): delay=max(delay,min(int(retry),7*86400))
                else:
                    parsed,_=parse_date(retry)
                    if parsed and 'T' in parsed: delay=max(delay,min(7*86400,int((dt.datetime.fromisoformat(parsed)-dt.datetime.now(UTC)).total_seconds())))
            retry_at=(dt.datetime.now(UTC)+dt.timedelta(seconds=delay)).isoformat(timespec='seconds')
            message=str(error)[:350]
            conn.execute('''INSERT INTO source_state(id,attempted_at,status,error,failures,next_attempt_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET attempted_at=excluded.attempted_at,
                status=excluded.status,error=excluded.error,failures=excluded.failures,next_attempt_at=excluded.next_attempt_at''',
                (source['id'],now(),'error',message,failures,retry_at))
            conn.commit(); stats['failures']+=1
            log('source_failure',source=source['id'],error=message,retry_at=retry_at)
            print(f'  FAILED {message}',flush=True)
    conn.execute('INSERT INTO runs(started_at,finished_at,successes,failures,added,changed) VALUES(?,?,?,?,?,?)',
                 (started,now(),stats['successes'],stats['failures'],stats['added'],stats['changed']))
    conn.commit(); log('collection_complete',**stats)
    print(json.dumps(stats,ensure_ascii=False))
    return stats

def prepare(conn,config,sources):
    rules=read_json(ROOT/'config/visibility.json',{})
    active=conn.execute("SELECT * FROM batches WHERE status IN ('pending','partial') ORDER BY created_at DESC LIMIT 1").fetchone()
    if active and (ROOT/active['path']).exists():
        if Path(active['path']).is_absolute():
            relative=str(Path(active['path']).relative_to(ROOT)).replace('\\','/')
            conn.execute('UPDATE batches SET path=? WHERE id=?',(relative,active['id']));conn.commit()
            atomic_write(ROOT/'runtime'/'workbuddy'/'CURRENT.txt',relative+'\n')
        age=(dt.datetime.now(UTC)-dt.datetime.fromisoformat(active['created_at'])).total_seconds()
        active_items=read_json(ROOT/active['path'])['items']
        fresh=all((row:=conn.execute('SELECT * FROM items WHERE id=?',(item['id'],)).fetchone())
                  and row['content_hash']==item['content_hash'] and visible(row,sources,rules) for item in active_items)
        if age<86400 and fresh:
            print(f"[prepare] reuse {active['path']}"); return ROOT/active['path']
        conn.execute("UPDATE batches SET status='expired' WHERE id=?",(active['id'],)); conn.commit()
    today=now()[:10]
    used=conn.execute("SELECT COUNT(*) FROM attempts WHERE status='accepted' AND substr(attempted_at,1,10)=?",(today,)).fetchone()[0]
    limit=max(0,min(config['ai_batch_size'],config['ai_daily_limit']-used))
    rows=conn.execute('''SELECT i.* FROM items i LEFT JOIN enrichments e ON i.id=e.item_id
        WHERE e.item_id IS NULL OR e.content_hash<>i.content_hash
        ORDER BY CASE WHEN i.module='events' THEN 0 ELSE 1 END, COALESCE(i.published_at,i.discovered_at) DESC''').fetchall()
    items=[]
    for row in rows:
        if len(items)>=limit: break
        if not visible(row,sources,rules): continue
        attempts=conn.execute("SELECT COUNT(*) FROM attempts WHERE item_id=? AND status='rejected' AND attempted_at>?",(row['id'],(dt.datetime.now(UTC)-dt.timedelta(days=1)).isoformat())).fetchone()[0]
        if attempts>=3: continue
        source=next(s for s in sources if s['id']==row['source_id'])
        items.append({'id':row['id'],'content_hash':row['content_hash'],'title':row['title'],
                      'url':row['url'],'source':source['name'],'authority':source['authority'],
                      'module':row['module'],'topics':json.loads(row['topics']),
                      'published_at':row['published_at'],'date_precision':row['date_precision'],
                      'authors':json.loads(row['authors']),'bibliography':json.loads(row['bibliography']),
                      'evidence_basis':row['evidence_basis'],'source_excerpt':row['evidence']})
    if not items:
        print('[prepare] 没有待处理条目，或今日 AI 处理上限已达到。'); return None
    batch_id=dt.datetime.now(UTC).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:6]
    folder=ROOT/'runtime'/'workbuddy'/batch_id; folder.mkdir(parents=True)
    path=folder/'input.json'
    write_json(path,{'schema_version':1,'batch_id':batch_id,'created_at':now(),
                    'allowed_topics':[t['id'] for t in config['topics']],
                    'allowed_modules':[m['id'] for m in config['modules']],
                    'instructions_file':'docs/EDITORIAL_POLICY.md','items':items})
    template=read_json(ROOT/'config/enrichment.schema.json')
    write_json(folder/'output.schema.json',template)
    relative=str(path.relative_to(ROOT)).replace('\\','/')
    atomic_write(ROOT/'runtime'/'workbuddy'/'CURRENT.txt',relative+'\n')
    conn.execute('INSERT INTO batches VALUES(?,?,?,?)',(batch_id,now(),'pending',relative)); conn.commit()
    log('batch_prepared',batch_id=batch_id,count=len(items))
    print(f'[prepare] {path} ({len(items)} items)')
    return path

def validate_enrichment(payload,item,config):
    allowed={'id','content_hash','title_zh','summary_zh','topics','module','evidence_quotes','event','deadline'}
    if not isinstance(payload,dict) or set(payload)-allowed: raise ValueError('条目存在未知字段或不是对象')
    required={'id','content_hash','title_zh','summary_zh','topics','module','evidence_quotes'}
    if not required.issubset(payload): raise ValueError('缺少必填字段')
    if payload.get('id')!=item['id'] or payload.get('content_hash')!=item['content_hash']:
        raise ValueError('条目 ID 或证据版本不匹配')
    title=payload.get('title_zh',''); summary=payload.get('summary_zh','')
    if not isinstance(title,str) or not 1<=len(title)<=240: raise ValueError('中文标题为空或超长')
    if not isinstance(summary,str) or len(summary)>600: raise ValueError('摘要超长或类型错误')
    if any(plain(text)!=text.strip() for text in (title,summary)): raise ValueError('标题或摘要包含 HTML 或非规范空白')
    topics=payload.get('topics',[])
    if not isinstance(topics,list) or any(t not in [x['id'] for x in config['topics']] for t in topics):
        raise ValueError('未知专题')
    module=payload.get('module',item['module'])
    if module not in [m['id'] for m in config['modules']]: raise ValueError('未知模块')
    if module in ('official','cases') and item.get('authority')!='official_institution':
        raise ValueError('学术评论或索引不能改写成官方文件或案件原始材料')
    if (item['evidence_basis'] in ('书目元数据','官方目录标题','RSS 标题') or not item.get('source_excerpt','').strip()) and summary:
        raise ValueError('只有标题或书目信息时，不得生成实质内容摘要；summary_zh 应为空')
    quotes=payload.get('evidence_quotes',[])
    evidence=item['title']+'\n'+item.get('source_excerpt','')
    if not isinstance(quotes,list) or len(quotes)>8: raise ValueError('证据引用格式错误')
    for quote in quotes:
        if not isinstance(quote,str) or len(quote)<6 or quote not in evidence:
            raise ValueError('证据片段不在输入中')
    if summary and not quotes: raise ValueError('摘要缺少输入证据片段')
    for key in ('event','deadline'):
        value=payload.get(key)
        if value is None: continue
        if module!='events': raise ValueError('日历日期只能用于学术活动条目')
        if not isinstance(value,dict) or set(value)!={'date','date_text','label'}: raise ValueError('日期字段格式错误')
        parsed,precision=parse_date(value['date'])
        if precision!='day' or parsed!=value['date']: raise ValueError('只接收明确的日历日期 YYYY-MM-DD')
        if not isinstance(value['date_text'],str) or value['date_text'] not in evidence: raise ValueError('日期缺少原文依据')
        original,original_precision=parse_date(value['date_text'])
        if original_precision!='day' or original!=parsed: raise ValueError('原文日期与规范化日期不一致；复杂日期请留空')
        if not isinstance(value['label'],str) or len(value['label'])>80: raise ValueError('日期标签超长')
    return {**payload,'module':module,'topics':list(dict.fromkeys(topics)),'title_zh':title.strip(),'summary_zh':summary.strip()}

def apply(conn,config,sources,path):
    path=Path(path).resolve()
    if not path.is_relative_to((ROOT/'runtime/workbuddy').resolve()):raise ValueError('模型输出必须位于项目 runtime/workbuddy 目录')
    response=read_json(path)
    if not isinstance(response,dict) or set(response)!={'batch_id','model','items'} or not isinstance(response['items'],list):
        raise ValueError('输出需严格包含 batch_id、model、items 三个字段')
    if not isinstance(response['model'],str) or not 1<=len(response['model'])<=120: raise ValueError('需填写实际使用的模型名称')
    batch=conn.execute('SELECT * FROM batches WHERE id=?',(response['batch_id'],)).fetchone()
    if not batch or batch['status'] not in ('pending','partial'): raise ValueError('未知、过期或已完成的批次')
    batch_path=ROOT/batch['path']
    request=read_json(batch_path); expected={item['id']:item for item in request['items']}
    if len(response['items'])>len(expected): raise ValueError('输出条目超出本批次范围')
    accepted=0; rejected=[]; seen=set()
    for entry in response['items']:
        key=entry.get('id','') if isinstance(entry,dict) else ''
        try:
            if key not in expected or key in seen: raise ValueError('未知或重复条目 ID')
            seen.add(key)
            row=conn.execute('SELECT * FROM items WHERE id=?',(key,)).fetchone()
            if not row or row['content_hash']!=expected[key]['content_hash']: raise ValueError('原始资料已更新，请重新准备批次')
            previous=conn.execute('SELECT content_hash FROM enrichments WHERE item_id=?',(key,)).fetchone()
            if previous and previous['content_hash']==row['content_hash']: continue
            validated=validate_enrichment(entry,expected[key],config)
            conn.execute('INSERT OR REPLACE INTO enrichments VALUES(?,?,?,?,?)',
                         (key,row['content_hash'],json.dumps(validated,ensure_ascii=False),response['model'],now()))
            conn.execute('INSERT INTO attempts VALUES(?,?,?,?,?)',(key,batch['id'],now(),'accepted',''))
            accepted+=1
        except (ValueError,TypeError,KeyError) as error:
            reason=str(error)
            conn.execute('INSERT INTO attempts VALUES(?,?,?,?,?)',(key,batch['id'],now(),'rejected',reason))
            rejected.append({'id':key,'reason':reason})
    completed_ids={r[0] for r in conn.execute('''SELECT e.item_id FROM enrichments e JOIN items i ON i.id=e.item_id
        WHERE e.item_id IN ('''+','.join('?' for _ in expected)+') AND e.content_hash=i.content_hash',tuple(expected)).fetchall()}
    completed=len(completed_ids)
    status='complete' if completed==len(expected) else 'partial'
    conn.execute('UPDATE batches SET status=? WHERE id=?',(status,batch['id'])); conn.commit()
    report={'batch_id':batch['id'],'accepted':accepted,'rejected':rejected,'remaining':len(expected)-completed,
            'completed_ids':sorted(completed_ids),'remaining_ids':[key for key in expected if key not in completed_ids],'status':status}
    write_json(batch_path.parent/'validation.json',report)
    log('batch_applied',**report); print(json.dumps(report,ensure_ascii=False,indent=2))
    return report

def public_data(conn,config,sources):
    rules=read_json(ROOT/'config/visibility.json',{})
    paused_sources={s['id'] for s in sources if source_paused(s,rules)}
    items=[]
    rows=conn.execute('SELECT * FROM items ORDER BY COALESCE(published_at,discovered_at) DESC').fetchall()
    for row in rows:
        if not visible(row,sources,rules): continue
        item={k:row[k] for k in ('id','source_id','title','url','doi','module','published_at','date_precision','discovered_at','updated_at','evidence_basis')}
        item['source_revision']=row['content_hash']
        item.update(topics=json.loads(row['topics']),authors=json.loads(row['authors']),bibliography=json.loads(row['bibliography']))
        item['material_type']={'wto':'官方新闻','icj':'官方新闻稿索引','pca':'机构公告索引','esil':'学会公告'}.get(row['source_id'],
                              '书目元数据' if row['source_id'].startswith('crossref-') else '官方机构新闻报道' if next((s.get('authority') for s in sources if s['id']==row['source_id']),None)=='official_news_service' else '学术平台文章')
        provenance=[dict(p) for p in conn.execute('SELECT source_id,url,seen_at FROM provenance WHERE item_id=?',(row['id'],))]
        if restricted_content(provenance,rules): continue
        item['provenance']=[p for p in provenance if p['source_id'] not in paused_sources]
        enrichment=conn.execute('SELECT * FROM enrichments WHERE item_id=? AND content_hash=?',(row['id'],row['content_hash'])).fetchone()
        item.update(title_zh='',summary_zh='',ai=None,event=None,deadline=None)
        if enrichment:
            enriched=json.loads(enrichment['payload'])
            if restricted_content(enriched,rules): continue
            item.update({key:enriched.get(key) for key in ('title_zh','summary_zh','module','topics','event','deadline')})
            item['ai']={'model':enrichment['model'],'processed_at':enrichment['created_at'],'basis':row['evidence_basis']}
        if item['module'] not in rules.get('paused_modules',[]) and not restricted_content(item,rules):
            items.append(item)
    source_info=[]
    for source in sources:
        if source['id'] in rules.get('hidden_sources',[]): continue
        paused=source['id'] in paused_sources
        state=conn.execute('SELECT * FROM source_state WHERE id=?',(source['id'],)).fetchone()
        info={key:source.get(key) for key in ('id','name','organization','homepage','kind','module','authority','enabled','poll_hours','scope','language')}
        if paused:
            info['enabled']=False
            state=None
        if source['kind']=='rss' and not paused:info['feed_url']=source['url']
        info.update(status='paused' if paused else state['status'] if state else ('unverified' if source['enabled'] else 'candidate'),
                    attempted_at=state['attempted_at'] if state else None,
                    success_at=state['success_at'] if state else None,
                    error='信源暂未成功读取或解析。' if state and state['error'] else None,
                    consecutive_failures=state['failures'] if state else 0,
                    item_count=sum(1 for x in items if x['source_id']==source['id']),
                    next_attempt_at=state['next_attempt_at'] if state else None)
        source_info.append(info)
    last_run=conn.execute('SELECT * FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    from cfp import public_data as cfp_public_data
    cloud=read_json(ROOT/'runtime/cloud/operation.json',{})
    cloud_run=cloud.get('runner')=='github-actions' and bool(cloud.get('last_cloud_run'))
    return {'schema_version':2,'generated_at':now(),'site':{k:config[k] for k in ('name','english_name','tagline','description','base_url','timezone')},
            'topics':[{k:t[k] for k in ('id','name','short')} for t in config['topics']],
            'modules':config['modules'],'items':items[:config['max_public_items']],
            'paused_modules':rules.get('paused_modules',[]),
            'sources':source_info,'cfp':cfp_public_data(conn,items),'operations':{'last_run':dict(last_run) if last_run else None,
            'scheduler_enabled':bool(cloud_run),
            'scheduled_run_verified':bool(cloud_run and (cloud.get('event')=='schedule' or cloud.get('scheduled_run_verified'))),
            'last_effective_run':(dict(last_run) if last_run and (last_run['successes'] or last_run['failures']) else cloud.get('previous_effective_run')),
            'scheduler_note':('最近一次云端运行：'+cloud['last_cloud_run']+'；触发方式：'+cloud.get('event','unknown')+'。信源成功时间单独显示。') if cloud_run else '云端定时流程已准备；尚未连接账户或验证实际定时运行。',
            'total_archived':len(items),'visible_in_export':min(len(items),config['max_public_items'])}}

def build(conn,config,sources):
    from rendering import write_release
    data=public_data(conn,config,sources)
    write_release(data)
    print(f"[build] dist/ ready: {len(data['items'])} items, {len(data['sources'])} sources")
    return data

def reprocess(conn,config,sources):
    processed=0
    rules=read_json(ROOT/'config/visibility.json',{})
    for source in sources:
        cache=ROOT/'runtime'/'cache'/source['id']/'latest.response'
        if not source.get('enabled') or source_paused(source,rules) or not cache.exists(): continue
        raw=cache.read_bytes()
        adapter={'rss':parse_feed,'crossref':parse_crossref,'html':parse_listing}[source['kind']]
        for entry in adapter(raw,source)[:config['max_entries_per_source']]:
            upsert_item(conn,entry,source,config);processed+=1
    conn.commit();log('cached_responses_reprocessed',items=processed)
    print(f'[reprocess] {processed} cached entries; source success timestamps unchanged')

def doctor(conn,config,sources):
    print('LexAtlas / Python '+sys.version.split()[0])
    print('Project: '+str(ROOT))
    print('Database integrity: '+conn.execute('PRAGMA integrity_check').fetchone()[0])
    print('Archive items: '+str(conn.execute('SELECT COUNT(*) FROM items').fetchone()[0]))
    print('Configured sources: '+str(sum(bool(s.get('enabled')) for s in sources)))
    print('Paid model calls: DISABLED (no API client in project)')
    print('Codex runtime dependency: NONE')
    print('Scheduled tasks: not installed by this program; check WorkBuddy configuration')
    print('Deployment: '+config.get('deploy',{}).get('provider','none'))
    lock=read_json(ROOT/'runtime/pipeline.lock')
    if lock: print('Lock: '+json.dumps(lock)+'; if task crashed, verify PID before removing runtime/pipeline.lock')
    for row in conn.execute('SELECT id,status,success_at,error FROM source_state ORDER BY id'):
        print(json.dumps(dict(row),ensure_ascii=False))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('collect','update'):
        cmd=commands.add_parser(name); cmd.add_argument('--force',action='store_true');cmd.add_argument('--source',action='append',default=[])
    commands.add_parser('prepare')
    cmd=commands.add_parser('apply'); cmd.add_argument('output',type=Path)
    commands.add_parser('build'); commands.add_parser('doctor'); commands.add_parser('status')
    commands.add_parser('reprocess')
    commands.add_parser('news-initial')
    cmd=commands.add_parser('cfp-refresh');cmd.add_argument('--force',action='store_true');cmd.add_argument('--limit',type=int,default=60)
    cmd=commands.add_parser('cfp-apply');cmd.add_argument('output',type=Path)
    commands.add_parser('publish'); commands.add_parser('rollback')
    cmd=commands.add_parser('serve'); cmd.add_argument('--port',type=int,default=8765); cmd.add_argument('--open',action='store_true')
    args=parser.parse_args(); config,sources=configuration()
    if args.command=='serve':
        import functools
        directory=ROOT/'dist'
        if not (directory/'index.html').exists(): raise RuntimeError('请先运行 build')
        handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(directory))
        with http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler) as server:
            print(f'Local: http://127.0.0.1:{args.port}',flush=True)
            if args.open: webbrowser.open(f'http://127.0.0.1:{args.port}')
            server.serve_forever()
        return
    if args.command in ('publish','rollback'):
        from publishing import publish,rollback
        if args.command=='publish': publish(config)
        else: rollback()
        return
    conn=database()
    try:
        if args.command in ('doctor','status'): doctor(conn,config,sources); return
        with run_lock():
            if args.command in ('cfp-refresh','update'):
                from cfp import refresh as cfp_refresh
                cfp_refresh(config,getattr(args,'force',False),getattr(args,'limit',60))
            if args.command=='cfp-apply':
                from cfp import apply_updates
                apply_updates(args.output)
            if args.command in ('collect','update'):
                selected=getattr(args,'source',[])
                if any(key not in {s['id'] for s in sources} for key in selected):raise ValueError('未知信源 ID')
                collect(conn,config,[s for s in sources if not selected or s['id'] in selected],args.force)
            if args.command=='news-initial':
                from news import import_initial
                import_initial(conn,config,sources)
            if args.command=='reprocess': reprocess(conn,config,sources)
            if args.command in ('prepare','update'): prepare(conn,config,sources)
            if args.command=='apply': apply(conn,config,sources,args.output)
            if args.command in ('build','update'): build(conn,config,sources)
    finally: conn.close()

if __name__=='__main__':
    try: main()
    except KeyboardInterrupt: print('\nStopped.',file=sys.stderr); sys.exit(130)
    except Exception as error:
        print(f'ERROR: {error}',file=sys.stderr); log('command_failed',command=sys.argv[1:],error=str(error)); sys.exit(1)

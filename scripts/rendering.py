"""Create one self-contained static release; all public exits share visibility rules."""
import datetime as dt
import email.utils
import hashlib
import html
import json
from pathlib import Path
import shutil
import uuid
import xml.etree.ElementTree as ET
from core import ROOT, UTC, atomic_write, now, write_json

CONTENT_POLICY="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://api.crossref.org; object-src 'none'; base-uri 'none'; form-action 'none'"

def x(value): return html.escape(str(value or ''),quote=True)

def security_meta():
    return f'<meta http-equiv="Content-Security-Policy" content="{x(CONTENT_POLICY)}"><meta name="referrer" content="no-referrer">'

def rss(data,items,label=None):
    root=ET.Element('rss',version='2.0'); channel=ET.SubElement(root,'channel')
    def element(parent,tag,value): ET.SubElement(parent,tag).text=str(value)
    element(channel,'title',data['site']['name']+' · '+(label or '国际法资讯'))
    element(channel,'link',data['site']['base_url'])
    element(channel,'description',data['site']['description'])
    element(channel,'language','zh-CN')
    element(channel,'lastBuildDate',email.utils.format_datetime(dt.datetime.fromisoformat(data['generated_at'])))
    sources={s['id']:s for s in data['sources']}
    for item in items[:100]:
        node=ET.SubElement(channel,'item')
        element(node,'title',item.get('title_zh') or item['title'])
        element(node,'link',item['url'])
        guid=ET.SubElement(node,'guid',isPermaLink='false'); guid.text='lexatlas:'+item['id']
        description=item.get('summary_zh') or '原始来源索引；请访问原文。'
        element(node,'description',description+' 来源：'+sources[item['source_id']]['name'])
        if item['published_at'] and item['date_precision']=='instant':
            element(node,'pubDate',email.utils.format_datetime(dt.datetime.fromisoformat(item['published_at'])))
        source=sources[item['source_id']]
        ET.SubElement(node,'source',url=source.get('feed_url') or source['homepage']).text=source['name']
    return ET.tostring(root,encoding='unicode',xml_declaration=True)

def ics_escape(value):
    return str(value or '').replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')

def fold_line(line):
    # RFC 5545 folds by UTF-8 octets, without splitting a multi-byte character.
    result=[]; current=''; size=0
    for char in line:
        n=len(char.encode('utf-8'))
        if size+n>73:
            result.append(current); current=' '+char; size=1+n
        else: current+=char; size+=n
    result.append(current)
    return '\r\n'.join(result)

def calendar(data):
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Lexpacis//Academic Calendar//ZH','CALSCALE:GREGORIAN','METHOD:PUBLISH','X-WR-CALNAME:'+ics_escape(data['site']['name']+'·学术日历')]
    stamp=dt.datetime.fromisoformat(data['generated_at']).astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')
    for item in data['items']:
        for key in ('event','deadline'):
            value=item.get(key)
            if not value: continue
            date=dt.date.fromisoformat(value['date'])
            label='截止' if key=='deadline' else '活动'
            # Stable UID + LAST-MODIFIED; day-only values are never invented time instants.
            modified=dt.datetime.fromisoformat(item['ai']['processed_at']).astimezone(UTC).strftime('%Y%m%dT%H%M%SZ')
            lines+=['BEGIN:VEVENT','UID:'+item['id']+'-'+key+'@lexatlas',
                    'DTSTAMP:'+stamp,'LAST-MODIFIED:'+modified,
                    'DTSTART;VALUE=DATE:'+date.strftime('%Y%m%d'),
                    'DTEND;VALUE=DATE:'+(date+dt.timedelta(days=1)).strftime('%Y%m%d'),
                    'SUMMARY:'+ics_escape('['+label+'] '+(item.get('title_zh') or item['title'])),
                    'URL:'+ics_escape(item['url']),
                    'DESCRIPTION:'+ics_escape(value['label']+'；原文日期：'+value['date_text']+'。日期来自公开公告，请以原文为准。'),
                    'END:VEVENT']
    lines+=['END:VCALENDAR']
    return '\r\n'.join(fold_line(line) for line in lines)+'\r\n'

def detail_page(data,item):
    source=next(s for s in data['sources'] if s['id']==item['source_id'])
    module=next(m['name'] for m in data['modules'] if m['id']==item['module'])
    title=item.get('title_zh') or item['title']
    description=item.get('summary_zh') or '国际法学术资料索引。保留原始标题与出处，请访问原文获取完整内容。'
    basis='AI 自动整理 · 基于'+item['evidence_basis'] if item.get('ai') else '来源元数据 · 尚无 AI 摘要'
    topics=' / '.join(t['name'] for t in data['topics'] if t['id'] in item['topics']) or '综合国际法'
    authors='、'.join(item['authors']) or '原文未提供作者'
    canonical=data['site']['base_url'].rstrip('/')+'/items/'+item['id']+'.html'
    name=x(data['site']['name']);english=x(data['site']['english_name']);mark=x((data['site']['english_name'] or data['site']['name'])[0])
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">{security_meta()}<meta name="viewport" content="width=device-width,initial-scale=1"><title>{x(title)} — {name}</title><meta name="description" content="{x(description[:160])}"><link rel="canonical" href="{x(canonical)}"><link rel="stylesheet" href="../styles.css"><link rel="icon" href="../favicon.svg"></head><body class="detail-document"><header class="document-header"><a class="brand" href="../index.html"><span class="brand-mark">{mark}<span>↗</span></span><span>{name}<small>{english}</small></span></a><a class="back-link" href="../index.html#/{item['module']}">← 返回{module}</a></header><main class="document-main"><div class="eyebrow">{x(module)} / {x(source['name'])}</div><h1>{x(title)}</h1>{f'<p class="original-title">{x(item["title"])}</p>' if item.get('title_zh') else ''}<div class="document-meta">{x(item['published_at'] or '原始发布日期未知')} · {x(authors)}</div><p class="basis-badge">{x(basis)}</p><p class="document-summary">{x(description)}</p><dl class="facts"><dt>专题</dt><dd>{x(topics)}</dd><dt>原始机构</dt><dd>{x(source['organization'])}</dd><dt>首次发现</dt><dd>{x(item['discovered_at'])}</dd><dt>资料依据</dt><dd>{x(item['evidence_basis'])}；本平台未核验全文</dd><dt>DOI</dt><dd>{x(item['doi'] or '未提供')}</dd></dl><div class="detail-actions"><a class="primary-button" href="{x(item['url'])}" target="_blank" rel="noopener noreferrer">访问原始来源 ↗</a><a class="secondary-button" href="../index.html#/cite?item={item['id']}">生成引注 ↗</a></div><p class="fine-print">学术索引与自动整理内容，不代表原机构立场。实质法律判断请核查原始文件和上下文。</p></main><footer class="document-footer">{name} · {x(data['site']['tagline'])}</footer></body></html>'''

def safe_remove_release(path):
    path=Path(path).resolve()
    if path.parent!=ROOT.resolve() or (path.name not in ('dist','dist.previous') and not path.name.startswith('.dist-stage-')):
        raise ValueError('拒绝清理项目发布目录之外的路径')
    if path.exists(): shutil.rmtree(path)

def write_release(data):
    stage=ROOT/('.dist-stage-'+uuid.uuid4().hex[:8]); stage.mkdir()
    try:
        for path in (ROOT/'web').iterdir():
            if path.is_symlink():raise ValueError('网页资产不得使用符号链接')
            if path.is_dir():shutil.copytree(path,stage/path.name)
            elif path.is_file():shutil.copyfile(path,stage/path.name)
        replacements={'SITE_NAME':data['site']['name'],'ENGLISH_NAME':data['site']['english_name'],'TAGLINE':data['site']['tagline'],'DESCRIPTION':data['site']['description'],'BRAND_MARK':(data['site']['english_name'] or data['site']['name'])[0]}
        for html_file in stage.glob('*.html'):
            template=html_file.read_text(encoding='utf-8')
            for key,value in replacements.items():template=template.replace('{{'+key+'}}',x(value))
            # Pages serves static files without applying _headers.
            template=template.replace('<head>','<head>'+security_meta(),1)
            atomic_write(html_file,template)
        atomic_write(stage/'favicon.svg','<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="13" fill="#243b43"/><text x="32" y="46" text-anchor="middle" font-size="42" fill="#f7f4ec" font-family="Georgia,serif">'+x(replacements['BRAND_MARK'])+'</text></svg>')
        # A JS data file also supports offline file:// previews without fetch/CORS.
        serialized=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
        atomic_write(stage/'data.js','window.LEXATLAS_DATA = '+serialized+';\n')
        write_json(stage/'data.json',data)
        (stage/'api').mkdir(); (stage/'items').mkdir(); (stage/'feeds').mkdir()
        write_json(stage/'api/items.json',data['items'])
        write_json(stage/'api/sources.json',data['sources'])
        write_json(stage/'api/status.json',{'generated_at':data['generated_at'],**data['operations']})
        write_json(stage/'api/cfp.json',data.get('cfp',{}))
        write_json(stage/'api/journals.json',data.get('cfp',{}).get('journals',[]))
        atomic_write(stage/'feed.xml',rss(data,data['items']))
        for topic in data['topics']:
            atomic_write(stage/'feeds'/(topic['id']+'.xml'),rss(data,[i for i in data['items'] if topic['id'] in i['topics']],topic['name']))
        (stage/'feeds/modules').mkdir()
        for module in data['modules']:
            atomic_write(stage/'feeds/modules'/(module['id']+'.xml'),rss(data,[i for i in data['items'] if i['module']==module['id']],module['name']))
        atomic_write(stage/'calendar.ics',calendar(data))
        cfp_items=[]
        for call in data.get('cfp',{}).get('calls',[]):
            if not call.get('deadline'):continue
            cfp_items.append({'id':call['id'],'title':call['title'],'title_zh':call['title'],'url':call['url'],
                              'deadline':{'date':call['deadline'],'date_text':call['deadline_text'],'label':call['deadline_label']},'event':None,'ai':{'processed_at':data['generated_at']}})
        atomic_write(stage/'cfp.ics',calendar({**data,'items':cfp_items}))
        for item in data['items']: atomic_write(stage/'items'/(item['id']+'.html'),detail_page(data,item))
        base=data['site']['base_url'].rstrip('/')
        atomic_write(stage/'robots.txt','User-agent: *\nAllow: /\nSitemap: '+base+'/sitemap.xml\n')
        sitemap=ET.Element('urlset',xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
        for link in [base+'/']+[base+'/items/'+i['id']+'.html' for i in data['items']]:
            ET.SubElement(ET.SubElement(sitemap,'url'),'loc').text=link
        atomic_write(stage/'sitemap.xml',ET.tostring(sitemap,encoding='unicode',xml_declaration=True))
        atomic_write(stage/'_headers',"/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n  Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()\n  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://api.crossref.org; object-src 'none'; base-uri 'self'; frame-ancestors 'self'\n/data.js\n  Cache-Control: no-cache\n/data.json\n  Cache-Control: no-cache\n")
        hashes={str(p.relative_to(stage)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in stage.rglob('*') if p.is_file()}
        write_json(stage/'release.json',{'version':1,'built_at':now(),'item_count':len(data['items']),'files':hashes})
        # Validate all generated public URLs and data shape before switching releases.
        if not (stage/'index.html').exists(): raise ValueError('发布包缺少首页')
        current=ROOT/'dist'; previous=ROOT/'dist.previous'
        safe_remove_release(previous)
        if current.exists(): current.rename(previous)
        try: stage.rename(current)
        except Exception:
            if previous.exists() and not current.exists(): previous.rename(current)
            raise
    finally:
        if stage.exists(): safe_remove_release(stage)

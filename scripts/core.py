"""Standard-library-only ingestion and persistent storage. No model/API calls."""
from __future__ import annotations
import contextlib
import datetime as dt
import email.utils
import hashlib
import html
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc

def now():
    return dt.datetime.now(UTC).isoformat(timespec='seconds')

def read_json(path, default=None):
    return json.loads(Path(path).read_text(encoding='utf-8-sig')) if Path(path).exists() else default

def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def write_json(path, data):
    atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2)+'\n')

def log(event, **data):
    folder = ROOT/'runtime'/'logs'
    folder.mkdir(parents=True, exist_ok=True)
    record = {'at':now(), 'event':event, **data}
    with (folder/(now()[:10]+'.jsonl')).open('a', encoding='utf-8') as out:
        out.write(json.dumps(record, ensure_ascii=False)+'\n')

class TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.ignore = 0
    def handle_starttag(self, tag, attrs):
        if tag in ('script','style'): self.ignore += 1
        elif tag in ('p','br','li','div','h1','h2','h3'): self.text.append(' ')
    def handle_endtag(self, tag):
        if tag in ('script','style'): self.ignore = max(0,self.ignore-1)
        elif tag in ('p','li','div'): self.text.append(' ')
    def handle_data(self, data):
        if not self.ignore: self.text.append(data)

def plain(value):
    parser = TextParser()
    parser.feed(str(value or ''))
    return re.sub(r'\s+', ' ', ''.join(parser.text)).strip()

def safe_url(value, base=''):
    value = html.unescape(str(value or '').strip())
    result = urllib.parse.urlsplit(urllib.parse.urljoin(base, value))
    if result.scheme not in ('https','http') or not result.hostname or result.username or result.password:
        return ''
    return urllib.parse.urlunsplit((result.scheme,result.netloc,result.path,result.query,''))

def canonical_url(url):
    parts = urllib.parse.urlsplit(safe_url(url))
    query = [(k,v) for k,v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in ('fbclid','gclid')]
    return urllib.parse.urlunsplit((parts.scheme.lower(),parts.netloc.lower(),parts.path.rstrip('/') or '/',urllib.parse.urlencode(sorted(query)),''))

def identity(url, doi=''):
    doi = re.sub(r'^https?://(?:dx\.)?doi\.org/', '', doi.strip(), flags=re.I).lower()
    key = 'doi:'+doi if doi else canonical_url(url)
    return hashlib.sha256(key.encode()).hexdigest()[:20]

def fingerprint(title, evidence, date, authors, extra=None):
    return hashlib.sha256(json.dumps([title,evidence,date,authors,extra], ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def parse_date(value):
    value = str(value or '').strip()
    if not value: return None, 'unknown'
    if re.fullmatch(r'\d{4}', value): return value, 'year'
    if re.fullmatch(r'\d{4}-\d{2}', value):
        try: dt.date.fromisoformat(value+'-01'); return value,'month'
        except ValueError: return None,'unknown'
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        try: dt.date.fromisoformat(value); return value,'day'
        except ValueError: return None,'unknown'
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:
        try: parsed = email.utils.parsedate_to_datetime(value)
        except (ValueError,TypeError):
            for fmt in ('%d %B %Y','%B %d, %Y','%d %b %Y','%B %d %Y','%Y年%m月%d日'):
                try: return dt.datetime.strptime(value,fmt).date().isoformat(),'day'
                except ValueError: pass
            return None,'unknown'
    if parsed.tzinfo is None:
        return parsed.date().isoformat(),'day'
    return parsed.astimezone(UTC).isoformat(timespec='seconds'),'instant'

def date_from_parts(parts):
    if not parts: return None,'unknown'
    raw = '-'.join([str(parts[0])] + [f'{int(x):02}' for x in parts[1:3]])
    return parse_date(raw)

def classify(title, source, config):
    text = title.lower()
    module = source['module']
    if module!='news' and re.search(r'call for (?:papers|abstracts)|webinar|workshop|research forum|summer school|events and announcements|upcoming conference|conference announcement|征稿|研讨会|学术会议',text):
        module='events'
    if source['id']=='pca' and not re.search(r'case no|arbitrat(?:ion|ral) proceedings|award|conciliation|hearing|v\.',text):
        module='official'
    if source['id']=='icj' and not re.search(r'case|proceedings|judgment|advisory opinion|application|hearings|v\.',text):
        module='official'
    topics = list(source.get('topics',[]))
    for topic in config['topics']:
        if any(word.lower() in text for word in topic['keywords']) and topic['id'] not in topics:
            topics.append(topic['id'])
    return module,topics

def child_text(node, names):
    for element in node:
        if element.tag.split('}')[-1] in names:
            return ''.join(element.itertext()).strip()
    return ''

def parse_feed(data, source):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('不接受含 DTD / ENTITY 的订阅文件')
    root = ET.fromstring(data.lstrip(b'\xef\xbb\xbf \r\n\t'))
    entries = [n for n in root.iter() if n.tag.split('}')[-1] in ('item','entry')]
    result=[]
    for item in entries:
        title=plain(child_text(item,('title',)))
        url=child_text(item,('link',))
        for child in item:
            if child.tag.split('}')[-1]=='link' and child.attrib.get('rel','alternate')=='alternate' and child.attrib.get('href'):
                url=child.attrib['href']; break
        url=safe_url(url,source['homepage'])
        if not title or not url: continue
        date,precision=parse_date(child_text(item,('pubDate','published','date','updated')))
        author=plain(child_text(item,('creator','author')))
        excerpt=plain(child_text(item,('description','summary','encoded','content')))[:4500]
        if source.get('excerpt_policy')=='title_only' or re.fullmatch(r'The post .+ appeared first on .+\.?',excerpt):
            excerpt=''
        result.append({'title':title,'url':url,'published_at':date,'date_precision':precision,
                       'authors':[author] if author else [],'evidence':excerpt,'evidence_basis':'RSS 摘录' if excerpt else 'RSS 标题', 'doi':''})
    counts={}
    for item in result:
        if item['evidence']: counts[item['evidence']]=counts.get(item['evidence'],0)+1
    for item in result:
        if counts.get(item['evidence'],0)>=3:
            item['evidence']='';item['evidence_basis']='RSS 标题'
    return result

def parse_crossref(data, source):
    message=json.loads(data).get('message',{})
    if not isinstance(message,dict) or not isinstance(message.get('items'),list):
        raise ValueError('Crossref 响应缺少 message.items')
    result=[]
    for item in message['items']:
        title=plain((item.get('title') or [''])[0])
        doi=item.get('DOI','').lower()
        url=safe_url('https://doi.org/'+doi) if doi else safe_url(item.get('URL',''))
        if not title or not url: continue
        date,precision=None,'unknown'
        for key in ('published','published-online','published-print','issued'):
            parts=item.get(key,{}).get('date-parts',[[]])[0]
            if parts:
                date,precision=date_from_parts(parts); break
        authors=[' '.join(filter(None,[a.get('given'),a.get('family')])) or a.get('name','') for a in item.get('author',[])]
        result.append({'title':title,'url':url,'doi':doi,'published_at':date,'date_precision':precision,
                       'authors':[a for a in authors if a], 'evidence':'', 'evidence_basis':'书目元数据',
                       'bibliography':{k:item.get(k) for k in ('container-title','volume','issue','page','type','publisher')}})
    return result

class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links=[]; self.anchor=None; self.recent=''; self.time_depth=0
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='a' and attrs.get('href'):
            self.anchor={'href':attrs['href'],'parts':[], 'context':self.recent[-220:]}
        if tag=='time' and attrs.get('datetime'):
            self.recent+=' '+attrs['datetime']+' '
    def handle_data(self,data):
        self.recent=(self.recent+' '+data)[-1000:]
        if self.anchor is not None: self.anchor['parts'].append(data)
    def handle_endtag(self,tag):
        if tag=='a' and self.anchor is not None:
            self.anchor['title']=plain(' '.join(self.anchor.pop('parts')))
            self.links.append(self.anchor); self.anchor=None

def parse_listing(data, source):
    if source.get('adapter')=='icj':
        return parse_icj(data,source)
    if source.get('adapter')=='un_geneva_news':
        return parse_news_listing(data,source)
    parser=LinkParser(); parser.feed(data.decode('utf-8',errors='replace'))
    result=[]; seen=set()
    pattern=re.compile(source['link_pattern'])
    for link in parser.links:
        url=safe_url(link['href'],source['url']); title=link['title']
        if not url or not pattern.search(urllib.parse.urlsplit(url).path) or len(title)<35 or url in seen: continue
        if re.search(r'privacy|cookies|read more|next page',title,re.I): continue
        seen.add(url)
        found=re.findall(r'\b(?:\d{1,2}\s+[A-Z][a-z]+\s+20\d{2}|20\d{2}-\d{2}-\d{2})\b',link['context'])
        date,precision=parse_date(found[-1] if found else '')
        result.append({'title':title,'url':url,'published_at':date,'date_precision':precision,
                       'authors':[],'evidence':'','evidence_basis':'官方目录标题','doi':''})
    return result

def parse_news_listing(data,source):
    """Use isolated article cards for dates; otherwise retain undated title/link metadata."""
    markup=data.decode('utf-8',errors='replace')
    pattern=re.compile(r'/en/news-media/news/\d{4}/\d{2}/\d+/[^/?#]+')
    # Drupal uses an outer article and separate image articles inside each news row.
    # Splitting on article tags alone stops the first record at its image.
    rows=re.split(r'<div\b[^>]*\bclass=["\'][^"\']*\bviews-row\b[^"\']*["\'][^>]*>',markup,flags=re.I)[1:]
    cards=rows or re.findall(r'<article\b[^>]*>(.*?)</article>',markup,re.S|re.I)
    blocks=cards or [markup]
    entries=[];seen=set()
    for block in blocks:
        parser=LinkParser();parser.feed(block)
        matching={}
        for link in parser.links:
            url=safe_url(link['href'],source['url'])
            target=urllib.parse.urlsplit(url)
            if target.hostname==urllib.parse.urlsplit(source['url']).hostname and pattern.fullmatch(target.path) and len(link['title'])>25:
                matching.setdefault(url,link['title'])
        for url,title in matching.items():
            if url in seen:continue
            seen.add(url)
            date,precision=None,'unknown'
            # A page-wide date must never be attached to every headline.
            if cards and len(matching)==1:
                values=re.findall(r'<time\b[^>]*>(.*?)</time>',block,re.S|re.I)
                parsed=[parse_date(plain(value)) for value in values]
                distinct={(d,p) for d,p in parsed if d}
                if len(distinct)==1:date,precision=distinct.pop()
            entries.append({'title':title,'url':url,'published_at':date,'date_precision':precision,
                            'authors':[],'doi':'','evidence':'','evidence_basis':'官方新闻目录元数据'})
    return entries

def parse_icj(data,source):
    markup=data.decode('utf-8',errors='replace')
    blocks=re.split(r'<div\b[^>]*class="[^"]*\bviews-row\b[^"]*"[^>]*>',markup)[1:]
    result=[]; seen=set()
    for block in blocks:
        match=re.search(r'views-field-field-document-long-title.*?<p>(.*?)</p>',block,re.S)
        if not match: continue
        title=plain(match.group(1))
        parsed=LinkParser(); parsed.feed(block)
        candidates=[safe_url(a['href'],source['url']) for a in parsed.links
                    if re.search(r'/(?:press-releases|case-related)/.*-en\.pdf$',a['href'],re.I)]
        if not candidates or candidates[0] in seen: continue
        url=candidates[0]; seen.add(url)
        time=re.search(r'<time\b[^>]*>(.*?)</time>',block,re.S)
        date,precision=parse_date(plain(time.group(1)) if time else '')
        result.append({'title':title,'url':url,'published_at':date,'date_precision':precision,
                       'authors':[],'evidence':'','evidence_basis':'官方目录标题','doi':''})
    return result

def database(root=ROOT):
    folder=Path(root)/'runtime'; folder.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(folder/'lexatlas.sqlite3',timeout=15)
    conn.row_factory=sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
      CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
        doi TEXT, module TEXT, topics TEXT, authors TEXT, published_at TEXT, date_precision TEXT,
        discovered_at TEXT, updated_at TEXT, content_hash TEXT, evidence TEXT, evidence_basis TEXT,
        bibliography TEXT, visibility TEXT DEFAULT 'public');
      CREATE TABLE IF NOT EXISTS provenance (
        item_id TEXT, source_id TEXT, url TEXT, seen_at TEXT,
        PRIMARY KEY(item_id,source_id));
      CREATE TABLE IF NOT EXISTS source_state (
        id TEXT PRIMARY KEY, attempted_at TEXT, success_at TEXT, status TEXT, error TEXT,
        etag TEXT, last_modified TEXT, item_count INTEGER DEFAULT 0, failures INTEGER DEFAULT 0,
        next_attempt_at TEXT);
      CREATE TABLE IF NOT EXISTS enrichments (
        item_id TEXT PRIMARY KEY, content_hash TEXT, payload TEXT, model TEXT, created_at TEXT);
      CREATE TABLE IF NOT EXISTS attempts (
        item_id TEXT, batch_id TEXT, attempted_at TEXT, status TEXT, reason TEXT);
      CREATE TABLE IF NOT EXISTS batches (
        id TEXT PRIMARY KEY, created_at TEXT, status TEXT, path TEXT);
      CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, successes INTEGER,
        failures INTEGER, added INTEGER, changed INTEGER);
    ''')
    return conn

def upsert_item(conn, entry, source, config):
    key=identity(entry['url'],entry.get('doi',''))
    authors=entry.get('authors',[])
    content_hash=fingerprint(entry['title'],entry.get('evidence',''),entry.get('published_at'),authors,
                             [entry.get('evidence_basis'),entry.get('bibliography',{})])
    existing=conn.execute('SELECT * FROM items WHERE id=?',(key,)).fetchone()
    conn.execute('INSERT OR REPLACE INTO provenance VALUES(?,?,?,?)',(key,source['id'],entry['url'],now()))
    # Preserve an already selected primary source; record additional index provenance.
    if existing and existing['source_id']!=source['id']:
        return 'unchanged'
    if existing and existing['content_hash']==content_hash:
        # Rules may improve independently of upstream content; preserve fresh AI overrides.
        module,topics=classify(entry['title'],source,config)
        conn.execute('UPDATE items SET module=?,topics=? WHERE id=?',(module,json.dumps(topics),key))
        return 'unchanged'
    module,topics=classify(entry['title'],source,config)
    values=(key,source['id'],entry['title'],entry['url'],entry.get('doi',''),module,json.dumps(topics),
            json.dumps(authors,ensure_ascii=False),entry.get('published_at'),entry.get('date_precision','unknown'),
            existing['discovered_at'] if existing else now(),now(),content_hash,entry.get('evidence',''),
            entry.get('evidence_basis','标题'),json.dumps(entry.get('bibliography',{}),ensure_ascii=False),
            existing['visibility'] if existing else 'public')
    conn.execute('INSERT OR REPLACE INTO items VALUES('+','.join('?'*17)+')',values)
    return 'changed' if existing else 'added'

def http_fetch(source, config, state=None):
    from network_policy import validate_public_url, RestrictedRedirect
    hosts={urllib.parse.urlsplit(source['url']).hostname.lower(),*source.get('allowed_redirect_hosts',[])}
    validate_public_url(source['url'],hosts)
    headers={'User-Agent':config['user_agent'],'Accept':'application/rss+xml, application/atom+xml, application/json, text/html;q=0.8, */*;q=0.5'}
    if state:
        if state['etag']: headers['If-None-Match']=state['etag']
        if state['last_modified']: headers['If-Modified-Since']=state['last_modified']
    request=urllib.request.Request(source['url'],headers=headers)
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),RestrictedRedirect(hosts))
        with opener.open(request,timeout=config['fetch_timeout_seconds']) as response:
            if not safe_url(response.url): raise ValueError('不支持的重定向地址')
            data=response.read(config['max_fetch_bytes']+1)
            if len(data)>config['max_fetch_bytes']: raise ValueError('信源响应超过大小限制')
            return data, response.headers
    except urllib.error.HTTPError as error:
        if error.code==304: return None,error.headers
        raise

@contextlib.contextmanager
def run_lock():
    path=ROOT/'runtime'/'pipeline.lock'; path.parent.mkdir(parents=True,exist_ok=True)
    try:
        fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:
        raise RuntimeError('另一个更新任务正在运行；请勿并行执行。异常退出时先运行 doctor 检查锁。')
    try:
        with os.fdopen(fd,'w') as stream: json.dump({'pid':os.getpid(),'created_at':now()},stream)
        yield
    finally:
        path.unlink(missing_ok=True)

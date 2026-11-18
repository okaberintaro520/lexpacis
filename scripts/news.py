"""One-time verified directory import. No network calls and no invented fetch success."""
import json
import urllib.parse
from core import ROOT, identity, log, now, parse_date, read_json, safe_url, upsert_item

def import_initial(conn,config,sources):
    from pipeline import validate_enrichment
    document=read_json(ROOT/'config/news-initial.json',{})
    if document.get('checked_method')!='official_listing_read':raise ValueError('首次导入缺少目录核对说明')
    listing=safe_url(document.get('listing_url',''))
    if not listing or urllib.parse.urlsplit(listing).hostname!='www.ungeneva.org':raise ValueError('未知新闻目录')
    indexed={s['id']:s for s in sources};added=0;translated=0
    for row in document.get('items',[]):
        source=indexed.get(row.get('source_id'))
        if not source or source['module']!='news':raise ValueError('条目未对应已登记新闻源')
        url=safe_url(row.get('url',''))
        if not url or urllib.parse.urlsplit(url).hostname!=urllib.parse.urlsplit(listing).hostname:raise ValueError('新闻链接不在已核对目录主机')
        date,precision=parse_date(row.get('published_at'))
        if precision!='day':raise ValueError('首次导入必须保留明确的目录日期')
        entry={'title':row['title'],'url':url,'published_at':date,'date_precision':precision,'authors':[],
               'doi':'','evidence':'','evidence_basis':'官方新闻目录元数据（首次核对）'}
        if upsert_item(conn,entry,source,config)=='added':added+=1
        key=identity(url);item=conn.execute('SELECT * FROM items WHERE id=?',(key,)).fetchone()
        previous=conn.execute('SELECT content_hash FROM enrichments WHERE item_id=?',(key,)).fetchone()
        if previous and previous['content_hash']==item['content_hash']:continue
        output={'id':key,'content_hash':item['content_hash'],'title_zh':row['title_zh'],'summary_zh':'','module':'news',
                'topics':row.get('topics',[]),'evidence_quotes':[],'event':None,'deadline':None}
        request={'id':key,'content_hash':item['content_hash'],'title':row['title'],'module':'news','source_excerpt':'',
                 'authority':source['authority'],'evidence_basis':entry['evidence_basis']}
        valid=validate_enrichment(output,request,config)
        conn.execute('INSERT OR REPLACE INTO enrichments VALUES(?,?,?,?,?)',(key,item['content_hash'],json.dumps(valid,ensure_ascii=False),'Codex（首次新闻目录译名）',now()))
        translated+=1
    conn.commit();report={'added':added,'translated_titles':translated,'listing_checked_at':document['checked_at'],'fetch_success_recorded':False}
    log('news_directory_imported',**report);print(json.dumps(report,ensure_ascii=False));return report

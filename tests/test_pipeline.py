import copy
import datetime as dt
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import core
import pipeline
import rendering
import publishing
import cfp

ROOT=Path(__file__).resolve().parents[1]
CONFIG=core.read_json(ROOT/'config/site.json')
SOURCES=core.read_json(ROOT/'config/sources.json')
SOURCE=next(s for s in SOURCES if s['id']=='esil')

class ParserTests(unittest.TestCase):
    def test_rss_leading_blank_and_entities(self):
        xml=b'\n\n<?xml version="1.0"?><rss><channel><item><title>Climate &amp; Law</title><link>https://example.org/a</link><pubDate>Wed, 18 Nov 2026 12:00:00 GMT</pubDate><description>&lt;p&gt;A meeting.&lt;/p&gt;</description></item></channel></rss>'
        item=core.parse_feed(xml,{**SOURCE,'excerpt_policy':'use_excerpt'})[0]
        self.assertEqual(item['title'],'Climate & Law')
        self.assertEqual(item['evidence'],'A meeting.')
        self.assertEqual(item['date_precision'],'instant')
    def test_atom_and_unsafe_link(self):
        xml=b'<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Research</title><link href="https://example.org/p"/><updated>2026-11-18</updated></entry><entry><title>Bad</title><link href="javascript:alert(1)"/></entry></feed>'
        items=core.parse_feed(xml,SOURCE)
        self.assertEqual(len(items),1)
        self.assertEqual(items[0]['url'],'https://example.org/p')
    def test_dtd_rejected(self):
        with self.assertRaises(ValueError):core.parse_feed(b'<!DOCTYPE rss [<!ENTITY a "boom">]><rss/>',SOURCE)
    def test_repeated_template_is_not_evidence(self):
        xml='<rss><channel>'+''.join(f'<item><title>Event {i}</title><link>https://example.org/{i}</link><description>Deadline for submissions: 30 January 2025</description></item>' for i in range(3))+'</channel></rss>'
        parsed=core.parse_feed(xml.encode(),{**SOURCE,'excerpt_policy':'use_excerpt'})
        self.assertTrue(all(not i['evidence'] and i['evidence_basis']=='RSS 标题' for i in parsed))
    def test_crossref_precision(self):
        raw={'message':{'items':[{'title':['A paper'],'DOI':'10.1234/test','published':{'date-parts':[[2026,11]]},'author':[{'given':'A','family':'Scholar'}]}]}}
        item=core.parse_crossref(json.dumps(raw).encode(),SOURCE)[0]
        self.assertEqual((item['published_at'],item['date_precision']),('2026-11','month'))
        self.assertEqual(item['authors'],['A Scholar'])
        self.assertEqual(item['evidence'],'')
    def test_doi_dedupe_and_tracking(self):
        self.assertEqual(core.identity('https://a.org/x','10.12/Abc'),core.identity('https://b.org/x','https://doi.org/10.12/abc'))
        self.assertEqual(core.identity('https://a.org/x?utm_source=y'),core.identity('https://a.org/x'))
    def test_dates_do_not_invent_precision(self):
        self.assertEqual(core.parse_date('2026'),('2026','year'))
        self.assertEqual(core.parse_date('2026-02-31'),(None,'unknown'))
        self.assertEqual(core.parse_date('19 November 2026'),('2026-11-19','day'))
    def test_online_symposium_is_not_an_event(self):
        source=next(s for s in SOURCES if s['id']=='opiniojuris')
        self.assertEqual(core.classify('6th Annual Symposium on Pop Culture: Closing Remarks',source,CONFIG)[0],'commentary')
        self.assertEqual(core.classify('Events and Announcements: 15 November 2026',source,CONFIG)[0],'events')
    def test_icj_press_release_fields(self):
        raw=b'<div class="views-row"><div class="views-field-field-document-long-title"><p>Application before the Court</p></div><time datetime="2026-11-03T12:00:00Z">3 November 2026</time><a href="/sites/default/files/case-related/178/test-en.pdf">English</a></div>'
        item=core.parse_icj(raw,next(s for s in SOURCES if s['id']=='icj'))[0]
        self.assertEqual(item['title'],'Application before the Court')
        self.assertEqual((item['published_at'],item['date_precision']),('2026-11-03','day'))

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.item={'id':'one','content_hash':'hash','title':'Conference on climate law','source_excerpt':'The conference takes place on 3 December 2026. Submit by 19 November 2026.',
                   'module':'events','authority':'academic_society','evidence_basis':'RSS 摘录'}
        self.output={'id':'one','content_hash':'hash','title_zh':'气候法学术会议','summary_zh':'公告提供了气候法会议与投稿安排。','topics':['ocean-climate'],'module':'events',
                     'evidence_quotes':['The conference takes place on 3 December 2026.'],
                     'event':{'date':'2026-12-03','date_text':'3 December 2026','label':'会议'},'deadline':None}
    def test_valid_output(self):
        self.assertEqual(pipeline.validate_enrichment(self.output,self.item,CONFIG)['event']['date'],'2026-12-03')
    def test_stale_evidence_rejected(self):
        self.output['content_hash']='old'
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)
    def test_invented_quote_rejected(self):
        self.output['evidence_quotes']=['not actually present']
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)
    def test_metadata_cannot_generate_abstract(self):
        self.item['evidence_basis']='书目元数据'
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)
    def test_empty_excerpt_cannot_generate_summary(self):
        self.item['source_excerpt']=''
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)
    def test_date_must_match_quote(self):
        self.output['event']['date']='2026-12-04'
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)
    def test_commentary_cannot_become_official(self):
        self.output['module']='official'
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)
    def test_unknown_fields_and_html_rejected(self):
        self.output['command']='rm -rf /'
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)
        self.output.pop('command'); self.output['title_zh']='<script>alert(1)</script>'
        with self.assertRaises(ValueError):pipeline.validate_enrichment(self.output,self.item,CONFIG)

class PersistentWorkflowTests(unittest.TestCase):
    def setUp(self):
        test_area=ROOT/'runtime'/'test-temp';test_area.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='lexatlas-test-',dir=test_area);self.root=Path(self.temp.name)
        self.patches=[patch.object(module,'ROOT',self.root) for module in (core,pipeline,rendering,publishing,cfp)]
        for p in self.patches:p.start()
        (self.root/'config').mkdir();shutil.copytree(ROOT/'web',self.root/'web')
        core.write_json(self.root/'config/enrichment.schema.json',core.read_json(ROOT/'config/enrichment.schema.json'))
        core.write_json(self.root/'config/visibility.json',{'hidden_items':[],'hidden_sources':[]})
        self.conn=core.database(self.root)
        self.entry={'title':'Conference on climate law','url':'https://example.org/meeting','doi':'','authors':['A Scholar'],'published_at':'2026-11-18','date_precision':'day',
                    'evidence':'The conference takes place on 3 December 2026.','evidence_basis':'RSS 摘录'}
        core.upsert_item(self.conn,self.entry,SOURCE,CONFIG);self.conn.commit()
    def tearDown(self):
        self.conn.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def prepare_response(self):
        path=pipeline.prepare(self.conn,CONFIG,SOURCES);request=core.read_json(path);item=request['items'][0]
        return path,{'batch_id':request['batch_id'],'model':'test-fixture-not-production','items':[{'id':item['id'],'content_hash':item['content_hash'],'title_zh':'气候法会议','summary_zh':'公告列出会议日期。','topics':['ocean-climate'],'module':'events','evidence_quotes':['The conference takes place on 3 December 2026.'],'event':{'date':'2026-12-03','date_text':'3 December 2026','label':'会议'},'deadline':None}]}
    def test_collect_idempotency(self):
        self.assertEqual(core.upsert_item(self.conn,self.entry,SOURCE,CONFIG),'unchanged')
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],1)
    def test_prepare_paths_portable_and_reused(self):
        path,_=self.prepare_response()
        self.assertEqual(path,pipeline.prepare(self.conn,CONFIG,SOURCES))
        row=self.conn.execute('SELECT path FROM batches').fetchone()
        self.assertFalse(Path(row['path']).is_absolute())
    def test_apply_and_calendar_privacy(self):
        path,response=self.prepare_response();out=path.parent/'output.json';core.write_json(out,response)
        self.assertEqual(pipeline.apply(self.conn,CONFIG,SOURCES,out)['accepted'],1)
        data=pipeline.public_data(self.conn,CONFIG,SOURCES)
        encoded=json.dumps(data,ensure_ascii=False)
        self.assertNotIn('The conference takes place',encoded)
        self.assertNotIn('evidence_quotes',encoded)
        text=rendering.calendar(data)
        self.assertIn('DTSTART;VALUE=DATE:20261203',text)
        self.assertIn('DTEND;VALUE=DATE:20261204',text)
        self.assertIn('UID:'+data['items'][0]['id']+'-event@lexatlas',text)
        self.assertTrue(all(len(line.encode('utf-8'))<=75 for line in text.split('\r\n')))
    def test_partial_batch_preserves_accepted_items(self):
        other=copy.deepcopy(self.entry);other['url']='https://example.org/another-meeting'
        core.upsert_item(self.conn,other,SOURCE,CONFIG);self.conn.commit()
        path,response=self.prepare_response();request=core.read_json(path)
        bad=copy.deepcopy(response['items'][0]);bad['id']=request['items'][1]['id'];bad['content_hash']=request['items'][1]['content_hash'];bad['evidence_quotes']=['This quotation was invented.']
        response['items'].append(bad);out=path.parent/'output.json';core.write_json(out,response)
        report=pipeline.apply(self.conn,CONFIG,SOURCES,out)
        self.assertEqual((report['accepted'],len(report['rejected']),report['remaining']),(1,1,1))
        self.assertEqual(report['remaining_ids'],[bad['id']])
    def test_source_change_invalidates_summary(self):
        path,response=self.prepare_response();out=path.parent/'output.json';core.write_json(out,response);pipeline.apply(self.conn,CONFIG,SOURCES,out)
        self.entry['evidence']='A changed announcement.';core.upsert_item(self.conn,self.entry,SOURCE,CONFIG);self.conn.commit()
        self.assertIsNone(pipeline.public_data(self.conn,CONFIG,SOURCES)['items'][0]['ai'])
    def test_retraction_applies_to_every_public_output(self):
        key=self.conn.execute('SELECT id FROM items').fetchone()[0]
        core.write_json(self.root/'config/visibility.json',{'hidden_items':[key]})
        data=pipeline.public_data(self.conn,CONFIG,SOURCES)
        rendering.write_release(data)
        self.assertEqual(data['items'],[])
        self.assertEqual(list((self.root/'dist/items').glob('*')),[])
        self.assertNotIn(key,(self.root/'dist/feed.xml').read_text(encoding='utf-8'))
        self.assertNotIn(key,(self.root/'dist/calendar.ics').read_text(encoding='utf-8'))
        self.assertNotIn(key,(self.root/'dist/api/items.json').read_text(encoding='utf-8'))
    def test_release_integrity_and_rollback(self):
        pipeline.build(self.conn,CONFIG,SOURCES)
        first=publishing.verify_release()['built_at']
        self.entry['title']='Updated conference announcement';core.upsert_item(self.conn,self.entry,SOURCE,CONFIG);self.conn.commit()
        pipeline.build(self.conn,CONFIG,SOURCES)
        publishing.rollback()
        payload=core.read_json(self.root/'dist/data.json')
        self.assertEqual(payload['items'][0]['title'],'Conference on climate law')
        (self.root/'dist/secret.txt').write_text('not allowed')
        with self.assertRaises(ValueError):publishing.verify_release()
    def test_failed_fetch_retains_archive(self):
        with patch.object(pipeline,'http_fetch',side_effect=OSError('fixture offline')):
            result=pipeline.collect(self.conn,CONFIG,[SOURCE],True)
        self.assertEqual(result['failures'],1)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM items').fetchone()[0],1)
        self.assertEqual(self.conn.execute('SELECT status FROM source_state').fetchone()[0],'error')
    def test_daily_model_budget(self):
        config=copy.deepcopy(CONFIG);config['ai_daily_limit']=1
        self.conn.execute('INSERT INTO attempts VALUES(?,?,?,?,?)',('other','old',core.now(),'accepted',''));self.conn.commit()
        self.assertIsNone(pipeline.prepare(self.conn,config,SOURCES))
    def test_xml_escaping(self):
        self.entry['title']='Climate & law <context>';core.upsert_item(self.conn,self.entry,SOURCE,CONFIG);self.conn.commit()
        text=rendering.rss(pipeline.public_data(self.conn,CONFIG,SOURCES),pipeline.public_data(self.conn,CONFIG,SOURCES)['items'])
        ET.fromstring(text)
        self.assertIn('&amp;',text)

if __name__=='__main__':unittest.main()

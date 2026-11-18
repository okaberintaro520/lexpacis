import copy
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import core,cfp,pipeline,rendering,publishing,manage,network_policy

class NetworkPolicyTests(unittest.TestCase):
    def result(self,address):return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(address,443))]
    def test_public_approved_host(self):
        with patch.object(network_policy.socket,'getaddrinfo',return_value=self.result('8.8.8.8')):
            self.assertEqual(network_policy.validate_public_url('https://journal.example/path',{'journal.example'}),'https://journal.example/path')
    def test_private_and_reserved_destinations_rejected(self):
        for address in ('127.0.0.1','192.168.1.1','169.254.169.254','198.18.0.1','0.0.0.0'):
            with self.subTest(address=address),patch.object(network_policy.socket,'getaddrinfo',return_value=self.result(address)):
                with self.assertRaises(ValueError):network_policy.validate_public_url('https://journal.example/',{'journal.example'})
    def test_unknown_host_credentials_and_ports_rejected(self):
        for url in ('https://evil.example/','https://name:secret@journal.example/','https://journal.example:8000/','file:///etc/passwd'):
            with self.subTest(url=url),self.assertRaises(ValueError):network_policy.validate_public_url(url,{'journal.example'})
    def test_https_downgrade_rejected(self):
        request=urllib.request.Request('https://journal.example/')
        with self.assertRaises(ValueError):network_policy.RestrictedRedirect({'journal.example'}).redirect_request(request,None,302,'',{},'http://journal.example/')

class FeatureWorkflowTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'runtime/test-temp';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(prefix='features-',dir=parent);self.root=Path(self.temp.name)
        self.patches=[patch.object(module,'ROOT',self.root) for module in (core,cfp,pipeline,rendering,publishing,manage)]
        for p in self.patches:p.start()
        import shutil
        shutil.copytree(ROOT/'web',self.root/'web');shutil.copytree(ROOT/'config',self.root/'config')
        self.config=core.read_json(self.root/'config/site.json');self.conn=core.database(self.root)
        self.evidence='Call for papers on international law. Abstracts are due by 10 January 2027.'
        core.write_json(self.root/'runtime/cfp/state.json',{'pages':{'journal:ljil':{'id':'journal:ljil','url':'https://www.cambridge.org/test-call','status':'identity_matched','content_hash':'current','evidence_excerpt':self.evidence}}})
        self.call={'id':'cfp-test-call','title':'国际法专题征稿','original_title':'Call for papers on international law','kind':'journal_special','journal_id':'ljil','language':'en',
                   'url':'https://www.cambridge.org/test-call','description':'征集国际法论文摘要。','deadline':'2027-01-10','deadline_text':'10 January 2027','deadline_label':'摘要截止','deadline_timezone':None,'event_date':None,
                   'topics':['theory'],'page_id':'journal:ljil','content_hash':'current','evidence_quote':'Abstracts are due by 10 January 2027.'}
    def tearDown(self):
        self.conn.close()
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def apply(self,call):
        path=self.root/'runtime/cfp/output.json';core.write_json(path,{'model':'fixture-only','calls':[call]});cfp.apply_updates(path)
    def test_valid_cfp_update(self):
        self.apply(self.call)
        self.assertEqual(core.read_json(self.root/'runtime/cfp/accepted-calls.json')[0]['deadline'],'2027-01-10')
    def test_cfp_invented_deadline_rejected(self):
        self.call['deadline']='2027-01-11'
        with self.assertRaises(ValueError):self.apply(self.call)
    def test_cfp_unknown_action_or_unread_link_rejected(self):
        self.call['command']='run unknown program'
        with self.assertRaises(ValueError):self.apply(self.call)
        self.call.pop('command');self.call['url']='https://example.org/unread'
        with self.assertRaises(ValueError):self.apply(self.call)
    def test_cfp_stale_evidence_rejected(self):
        self.call['content_hash']='old'
        with self.assertRaises(ValueError):self.apply(self.call)
    def test_cfp_retraction_in_calendar_and_json(self):
        core.write_json(self.root/'config/visibility.json',{'hidden_items':['cfp-ljil-law-society-2027']})
        data=pipeline.public_data(self.conn,self.config,core.read_json(self.root/'config/sources.json'))
        rendering.write_release(data)
        self.assertNotIn('cfp-ljil-law-society-2027',(self.root/'dist/cfp.ics').read_text(encoding='utf-8'))
        self.assertNotIn('cfp-ljil-law-society-2027',(self.root/'dist/api/cfp.json').read_text(encoding='utf-8'))
    def test_editorial_policy_covers_all_public_exports(self):
        sources=core.read_json(self.root/'config/sources.json')
        by_id={source['id']:source for source in sources}
        entries=[
            ('keep','Award interpretation under investment treaties','','crossref-ejil'),
            ('title','A comparative study of Chinese arbitration','','crossref-ejil'),
            ('evidence','A public law case study','The original discusses Taiwan.','crossref-ejil'),
            ('translation','Approaches to arbitration disclosure','','crossref-ejil'),
            ('provenance','Treaty access in archives','','crossref-ejil'),
            ('news','New research library opens','','un-geneva-news'),
            ('wto','A neutral institutional alert','','wto')
        ]
        for slug,title,evidence,source_id in entries:
            url='https://example.org/'+slug
            core.upsert_item(self.conn,{'title':title,'url':url,'evidence':evidence},by_id[source_id],self.config)
        restricted_ids={core.identity('https://example.org/'+entry[0]) for entry in entries[1:]}
        translated_id=core.identity('https://example.org/translation')
        translated=self.conn.execute('SELECT * FROM items WHERE id=?',(translated_id,)).fetchone()
        enrichment={'title_zh':'中国仲裁披露规则','summary_zh':'','module':'research','topics':[],'event':None,'deadline':None}
        self.conn.execute('INSERT INTO enrichments VALUES(?,?,?,?,?)',
                          (translated_id,translated['content_hash'],json.dumps(enrichment),'fixture',core.now()))
        self.conn.execute('INSERT INTO provenance VALUES(?,?,?,?)',
                          (core.identity('https://example.org/provenance'),'crossref-ajil','https://example.org/related/%43hina',core.now()))
        self.call['title']='中国比较法专题征稿'
        self.apply(self.call)
        data=pipeline.public_data(self.conn,self.config,sources)
        self.assertEqual([item['id'] for item in data['items']],[core.identity('https://example.org/keep')])
        self.assertNotIn(self.call['id'],[call['id'] for call in data['cfp']['calls']])
        self.assertEqual({s['id'] for s in data['sources'] if s['status']=='paused'},
                         {'wto','un-geneva-news','un-geneva-press','un-geneva-meetings'})
        rendering.write_release(data)
        for relative in ('data.js','api/items.json','feed.xml','feeds/modules/news.xml','sitemap.xml','calendar.ics','cfp.ics','api/cfp.json'):
            payload=(self.root/'dist'/relative).read_text(encoding='utf-8')
            for item_id in restricted_ids|{self.call['id']}:
                self.assertNotIn(item_id,payload)
        for item_id in restricted_ids:
            self.assertFalse((self.root/'dist/items'/f'{item_id}.html').exists())
    def test_output_path_restricted(self):
        path=self.root/'external-output.json';core.write_json(path,{'model':'fixture-only','calls':[self.call]})
        with self.assertRaises(ValueError):cfp.apply_updates(path)
    def test_rename_is_central_and_keeps_url(self):
        before=self.config['base_url'];manage.rename('国际法学术观察站','JurisScope','连接原始资料与学术研究。')
        config=core.read_json(self.root/'config/site.json');self.assertEqual(config['base_url'],before)
        data=pipeline.public_data(self.conn,config,core.read_json(self.root/'config/sources.json'));rendering.write_release(data)
        self.assertIn('国际法学术观察站',(self.root/'dist/index.html').read_text(encoding='utf-8'))
        self.assertNotIn('法域前沿',(self.root/'dist/index.html').read_text(encoding='utf-8'))
        self.assertIn('国际法学术观察站',(self.root/'dist/calendar.ics').read_text(encoding='utf-8'))
        self.assertIn('JurisScope',(self.root/'dist/data.js').read_text(encoding='utf-8'))
    def test_rename_rejects_html(self):
        with self.assertRaises(ValueError):manage.rename('<script>alert(1)</script>')
    def test_cfp_directory_scope(self):
        public=cfp.public_data(self.conn,[])
        self.assertEqual(len(public['journals']),36)
        self.assertEqual(sum(j['language'] in ('zh','bilingual') for j in public['journals']),14)
        self.assertTrue(all(j.get('submissions_url') for j in public['journals']))

if __name__=='__main__':unittest.main()

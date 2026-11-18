import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
import core,cloud,pipeline,cfp,rendering,security_audit

class CloudTests(unittest.TestCase):
    def setUp(self):
        parent=ROOT/'runtime/test-temp';parent.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=parent);self.root=Path(self.temp.name)
        for folder in ('config','web','dist','.github'):shutil.copytree(ROOT/folder,self.root/folder)
        (self.root/'scripts').mkdir();(self.root/'scripts/safe.py').write_text('# source')
        self.patches=[patch.object(m,'ROOT',self.root) for m in (core,cloud,pipeline,cfp,rendering,security_audit)]
        for p in self.patches:p.start()
        self.config,self.sources=pipeline.configuration();self.snapshot=core.read_json(self.root/'dist/data.json')
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.temp.cleanup()
    def test_restore_keeps_public_history_and_translations(self):
        conn=core.database(self.root)
        try:
            cloud.restore_snapshot(conn,self.snapshot,self.config,self.sources)
            cloud.retain_translations(conn,self.snapshot,self.config,self.sources)
            result=pipeline.public_data(conn,self.config,self.sources)
            self.assertEqual({i['id'] for i in result['items']},{i['id'] for i in self.snapshot['items']})
            old={i['id']:i for i in self.snapshot['items']}
            for item in result['items']:
                self.assertEqual(item['discovered_at'],old[item['id']]['discovered_at'])
                self.assertEqual(item['title_zh'],old[item['id']]['title_zh'])
            with self.assertRaises(ValueError):cloud.restore_snapshot(conn,self.snapshot,self.config,self.sources)
        finally:conn.close()
    def test_changed_title_does_not_reuse_old_translation(self):
        conn=core.database(self.root)
        try:
            cloud.restore_snapshot(conn,self.snapshot,self.config,self.sources)
            translated=next(i for i in self.snapshot['items'] if i.get('title_zh'))
            conn.execute('UPDATE items SET title=? WHERE id=?',('Changed original headline',translated['id']))
            cloud.retain_translations(conn,self.snapshot,self.config,self.sources)
            self.assertIsNone(conn.execute('SELECT * FROM enrichments WHERE item_id=?',(translated['id'],)).fetchone())
        finally:conn.close()
    def test_validated_date_survives_a_skipped_fetch_but_not_a_changed_revision(self):
        item=next(item for item in self.snapshot['items'] if item['module']=='events' and item.get('title_zh'))
        item['source_revision']='a'*64
        item['event']={'date':'2027-02-14','date_text':'14 February 2027','label':'活动日'}
        item['summary_zh']='经上一发布版本整理的活动介绍。'
        conn=core.database(self.root)
        try:
            cloud.restore_snapshot(conn,self.snapshot,self.config,self.sources)
            cloud.retain_translations(conn,self.snapshot,self.config,self.sources)
            current=next(row for row in pipeline.public_data(conn,self.config,self.sources)['items'] if row['id']==item['id'])
            self.assertEqual(current['event'],item['event'])
            self.assertEqual(current['summary_zh'],item['summary_zh'])
            conn.execute('UPDATE items SET content_hash=? WHERE id=?',('b'*64,item['id']))
            cloud.retain_translations(conn,self.snapshot,self.config,self.sources)
            current=next(row for row in pipeline.public_data(conn,self.config,self.sources)['items'] if row['id']==item['id'])
            self.assertIsNone(current['event'])
            self.assertEqual(current['summary_zh'],'')
        finally:conn.close()
    def test_offline_validation_makes_no_network_or_model_calls(self):
        with patch.object(pipeline,'collect',side_effect=AssertionError('must not collect')),patch.object(cfp,'refresh',side_effect=AssertionError('must not fetch')):
            report=cloud.run(offline=True)
        self.assertEqual(report['model_calls'],0);self.assertFalse(report['deployment_confirmed'])
        self.assertFalse(core.read_json(self.root/'dist/data.json')['operations']['scheduler_enabled'])
    def test_source_export_excludes_private_files_and_git_history(self):
        for folder in ('runtime','.git','.openai'):
            (self.root/folder).mkdir(exist_ok=True);(self.root/folder/'private-secret.txt').write_text('fixture secret')
        (self.root/'.env').write_text('SECRET=fixture')
        archive=cloud.export_source()
        with zipfile.ZipFile(archive) as z:
            names=z.namelist()
            self.assertIn('.github/workflows/metadata.yml',names)
            self.assertFalse(any(n.startswith(('runtime/','.git/','.openai/')) or n=='.env' for n in names))
            self.assertFalse(any('fixture secret' in z.read(n).decode('utf-8',errors='ignore') for n in names))
    def test_pages_url_validation(self):
        self.assertEqual(cloud.github_base_url('Example/lexatlas'),'https://example.github.io/lexatlas')
        self.assertEqual(cloud.github_base_url('Example/Example.github.io'),'https://example.github.io')
        with self.assertRaises(ValueError):cloud.github_base_url('https://evil.example/repo')
    def test_unregistered_snapshot_source_rejected(self):
        self.snapshot['items'][0]['source_id']='unknown'
        conn=core.database(self.root)
        try:
            with self.assertRaises(ValueError):cloud.restore_snapshot(conn,self.snapshot,self.config,self.sources)
        finally:conn.close()

if __name__=='__main__':unittest.main()

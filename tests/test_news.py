import copy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import core,news,pipeline

class NewsTests(unittest.TestCase):
    def setUp(self):
        self.config=core.read_json(ROOT/'config/site.json')
        self.sources=core.read_json(ROOT/'config/sources.json')
        self.source=next(s for s in self.sources if s['id']=='un-geneva-news')
        self.url='/en/news-media/news/2026/11/124933/a-news-title'
    def test_card_dates_do_not_leak(self):
        markup=f'<article><time>17 November 2026</time><a href="{self.url}">A sufficiently long first news headline</a></article><article><a href="{self.url}-2">A sufficiently long second news headline</a></article>'
        rows=core.parse_listing(markup.encode(),self.source)
        self.assertEqual(rows[0]['published_at'],'2026-11-17')
        self.assertIsNone(rows[1]['published_at'])
    def test_page_date_is_not_article_date(self):
        markup=f'<time>17 November 2026</time><a href="{self.url}">A sufficiently long original news headline</a><a href="{self.url}">Read more</a>'
        rows=core.parse_listing(markup.encode(),self.source)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['date_precision'],'unknown')
    def test_drupal_news_row_date_follows_nested_image(self):
        markup=(f'<article class="node"><div class="views-row row-1">'
                '<article class="un-news-image"><img alt=""></article>'
                f'<h2><a href="{self.url}">A sufficiently long first news headline</a></h2>'
                '<time>17 November 2026</time></div>'
                f'<div class="views-row row-2"><a href="{self.url}-2">A sufficiently long second news headline</a>'
                '<time>18 November 2026</time></div></article>')
        rows=core.parse_listing(markup.encode(),self.source)
        self.assertEqual([r['published_at'] for r in rows],['2026-11-17','2026-11-18'])
    def test_institutional_workshop_report_stays_news(self):
        self.assertEqual(core.classify('UN workshop reports on civilian protection',self.source,self.config)[0],'news')
    def test_import_is_idempotent_and_not_fetch_success(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime/test-temp') as temporary:
            root=Path(temporary);(root/'config').mkdir()
            core.write_json(root/'config/news-initial.json',{
                'checked_method':'official_listing_read',
                'listing_url':'https://www.ungeneva.org/en/news-media/news',
                'checked_at':'2026-11-18',
                'items':[{'source_id':self.source['id'],'title':'Test listing headline',
                          'title_zh':'测试目录标题','published_at':'2026-11-17',
                          'url':'https://www.ungeneva.org'+self.url}]
            })
            with patch.object(core,'ROOT',root),patch.object(news,'ROOT',root),patch.object(pipeline,'ROOT',root):
                conn=core.database(root)
                try:
                    first=news.import_initial(conn,self.config,self.sources)
                    second=news.import_initial(conn,self.config,self.sources)
                    self.assertEqual(first['added'],1);self.assertEqual(second['added'],0)
                    self.assertEqual(second['translated_titles'],0)
                    self.assertEqual(conn.execute('SELECT COUNT(*) FROM source_state').fetchone()[0],0)
                    public=pipeline.public_data(conn,self.config,self.sources)
                    self.assertEqual(len(public['items']),1)
                    self.assertTrue(all(i['module']=='news' and i['material_type']=='官方机构新闻报道' and not i['summary_zh'] for i in public['items']))
                finally:conn.close()
    def test_news_cannot_be_promoted_to_case_material(self):
        item={'id':'test','content_hash':'hash','title':'News headline','module':'news','authority':'official_news_service','evidence_basis':'官方新闻目录元数据','source_excerpt':''}
        result={'id':'test','content_hash':'hash','title_zh':'新闻标题','summary_zh':'','topics':[],'module':'cases','evidence_quotes':[]}
        with self.assertRaises(ValueError):pipeline.validate_enrichment(result,item,self.config)

if __name__=='__main__':unittest.main()

import importlib.util
import logging
import re
import sys
import types
import unittest
from unittest.mock import patch


class ArticleRefreshTests(unittest.TestCase):
    def load(self):
        stub = types.SimpleNamespace(strip_html=lambda value: re.sub('<[^>]+>', ' ', value),
                                     normalize_text=lambda value: value.casefold(), logger=logging.getLogger('test'))
        with patch.dict(sys.modules, {'main': stub}):
            spec = importlib.util.spec_from_file_location('refresh_article', 'article_sources.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        return module

    def test_latest_headline_and_late_update_are_preserved(self):
        article = self.load()
        late = 'Son güncellemede yaralı öğrencilerden birinin hayatını kaybettiği açıklandı'
        html = ('<html><head><meta property="article:modified_time" content="2026-10-08T12:00:00Z"></head>'
                '<h1>Bir öğrenci hayatını kaybetti</h1><article><p>' + 'İlk açıklamada olay ve yaralıların tedavisi anlatıldı ' * 65
                + '</p><p>' + late + '</p></article></html>')
        response = types.SimpleNamespace(content=html.encode(), headers={'Content-Type': 'text/html; charset=utf-8'},
                                         url='https://example.test/article', raise_for_status=lambda: None)
        item = {'title': 'Sekiz öğrenci yaralandı'}
        with patch.object(article.requests, 'get', return_value=response):
            text = article.fetch_url_text(response.url, item)
        self.assertGreater(len(text), 2600)
        self.assertIn(late, text)
        self.assertEqual(item['source_headline'], 'Bir öğrenci hayatını kaybetti')
        self.assertEqual(item['source_modified_at'], '2026-10-08T12:00:00Z')
        self.assertTrue(item['source_checked_at'])

    def test_failed_article_cannot_be_replaced_with_stale_rss(self):
        article = self.load()
        item = {'url': 'https://example.test/article', 'title': 'Old headline', 'summary': 'Old source summary ' * 50}
        with patch.object(article, 'fetch_url_text', side_effect=RuntimeError('source unavailable')):
            with self.assertRaisesRegex(ValueError, 'stale RSS'):
                article.fetch_article_content(item)

if __name__ == '__main__':
    unittest.main()

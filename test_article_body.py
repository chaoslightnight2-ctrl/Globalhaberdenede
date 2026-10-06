import importlib.util
import logging
import re
import sys
import types
import unittest
from unittest.mock import patch

class ArticleBodyTests(unittest.TestCase):
    def test_primary_body_preserves_institution_and_excludes_other_news(self):
        stub = types.SimpleNamespace(strip_html=lambda value: re.sub('<[^>]+>', ' ', value),
            normalize_text=lambda value: value.casefold(), logger=logging.getLogger('article-test'))
        with patch.dict(sys.modules, {'main': stub}):
            spec = importlib.util.spec_from_file_location('article_under_test', 'article_sources.py')
            article = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(article)
        html = '''<html><nav>Ankara İstanbul Arama</nav><div class="news-content">
        <p>Soma Cumhuriyet Başsavcılığı koordinesinde dokuz şüpheli gözaltına alındı</p>
        <div class="related-news"><p>Sıradaki haber başka kişinin farklı kararı</p></div>
        <div class="news-tags"><p>Etiketler</p></div></div><aside>Başka olay</aside></html>'''
        actual = article.extract_article_container(html)
        self.assertEqual(actual, 'Soma Cumhuriyet Başsavcılığı koordinesinde dokuz şüpheli gözaltına alındı')
        self.assertNotIn('Sıradaki', actual)
        self.assertNotIn('Ankara', actual)
        self.assertEqual(article.extract_article_container('<p>Unscoped content</p>'), '')

    def test_wordpress_article_body_excludes_navigation_and_related(self):
        stub = types.SimpleNamespace(strip_html=lambda value: re.sub('<[^>]+>', ' ', value),
            normalize_text=lambda value: value.casefold(), logger=logging.getLogger('article-test'))
        with patch.dict(sys.modules, {'main': stub}):
            spec = importlib.util.spec_from_file_location('article_under_test', 'article_sources.py')
            article = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(article)
        html = '<article><nav>Mission Overview Rover Components</nav><div class="entry-content"><p>Written by Someone</p><p>The rover found pale rocks beyond the crater</p><figure><figcaption>Credit Agency</figcaption></figure><div class="related-articles"><p>Another story</p></div><p>Visit Mission Updates</p></div></article>'
        self.assertEqual(article.extract_article_container(html), 'The rover found pale rocks beyond the crater')

if __name__ == '__main__':
    unittest.main()

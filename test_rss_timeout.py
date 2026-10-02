import ast
import logging
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from typing import Any
import requests

class RssTimeoutTests(unittest.TestCase):
    def test_unavailable_feed_does_not_block_next_real_feed(self):
        tree = ast.parse(Path('main.py').read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'fetch_news_pool')
        network = types.SimpleNamespace(get=Mock(side_effect=[requests.Timeout(), types.SimpleNamespace(
            content=b'publisher-rss', raise_for_status=lambda: None)]), RequestException=requests.RequestException)
        entry = types.SimpleNamespace(title='Actual publisher title', summary='Actual publisher summary', link='https://publisher.test/news')
        parser = Mock(return_value=types.SimpleNamespace(entries=[entry]))
        namespace = dict(Any=Any, datetime=datetime, timedelta=timedelta, UTC=timezone.utc, TIMEZONE=timezone.utc,
                         NEWS_QUERIES=['unavailable', 'available'], logger=logging.getLogger('rss-test'), requests=network,
                         feedparser=types.SimpleNamespace(parse=parser), google_news_rss_url=lambda query: 'https://feed.test/' + query,
                         parse_entry_datetime=lambda item: datetime.now(timezone.utc), strip_html=lambda text: text,
                         fingerprint=lambda title, summary: 'actual-source', mentions_past_event_date=lambda text: False)
        exec(compile(ast.Module(body=[function], type_ignores=[]), 'main.py', 'exec'), namespace)
        items = namespace['fetch_news_pool']()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['url'], entry.link)
        self.assertEqual(network.get.call_count, 2)
        self.assertTrue(all(call.kwargs['timeout'] == 25 for call in network.get.call_args_list))
        parser.assert_called_once_with(b'publisher-rss')

if __name__ == '__main__':
    unittest.main()

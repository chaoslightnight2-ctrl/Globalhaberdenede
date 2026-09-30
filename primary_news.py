"""Collect article URLs directly from publisher RSS, not Google landing pages."""
from __future__ import annotations
from datetime import datetime, timedelta
import feedparser
import requests
import main as bot

_original_pool = bot.fetch_news_pool
_original_rank = bot.enrich_and_rank


def publisher_first(news):
    ranked = _original_rank(news)
    ranked.sort(key=lambda item: (bool(item.get('direct_source')), item.get('viral_score', 0)), reverse=True)
    return ranked
FEEDS = [
    ('BBC World', 'https://feeds.bbci.co.uk/news/world/rss.xml'),
    ('BBC Business', 'https://feeds.bbci.co.uk/news/business/rss.xml'),
    ('BBC Science', 'https://feeds.bbci.co.uk/news/science_and_environment/rss.xml'),
    ('BBC Technology', 'https://feeds.bbci.co.uk/news/technology/rss.xml'),
    ('DW World', 'https://rss.dw.com/rdf/rss-en-world'),
    ('Guardian World', 'https://www.theguardian.com/world/rss'),
    ('NASA', 'https://www.nasa.gov/news-release/feed/'),
]


def collect(hours_back=72):
    cutoff = bot.now_tr() - timedelta(hours=hours_back)
    items = []
    for source, url in FEEDS:
        try:
            response = requests.get(url, timeout=25, headers={'User-Agent': 'Mozilla/5.0'})
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            for entry in feed.entries:
                at = bot.parse_entry_datetime(entry)
                if not at or at < cutoff:
                    continue
                title = bot.strip_html(entry.get('title', ''))
                link = entry.get('link', '')
                if not title or not link or '/live/' in link or '/video/' in link:
                    continue
                parts = [entry.get('summary', ''), entry.get('description', '')]
                parts.extend(row.get('value', '') for row in entry.get('content', []))
                summary = max((bot.strip_html(part) for part in parts), key=len, default='')
                publisher = source.split()[0] if source != 'NASA' else ''
                items.append({'title': title, 'summary': summary, 'url': link, 'source': source, 'source_name': publisher,
                              'query': source, 'published_at': at.astimezone(bot.TIMEZONE).isoformat(),
                              'fingerprint': bot.fingerprint(title, summary), 'direct_source': True})
            bot.logger.info('Direct publisher RSS: %s, entries=%s', source, len(feed.entries))
        except Exception as exc:
            bot.logger.warning('Publisher RSS unavailable: %s: %s', source, exc)
    # These are parallel real news inputs, not generated substitute narration.
    all_items = items + _original_pool(hours_back=hours_back)
    seen = set()
    result = []
    for item in all_items:
        if item['url'] in seen:
            continue
        seen.add(item['url'])
        result.append(item)
    return result


bot.fetch_news_pool = collect
bot.enrich_and_rank = publisher_first

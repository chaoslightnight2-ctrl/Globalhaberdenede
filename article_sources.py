from __future__ import annotations
import json
import html
import re
from typing import Any
import requests
import main as bot
strip_html = bot.strip_html
normalize_text = bot.normalize_text
logger = bot.logger

def decoded_html(response):
    """Honor HTML encoding instead of requests' default Latin-1 for text/html."""
    content = response.content
    header = response.headers.get('Content-Type', '')
    declared = re.search(r'charset\s*=\s*["\']?([\w-]+)', header, re.I)
    if declared:
        return content.decode(declared.group(1), errors='replace')
    prefix = content[:4096].decode('ascii', errors='ignore')
    meta = re.search(r'<meta\b[^>]*charset\s*=\s*["\']?([\w-]+)', prefix, re.I)
    if meta:
        return content.decode(meta.group(1), errors='replace')
    try:
        return content.decode('utf-8-sig')
    except UnicodeDecodeError:
        return content.decode(response.apparent_encoding or response.encoding or 'utf-8', errors='replace')

def clean_article_text(text: str) -> str:
    text = strip_html(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    remove_phrases = [
        "Son Dakika Haberleri", "Video videosunu izle", "Haberi Görüntüle", "Devamını Oku",
        "Abone Ol", "Giriş Yap", "Kaydol", "Reklam", "Çerez", "Cookie", "KVKK", "Google News",
    ]
    for phrase in remove_phrases:
        text = re.sub(re.escape(phrase), " ", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip(" .-|:")


def google_news_base64_token(url: str) -> str:
    try:
        from urllib.parse import urlparse
        parts = [p for p in urlparse(url).path.split("/") if p]
        for marker in ("articles", "read"):
            if marker in parts:
                return parts[parts.index(marker) + 1].split("?")[0]
    except Exception:
        pass
    return ""


def decode_google_news_old(url: str) -> str:
    token = google_news_base64_token(url)
    if not token:
        return ""
    try:
        import base64
        raw = base64.urlsafe_b64decode(token + "===")
        decoded = raw.decode("latin1", errors="ignore")
        found = re.findall(r"https?://[^\x00-\x20\"'<>]+", decoded)
        if found:
            return found[0]
    except Exception:
        return ""
    return ""


def decode_google_news_batchexecute(url: str) -> str:
    token = google_news_base64_token(url)
    if not token:
        return ""
    try:
        from urllib.parse import quote
        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5"}
        page = requests.get(f"https://news.google.com/articles/{token}", headers=headers, timeout=15).text
        signature_match = re.search(r'data-n-a-sg="([^"]+)"', page)
        timestamp_match = re.search(r'data-n-a-ts="([^"]+)"', page)
        if not signature_match or not timestamp_match:
            return ""
        signature = signature_match.group(1)
        timestamp = timestamp_match.group(1)
        inner = [
            "garturlreq",
            [["tr-TR", "TR", ["FINANCE_TOP_INDICES", "WEB_TEST_1_0_0"], None, None, 1, 1, "TR:tr", None, 180, None, None, None, None, None, 0], "tr-TR", "TR", 1, [2, 3, 4, 8], 1, 0, "655000234", 0, 0, None, 0],
            token,
            int(timestamp),
            signature,
        ]
        outer = [[["Fbv4je", json.dumps(inner, separators=(",", ":")), None, "generic"]]]
        data = "f.req=" + quote(json.dumps(outer, separators=(",", ":")))
        resp = requests.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            headers={**headers, "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            data=data,
            timeout=20,
        )
        resp.raise_for_status()
        urls = re.findall(r"https?://[^\\\"\]]+", resp.text)
        for candidate in urls:
            if "news.google.com" not in candidate and "google.com" not in candidate:
                return candidate.replace("\\u003d", "=").replace("\\u0026", "&")
    except Exception as exc:
        logger.warning("Google News link çözülemedi: %s", exc)
    return ""


def resolve_article_url(item: dict[str, Any]) -> str:
    url = item.get("url", "")
    if "news.google.com" not in url:
        return url
    decoded = decode_google_news_old(url) or decode_google_news_batchexecute(url)
    if decoded:
        item["resolved_url"] = decoded
        logger.info("Google News gerçek kaynak çözüldü: %s", decoded[:120])
        return decoded
    return url


def score_article_text(text: str, title: str) -> int:
    norm = normalize_text(text)
    title_norm = normalize_text(title)
    if not norm:
        return 0
    score = min(len(norm), 2200) // 18
    if title_norm and norm == title_norm:
        score -= 90
    if len(norm.split()) < 45:
        score -= 55
    bad = ["çerez", "cookie", "abonelik", "reklam", "gizlilik", "whatsapp", "telegram", "facebook", "twitter", "instagram", "google haber"]
    score -= sum(25 for word in bad if word in norm)
    return score


def extract_json_ld_article_body(html_text: str) -> str:
    chunks = []
    scripts = re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>', html_text, flags=re.I)
    for raw in scripts:
        try:
            raw = html.unescape(raw).strip()
            data = json.loads(raw)
            queue = data if isinstance(data, list) else [data]
            while queue:
                obj = queue.pop(0)
                if isinstance(obj, dict):
                    body = obj.get("articleBody") or obj.get("description")
                    if body:
                        chunks.append(str(body))
                    graph = obj.get("@graph")
                    if isinstance(graph, list):
                        queue.extend(graph)
                elif isinstance(obj, list):
                    queue.extend(obj)
        except Exception:
            continue
    return clean_article_text(" ".join(chunks))


def extract_meta_content(html_text: str) -> str:
    matches = re.findall(
        r'<meta[^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\'][^>]+content=["\']([^"\']+)["\']',
        html_text,
        flags=re.I,
    )
    if not matches:
        matches = re.findall(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:description|og:description|twitter:description)["\']',
            html_text,
            flags=re.I,
        )
    return clean_article_text(" ".join(matches))


def extract_paragraph_text(html_text: str) -> str:
    html_text = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.I)
    html_text = re.sub(r"<style[\s\S]*?</style>", " ", html_text, flags=re.I)
    blocks = []
    for pattern in [
        r"<article[^>]*>([\s\S]*?)</article>",
        r"<main[^>]*>([\s\S]*?)</main>",
        r"<div[^>]+class=[\"'][^\"']*(?:article|content|news|detail|story|body|text)[^\"']*[\"'][^>]*>([\s\S]*?)</div>",
    ]:
        blocks.extend(re.findall(pattern, html_text, flags=re.I))
    if not blocks:
        blocks = [html_text]
    cleaned = []
    blocked = ["çerez", "cookie", "abonelik", "reklam", "gizlilik", "whatsapp", "telegram", "facebook", "twitter", "instagram", "yorumlar", "sıradaki haber", "en çok okunan"]
    for block in blocks[:8]:
        paragraphs = re.findall(r"<(?:p|h1|h2|h3|li)[^>]*>([\s\S]*?)</(?:p|h1|h2|h3|li)>", block, flags=re.I)
        for paragraph in paragraphs:
            text = clean_article_text(paragraph)
            low = normalize_text(text)
            if len(text) < 45:
                continue
            if any(word in low for word in blocked):
                continue
            if text in cleaned:
                continue
            cleaned.append(text)
            if len(" ".join(cleaned)) > 2600:
                break
        if len(" ".join(cleaned)) > 2600:
            break
    return clean_article_text(" ".join(cleaned))


def extract_article_container(html_text: str) -> str:
    """Read only explicit article-body paragraphs; exclude menus and related items."""
    from lxml import html as document_html
    document = document_html.fromstring(html_text)
    nodes = document.xpath('//*[@itemprop="articleBody"] | //div[contains(concat(" ", normalize-space(@class), " "), " news-content ")]')
    if not nodes:
        for token in ('entry-content', 'article-body', 'article-content', 'story-body'):
            nodes = document.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " ' + token + ' ")]')
            if nodes:
                break
    if not nodes:
        nodes = document.xpath('//article')
    for node in nodes:
        for extra in node.xpath('.//nav | .//aside | .//*[contains(concat(" ", normalize-space(@class), " "), " related-news ")] | .//*[contains(concat(" ", normalize-space(@class), " "), " news-tags ")]'):
            extra.drop_tree()
        for extra in node.xpath('.//header | .//footer | .//figure | .//figcaption | .//*[contains(@class, "related") or contains(@class, "byline") or contains(@class, "article-meta")]'):
            if extra.getparent() is not None:
                extra.drop_tree()
        paragraphs = [clean_article_text(p.text_content()) for p in node.xpath('.//p')
                      if p.text_content().strip() and not re.match(r'^(Written by|By |Visit )', p.text_content().strip(), re.I)]
        result = clean_article_text(' '.join(part for part in paragraphs if part))
        if result:
            return result
    return ''


def fetch_url_text(url: str, item: dict[str, Any]) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
        "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.5",
    }
    response = requests.get(url, headers=headers, timeout=22, allow_redirects=True)
    response.raise_for_status()
    item["resolved_url"] = response.url
    html_text = decoded_html(response)
    from lxml import html as document_html
    document = document_html.fromstring(html_text)
    heads = document.xpath('//h1')
    if heads:
        latest_headline = clean_article_text(heads[0].text_content())
        if latest_headline:
            item['source_headline'] = latest_headline
    modified = document.xpath('//meta[@property="article:modified_time"]/@content | //meta[@name="dateModified"]/@content')
    item['source_modified_at'] = modified[0] if modified else ''
    from datetime import datetime, timezone
    item['source_checked_at'] = datetime.now(timezone.utc).isoformat()
    import trafilatura
    extracted = extract_article_container(html_text) or trafilatura.extract(html_text, url=response.url, include_comments=False, include_tables=False)
    parts = [extracted or extract_json_ld_article_body(html_text)]
    return clean_article_text(" ".join(part for part in parts if part))[:12000]


def fetch_article_content(item: dict[str, Any]) -> str:
    title = item.get("title", "")
    candidates = []
    resolved = resolve_article_url(item)
    if resolved:
        candidates.append(resolved)
    if item.get("url") and item.get("url") not in candidates:
        candidates.append(item["url"])
    best = ""
    best_score = -999
    for url in dict.fromkeys(candidates):
        try:
            text = fetch_url_text(url, item)
            score = score_article_text(text, title)
            logger.info("İçerik adayı skor=%s uzunluk=%s url=%s", score, len(text), url[:100])
            if score > best_score:
                best = text
                best_score = score
        except Exception as exc:
            logger.warning("Haber içeriği çekilemedi: %s", exc)
    rss_text = clean_article_text(" ".join([item.get("summary", ""), item.get("title", "")]))
    # A fetched article body takes priority over a noisy full-page RSS summary.
    if not best or best_score < 25:
        raise ValueError('Updated publisher article unavailable; stale RSS cannot replace it')
    if best_score < 25:
        logger.warning("Haber içeriği hala zayıf: skor=%s başlık=%s", best_score, title[:90])
    item["article_score"] = best_score
    return best[:12000]



bot.fetch_article_content = fetch_article_content

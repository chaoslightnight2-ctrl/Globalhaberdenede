#!/usr/bin/env python3
"""
Global news YouTube Shorts bot.

- Son 20 saatteki dünya ve uluslararası haberleri tarar.
- Viral olma potansiyeli yüksek 3 farklı global haberi seçer.
- Daha önce kullanılan haberleri news_history.json ile eler.
- Seçilen haberleri selected_news.json dosyasına yazar.
- Her haber için kısa, sürükleyici Türkçe metin oluşturur.
- Habere uygun Pexels arka plan videosu bulur.
- 3 Shorts videosu üretir.
- YouTube'a 07:00 / 12:00 / 18:00 için zamanlı yükler.
"""

from __future__ import annotations

import asyncio
import calendar
import hashlib
import html
import json
import logging
import os
import re
import sys
import traceback
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo
from difflib import SequenceMatcher

import edge_tts
import feedparser
import requests
from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from moviepy.audio.fx.all import audio_loop, volumex
from moviepy.editor import AudioFileClip, CompositeAudioClip, CompositeVideoClip, TextClip, VideoFileClip
from moviepy.video.fx.all import crop

load_dotenv()

PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
YOUTUBE_REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN")
CLIENT_SECRETS_FILE = "client_secrets.json"
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YOUTUBE_CATEGORY_ID = "25"
TIMEZONE = ZoneInfo("Europe/Istanbul")

if not PEXELS_API_KEY:
    sys.exit("PEXELS_API_KEY tanımlı değil.")
if not YOUTUBE_REFRESH_TOKEN:
    sys.exit("YOUTUBE_REFRESH_TOKEN tanımlı değil.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler("bot.log", encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

NEWS_QUERIES = [
    "world breaking news today", "global latest news today",
    "international politics diplomacy world", "global economy inflation interest rates markets",
    "cost of living prices wages housing worldwide", "technology artificial intelligence cybersecurity news",
    "science space discoveries research news", "health public health medical research world news",
    "climate environment energy water crisis news", "natural disasters earthquakes floods fires global",
    "transport aviation railways global news", "education universities schools global news",
    "culture arts cinema music world news", "world sports football basketball news",
    "society human interest inspiring stories world", "Europe latest news policy economy",
    "Middle East latest news diplomacy humanitarian", "Asia latest news economy technology",
    "Africa latest news society economy", "Americas latest news politics economy",
    "United Nations international decisions news", "global digital culture social media trends",
]

BACKGROUND_HINTS = {
    "deprem": ["earthquake city damage", "rescue workers", "emergency city"],
    "yangın": ["fire smoke city", "firefighters emergency", "building fire smoke"],
    "sel": ["flood city street", "storm rain city", "water on road"],
    "kaza": ["traffic road night", "police lights road", "highway traffic"],
    "savaş": ["military vehicles", "war zone smoke", "soldiers silhouette"],
    "çatışma": ["military vehicles", "police lights night", "city smoke"],
    "gazze": ["middle east city", "humanitarian aid", "city smoke"],
    "israil": ["middle east city", "government building", "press conference"],
    "ukrayna": ["ukraine city", "war zone smoke", "military vehicles"],
    "rusya": ["moscow skyline", "government building", "military vehicles"],
    "abd": ["washington dc", "white house", "press conference"],
    "amerika": ["washington dc", "white house", "city skyline"],
    "avrupa": ["europe city skyline", "parliament building", "eu flags"],
    "çin": ["beijing skyline", "china city", "business district skyline"],
    "nato": ["nato flags", "military meeting", "press conference"],
    "birleşmiş milletler": ["united nations building", "diplomacy meeting", "press conference"],
    "ekonomi": ["financial graph", "business district skyline", "stock market screen"],
    "enflasyon": ["grocery shopping", "money close up", "financial graph"],
    "faiz": ["financial chart", "bank building", "business skyline"],
    "dolar": ["money close up", "stock market screen", "business district skyline"],
    "borsa": ["stock market screen", "financial graph", "business trading floor"],
    "petrol": ["oil refinery", "oil pump", "energy industry"],
    "seçim": ["ballot box", "election crowd", "press conference podium"],
    "başkan": ["government building", "press conference", "meeting hall"],
    "spor": ["football stadium crowd", "sports arena lights", "stadium field"],
    "maç": ["football stadium crowd", "soccer field", "sports arena"],
    "transfer": ["football stadium crowd", "sports press conference", "soccer field"],
}

OUTPUT_DIR = Path("output")
FONT_DIR = Path("fonts")
FONT_PATH = FONT_DIR / "Montserrat-Bold.ttf"
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/montserrat/static/Montserrat-Bold.ttf"
HISTORY_FILE = Path("news_history.json")
SELECTED_FILE = Path("selected_news.json")
PLAN_FILE = Path("video_plan.json")
VIDEO_SIZE = (1080, 1920)

DEFAULT_VOICE = os.getenv("VOICE", "tr-TR-AhmetNeural")
RATE = os.getenv("VOICE_RATE", "+8%")
PITCH = os.getenv("VOICE_PITCH", "-3Hz")

MAX_CAPTION_WORDS = 3
MAX_CAPTION_DURATION = 0.75
FONT_SIZE = 58
STROKE_WIDTH = 4


def now_tr() -> datetime:
    return datetime.now(TIMEZONE)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def strip_html(text: str) -> str:
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_text(text: str) -> str:
    text = strip_html(text).lower()
    text = re.sub(r"\s*-\s*[^-]+$", "", text)
    text = re.sub(r"[^a-z0-9çğıöşü\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_text(a), normalize_text(b)).ratio()


def fingerprint(title: str, summary: str = "") -> str:
    raw = normalize_text(title) + "|" + normalize_text(summary)[:240]
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def google_news_rss_url(query: str) -> str:
    # Arayüz dili Türkçe kalır; sorgular global haber odaklıdır.
    return f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=tr&gl=TR&ceid=TR:tr"


def parse_entry_datetime(entry: Any) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = getattr(entry, key, None)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
            except Exception:
                pass
    return None


def fetch_news_pool(hours_back: int = 20) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours_back)
    collected: list[dict[str, Any]] = []

    for query in NEWS_QUERIES:
        logger.info("Global RSS çekiliyor: %s", query)
        feed = feedparser.parse(google_news_rss_url(query))
        for entry in feed.entries:
            published_at = parse_entry_datetime(entry)
            if not published_at or published_at < cutoff:
                continue
            title = strip_html(getattr(entry, "title", ""))
            summary = strip_html(getattr(entry, "summary", "")) or strip_html(getattr(entry, "description", ""))
            link = getattr(entry, "link", "")
            if not title or not link:
                continue
            collected.append({
                "title": title,
                "summary": summary[:900],
                "url": link,
                "query": query,
                "source": "Google News RSS",
                "published_at": published_at.astimezone(TIMEZONE).isoformat(),
                "fingerprint": fingerprint(title, summary),
            })

    unique: list[dict[str, Any]] = []
    seen = set()
    for item in collected:
        if item["fingerprint"] in seen:
            continue
        seen.add(item["fingerprint"])
        unique.append(item)
    logger.info("Toplanan benzersiz global haber sayısı: %s", len(unique))
    return unique


def keyword_score(text: str) -> int:
    text_n = normalize_text(text)
    weights = {
        "son dakika": 10,
        "dünya": 5,
        "uluslararası": 6,
        "küresel": 6,
        "kriz": 8,
        "savaş": 9,
        "çatışma": 8,
        "gazze": 8,
        "israil": 7,
        "ukrayna": 7,
        "rusya": 7,
        "abd": 6,
        "amerika": 6,
        "avrupa": 5,
        "çin": 6,
        "nato": 7,
        "birleşmiş milletler": 7,
        "başkan": 5,
        "seçim": 5,
        "karar": 4,
        "açıklama": 3,
        "deprem": 9,
        "yangın": 7,
        "sel": 7,
        "kaza": 6,
        "ekonomi": 7,
        "enflasyon": 7,
        "faiz": 7,
        "dolar": 6,
        "borsa": 6,
        "petrol": 6,
        "teknoloji": 5,
        "yapay zeka": 6,
        "spor": 3,
        "maç": 3,
        "transfer": 4,
    }
    return sum(weight for word, weight in weights.items() if word in text_n)


def recency_score(published_iso: str) -> float:
    published = datetime.fromisoformat(published_iso)
    hours_old = max((now_tr() - published).total_seconds() / 3600, 0.0)
    return max(0.0, 40.0 - hours_old * 1.6)


def enrich_and_rank(news: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for item in news:
        score = recency_score(item["published_at"])
        score += keyword_score(item["title"] + " " + item.get("summary", ""))
        title_words = len(item["title"].split())
        if 5 <= title_words <= 16:
            score += 3
        if len(item.get("summary", "")) > 120:
            score += 2
        item["viral_score"] = round(score, 2)
    return sorted(news, key=lambda x: x["viral_score"], reverse=True)


def in_history(item: dict[str, Any], history_items: list[dict[str, Any]]) -> bool:
    for old in history_items:
        if item["fingerprint"] == old.get("fingerprint"):
            return True
        if similarity(item["title"], old.get("title", "")) >= 0.78:
            return True
    return False


def too_similar_to_selected(item: dict[str, Any], selected: list[dict[str, Any]]) -> bool:
    return any(
        item["fingerprint"] == other["fingerprint"] or similarity(item["title"], other["title"]) >= 0.74
        for other in selected
    )


def detect_topic_bucket(item: dict[str, Any]) -> str:
    text = normalize_text(item.get("title", "") + " " + item.get("summary", ""))
    groups = [
        ("technology_science", ["technology", "artificial intelligence", "cyber", "science", "space", "research", "bilim", "uzay"]),
        ("economy_life", ["economy", "inflation", "interest rate", "prices", "wages", "housing", "markets", "ekonomi"]),
        ("health_education", ["health", "hospital", "medicine", "education", "school", "university", "sağlık", "eğitim"]),
        ("climate_energy", ["climate", "environment", "drought", "energy", "electricity", "renewable", "iklim", "enerji"]),
        ("transport_cities", ["transport", "aviation", "railway", "airport", "traffic", "infrastructure", "ulaşım"]),
        ("culture_arts", ["culture", "cinema", "film", "music", "art", "book", "festival", "kültür", "sanat"]),
        ("sports", ["sport", "football", "basketball", "volleyball", "match", "spor", "futbol"]),
        ("disasters_safety", ["earthquake", "fire", "flood", "storm", "disaster", "deprem", "yangın", "sel"]),
        ("politics_diplomacy", ["politics", "election", "parliament", "government", "diplomacy", "nato", "siyaset", "seçim"]),
        ("society", ["society", "community", "human rights", "workers", "social", "toplum"]),
    ]
    for bucket, words in groups:
        if any(word in text for word in words):
            return bucket
    return "world_affairs"


def choose_top_three(news: list[dict[str, Any]], history: dict[str, Any]) -> list[dict[str, Any]]:
    ranked = enrich_and_rank(news)
    for item in ranked:
        item["topic_bucket"] = detect_topic_bucket(item)
    processed = history.get("processed_news", [])
    selected: list[dict[str, Any]] = []
    topic_counts: dict[str, int] = {}
    for cap in (1, 2, 99):
        for item in ranked:
            if item in selected or in_history(item, processed) or too_similar_to_selected(item, selected):
                continue
            bucket = item.get("topic_bucket", "world_affairs")
            if topic_counts.get(bucket, 0) >= cap:
                continue
            selected.append(item)
            topic_counts[bucket] = topic_counts.get(bucket, 0) + 1
            if len(selected) == 3:
                return selected
    raise RuntimeError("Tekrarsız üç global haber seçilemedi.")



def _groq_news_json(prompt: str) -> dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY tanımlı değil; yedek anlatım kapalı.")
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    response = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a careful Turkish-language global news editor. Use only supplied facts; preserve uncertainty and attribution."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.25,
            "max_completion_tokens": 520,
            "response_format": {"type": "json_object"},
        },
        timeout=90,
    )
    try:
        response.raise_for_status()
    except requests.HTTPError as exc:
        details = re.sub(r"\s+", " ", response.text or "")[:500]
        raise RuntimeError(f"Groq başarısız: HTTP {response.status_code}, model={model}, {details}") from exc
    choices = response.json().get("choices") or []
    if not choices:
        raise RuntimeError(f"Groq boş yanıt verdi: model={model}")
    content = choices[0].get("message", {}).get("content", "")
    start, end = content.find("{"), content.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("Groq JSON nesnesi döndürmedi.")
    return json.loads(content[start:end + 1])


def generate_news_script(item: dict[str, Any]) -> str:
    source_title = strip_html(item.get("title", ""))
    source_text = strip_html(item.get("summary", ""))
    if len(source_text) < 80:
        raise RuntimeError(f"Kaynak özeti yetersiz; güvenilir Shorts üretimi durduruldu: {source_title}")
    bucket = detect_topic_bucket(item)
    prompt = f"""
Global Haber için kısa ve merak uyandıran bir YouTube Shorts metni hazırla.
Kapsam dünya siyasetiyle sınırlı değil: ekonomi, teknoloji, bilim, sağlık, iklim, afet, ulaşım,
eğitim, kültür, spor ve toplum haberlerini de kapsar. Bu gelişmenin somut ayrıntısını ve etkisini anlat.
Başlık merak uyandırsın; kaynaktaki olguyu çarpıtmasın veya doğrulanmamış iddiayı kesin sunmasın.
Hook 6-12 kelime ve videonun ilk cümlesi olsun. Hook + anlatım + abone CTA toplamı 35-65 Türkçe
kelime olsun. CTA Global Haber'e abone olmayı açık ve doğal biçimde istesin.
Açıklama 1-2 özgün cümle olsun; ilk cümlede gelişmeyi ve başlığın bir arama terimini doğal biçimde geçir.
Kaynak dışında bilgi ekleme; etiket listesi veya emoji yazma.
Sadece JSON döndür:
{{"title":"...","hook":"...","narration":"...","cta":"...","description":"..."}}

Kategori: {bucket}
Kaynak başlığı: {source_title}
Kaynak özeti: {source_text[:3000]}
"""
    data = _groq_news_json(prompt)
    title = strip_html(str(data.get("title", ""))).strip(" .-|:")
    hook = strip_html(str(data.get("hook", ""))).strip()
    narration = strip_html(str(data.get("narration", ""))).strip()
    cta = strip_html(str(data.get("cta", ""))).strip()
    description = strip_html(str(data.get("description", ""))).strip()
    script = " ".join(part for part in [hook, narration, cta] if part)
    if not title or len(title) > 78 or not hook or not narration or not cta or not description:
        raise RuntimeError("Groq çıktısı metadata doğrulamasını geçemedi.")
    if not 35 <= len(script.split()) <= 65 or len(hook.split()) > 13:
        raise RuntimeError("Groq metni Shorts uzunluk/hook doğrulamasını geçemedi.")
    item["source_headline"] = source_title
    item["topic_bucket"] = bucket
    item["shorts_hook"] = hook
    item["youtube_description"] = description
    item["title"] = title
    return script




async def create_voiceover(script: str, audio_path: Path) -> list[tuple[float, float, str]]:
    logger.info("Ses oluşturuluyor. Voice=%s Rate=%s Pitch=%s", DEFAULT_VOICE, RATE, PITCH)
    communicate = edge_tts.Communicate(script, DEFAULT_VOICE, rate=RATE, pitch=PITCH)
    word_timestamps: list[tuple[float, float, str]] = []
    with open(audio_path, "wb") as file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_timestamps.append((chunk["offset"] / 10_000_000, chunk["duration"] / 10_000_000, chunk["text"]))

    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Ses dosyası oluşmadı")
    if word_timestamps:
        return word_timestamps

    audio_clip = AudioFileClip(str(audio_path))
    total_duration = max(float(audio_clip.duration), 1.0)
    audio_clip.close()
    words = [word for word in script.split() if word.strip()]
    total_chars = sum(max(len(word), 1) for word in words) or 1
    current = 0.05
    usable_duration = max(total_duration - 0.1, 0.5)
    for word in words:
        duration = max(usable_duration * (max(len(word), 1) / total_chars), 0.16)
        word_timestamps.append((current, duration, word))
        current += duration
    return word_timestamps


def extract_keywords(text: str, count: int = 5) -> list[str]:
    words = [w for w in normalize_text(text).split() if len(w) >= 4]
    stop = {"haber", "dünya", "global", "gündem", "son", "dakika", "için", "olan", "ile", "göre"}
    words = [w for w in words if w not in stop]
    return sorted(set(words), key=len, reverse=True)[:count]


def build_background_queries(item: dict[str, Any]) -> list[str]:
    text = normalize_text(item["title"] + " " + item.get("summary", ""))
    queries: list[str] = []
    for key, mapped in BACKGROUND_HINTS.items():
        if key in text:
            queries.extend(mapped)
    keywords = extract_keywords(item["title"] + " " + item.get("summary", ""))
    if len(keywords) >= 2:
        queries.append(f"{keywords[0]} {keywords[1]} news")
    if keywords:
        queries.append(f"{keywords[0]} global news background")
    queries.extend(["global news background", "world map news", "press conference", "international city skyline"])
    return list(dict.fromkeys(queries))


def search_pexels_video(query: str) -> str | None:
    headers = {"Authorization": PEXELS_API_KEY}
    try:
        response = requests.get(
            "https://api.pexels.com/videos/search",
            headers=headers,
            params={"query": query, "per_page": 10, "orientation": "portrait", "size": "large"},
            timeout=20,
        )
        response.raise_for_status()
        candidates: list[tuple[int, str]] = []
        for video in response.json().get("videos", []):
            for vf in video.get("video_files", []):
                width = int(vf.get("width") or 0)
                height = int(vf.get("height") or 0)
                link = vf.get("link")
                if not link or width <= 0 or height <= 0:
                    continue
                score = width * height + (10_000_000 if height >= width else 0)
                candidates.append((score, link))
        if candidates:
            candidates.sort(reverse=True)
            return candidates[0][1]
    except Exception as exc:
        logger.warning("Pexels arka plan hatası (%s): %s", query, exc)
    return None


def download_background_video(item: dict[str, Any], output_path: Path) -> None:
    url = None
    chosen_query = None
    for query in build_background_queries(item):
        url = search_pexels_video(query)
        if url:
            chosen_query = query
            break
    if not url:
        raise RuntimeError("Uygun Pexels arka plan videosu bulunamadı")
    logger.info("Arka plan seçildi: %s", chosen_query)
    with requests.get(url, stream=True, timeout=90) as response:
        response.raise_for_status()
        with open(output_path, "wb") as file:
            for chunk in response.iter_content(8192):
                if chunk:
                    file.write(chunk)
    if output_path.stat().st_size < 200_000:
        raise RuntimeError("Arka plan videosu çok küçük veya bozuk")


def ensure_font() -> str:
    if FONT_PATH.exists():
        return str(FONT_PATH.resolve())
    FONT_DIR.mkdir(exist_ok=True)
    try:
        with requests.get(FONT_URL, timeout=20) as response:
            response.raise_for_status()
            FONT_PATH.write_bytes(response.content)
        return str(FONT_PATH.resolve())
    except Exception:
        return "Arial-Bold"


def clean_caption_word(word: str) -> str:
    return re.sub(r"[^A-Za-z0-9'\-À-ÖØ-öø-ÿçğıöşüÇĞİÖŞÜ]+", "", str(word)).strip()


def chunk_timestamps(word_ts: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    if not word_ts:
        return []
    chunks: list[tuple[float, float, str]] = []
    current_words: list[str] = []
    chunk_start = word_ts[0][0]
    chunk_end = word_ts[0][0]
    for start, duration, word in word_ts:
        word = clean_caption_word(word)
        if not word:
            continue
        word_end = max(start + duration, start + 0.14)
        projected_duration = word_end - chunk_start
        if current_words and (len(current_words) >= MAX_CAPTION_WORDS or projected_duration > MAX_CAPTION_DURATION):
            chunks.append((chunk_start, max(chunk_end - chunk_start, 0.16), " ".join(current_words)))
            current_words = [word]
            chunk_start = start
            chunk_end = word_end
        else:
            current_words.append(word)
            chunk_end = word_end
    if current_words:
        chunks.append((chunk_start, max(chunk_end - chunk_start, 0.16), " ".join(current_words)))
    fixed: list[tuple[float, float, str]] = []
    for i, (start, duration, text) in enumerate(chunks):
        end = start + duration
        if i + 1 < len(chunks):
            end = min(end, chunks[i + 1][0] - 0.015)
        fixed.append((start, max(end - start, 0.12), text))
    return fixed


def generate_captions(chunked_ts: list[tuple[float, float, str]]) -> list[Any]:
    if not chunked_ts:
        return []
    font = ensure_font()
    clips: list[Any] = []
    for start, duration, text in chunked_ts:
        text = re.sub(r"[^A-Za-z0-9'\-À-ÖØ-öø-ÿçğıöşüÇĞİÖŞÜ ]+", "", text).strip()
        if not text:
            continue
        clip = (
            TextClip(
                text,
                fontsize=FONT_SIZE,
                color="white",
                font=font,
                stroke_color="black",
                stroke_width=STROKE_WIDTH,
                method="caption" if len(text) > 12 else "label",
                size=(VIDEO_SIZE[0] - 180, None),
            )
            .set_start(start)
            .set_duration(duration)
            .set_position(("center", "center"))
        )
        clips.append(clip)
    return clips


def mix_background_music(audio_clip: AudioFileClip, music_path: str = "bg_music.mp3"):
    if not os.path.exists(music_path):
        return None
    try:
        bg = AudioFileClip(music_path).fx(volumex, 0.06)
        bg = audio_loop(bg, duration=audio_clip.duration)
        return CompositeAudioClip([audio_clip, bg])
    except Exception:
        return None


def assemble_video(background_path: Path, audio_path: Path, video_path: Path, word_ts: list[tuple[float, float, str]]) -> None:
    bg_clip = VideoFileClip(str(background_path))
    audio_clip = AudioFileClip(str(audio_path))
    target_duration = audio_clip.duration
    width, height = bg_clip.size
    if width / height < VIDEO_SIZE[0] / VIDEO_SIZE[1]:
        bg_clip = bg_clip.resize(width=VIDEO_SIZE[0])
        bg_clip = crop(bg_clip, y1=(bg_clip.h - VIDEO_SIZE[1]) // 2, y2=(bg_clip.h + VIDEO_SIZE[1]) // 2)
    else:
        bg_clip = bg_clip.resize(height=VIDEO_SIZE[1])
        bg_clip = crop(bg_clip, x1=(bg_clip.w - VIDEO_SIZE[0]) // 2, x2=(bg_clip.w + VIDEO_SIZE[0]) // 2)
    bg_clip = bg_clip.resize(VIDEO_SIZE)
    bg_clip = bg_clip.loop(duration=target_duration) if bg_clip.duration < target_duration else bg_clip.subclip(0, target_duration)
    final_audio = mix_background_music(audio_clip, "bg_music.mp3") or audio_clip
    bg_clip = bg_clip.set_audio(final_audio)
    captions = generate_captions(chunk_timestamps(word_ts))
    final = CompositeVideoClip([bg_clip] + captions, size=VIDEO_SIZE)
    final.write_videofile(str(video_path), codec="libx264", audio_codec="aac", fps=30, preset="medium", threads=4, verbose=False, logger=None)


def load_client_config() -> dict[str, Any]:
    client_secrets_json = os.getenv("CLIENT_SECRETS_JSON")
    if client_secrets_json:
        return json.loads(client_secrets_json)
    if Path(CLIENT_SECRETS_FILE).exists():
        return json.loads(Path(CLIENT_SECRETS_FILE).read_text(encoding="utf-8"))
    raise RuntimeError("CLIENT_SECRETS_JSON bulunamadı")


def get_youtube_service():
    config = load_client_config()
    client_config = config.get("installed") or config.get("web") or next(iter(config.values()))
    credentials = Credentials(
        token=None,
        refresh_token=YOUTUBE_REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_config["client_id"],
        client_secret=client_config["client_secret"],
        scopes=YOUTUBE_SCOPES,
    )
    credentials.refresh(Request())
    return build("youtube", "v3", credentials=credentials)


def compute_publish_times() -> list[datetime]:
    slots = [(7, 0), (12, 0), (18, 0)]
    current = now_tr()
    results: list[datetime] = []
    for hour, minute in slots:
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        results.append(candidate)
    return results


def upload_to_youtube(video_path: Path, item: dict[str, Any], publish_at: datetime) -> dict[str, Any]:
    youtube = get_youtube_service()
    title = item.get("title", "").strip()
    if not title:
        raise RuntimeError("Groq video başlığı üretmedi; yükleme durduruldu.")
    if "#shorts" not in title.lower():
        title = f"{title} #shorts"
    summary = item.get("youtube_description", "").strip()
    if not summary:
        raise RuntimeError("Groq açıklama üretmedi; yedek açıklama kullanılmadan yükleme durduruldu.")
    description = (
        f"{summary}\n\nKaynak: {item.get('source', 'Haber kaynağı')}\n"
        f"Haber bağlantısı: {item.get('url', '')}\n\n#shorts #DünyaHaberleri #GlobalHaber"
    )
    topic_tags = {
        "technology_science": ["teknoloji haberleri", "bilim haberleri"],
        "economy_life": ["dünya ekonomisi", "ekonomi haberleri"],
        "health_education": ["sağlık haberleri", "eğitim haberleri"],
        "climate_energy": ["iklim haberleri", "enerji haberleri"],
        "transport_cities": ["ulaşım haberleri", "şehir haberleri"],
        "culture_arts": ["dünya kültürü", "kültür sanat"],
        "sports": ["dünya spor", "spor haberleri"],
        "disasters_safety": ["dünya gündemi", "afet haberleri"],
        "politics_diplomacy": ["dünya siyaseti", "uluslararası haberler"],
        "society": ["toplum haberleri", "dünya gündemi"],
        "world_affairs": ["dünya haberleri", "uluslararası gündem"],
    }
    tags = ["Global Haber", "dünya haberleri"]
    tags.extend(topic_tags.get(item.get("topic_bucket", "world_affairs"), topic_tags["world_affairs"]))
    seen = {tag.lower() for tag in tags}
    for word in re.findall(r"[a-z0-9çğıöşü]{4,}", normalize_text(title)):
        if word not in seen:
            tags.append(word)
            seen.add(word)
        if len(tags) >= 7:
            break
    body = {
        "snippet": {"title": title[:100], "description": description[:5000], "tags": tags[:7], "categoryId": YOUTUBE_CATEGORY_ID},
        "status": {
            "privacyStatus": "private",
            "publishAt": publish_at.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "selfDeclaredMadeForKids": False,
        },
    }
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            logger.info("YouTube yükleme: %s%%", int(status.progress() * 100))
    video_id = response["id"]
    item["youtube_tags"] = tags[:7]
    return {
        "video_id": video_id,
        "youtube_url": f"https://youtu.be/{video_id}",
        "publish_at_local": publish_at.isoformat(),
        "publish_at_utc": body["status"]["publishAt"],
        "tags": tags[:7],
    }




def build_video_for_item(item: dict[str, Any], index: int) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    audio_path = OUTPUT_DIR / f"voiceover_{index}.mp3"
    background_path = OUTPUT_DIR / f"background_{index}.mp4"
    video_path = OUTPUT_DIR / f"short_{index}.mp4"
    logger.info("Global haber videosu üretiliyor: %s", item["title"])
    word_ts = asyncio.run(create_voiceover(item["script"], audio_path))
    download_background_video(item, background_path)
    assemble_video(background_path, audio_path, video_path, word_ts)
    return {"audio_path": str(audio_path), "background_path": str(background_path), "video_path": str(video_path)}


def update_history(history: dict[str, Any], selected: list[dict[str, Any]]) -> dict[str, Any]:
    history.setdefault("processed_news", [])
    for item in selected:
        history["processed_news"].append({
            "title": item["title"],
            "summary": item.get("summary", ""),
            "url": item["url"],
            "source": item.get("source", ""),
            "published_at": item["published_at"],
            "fingerprint": item["fingerprint"],
            "viral_score": item.get("viral_score"),
            "scheduled_slot": item.get("scheduled_slot"),
            "youtube_url": item.get("youtube_url"),
            "processed_at": now_tr().isoformat(),
        })
    history["processed_news"] = history["processed_news"][-400:]
    return history


def main() -> None:
    logger.info("Global haber botu başladı")
    history = load_json(HISTORY_FILE, {"processed_news": []})
    news_pool = fetch_news_pool(hours_back=20)
    selected = choose_top_three(news_pool, history)
    save_json(SELECTED_FILE, {"generated_at": now_tr().isoformat(), "selected_news": selected})

    for item in selected:
        item["script"] = generate_news_script(item)

    publish_times = compute_publish_times()
    plan_rows = []
    for index, (item, publish_at) in enumerate(zip(selected, publish_times), start=1):
        item["scheduled_slot"] = publish_at.strftime("%H:%M")
        build_info = build_video_for_item(item, index)
        item.update(build_info)
        upload_info = upload_to_youtube(Path(build_info["video_path"]), item, publish_at)
        item.update(upload_info)
        plan_rows.append({
            "index": index,
            "title": item["title"],
            "source_headline": item.get("source_headline", ""),
            "topic_bucket": item.get("topic_bucket", ""),
            "shorts_hook": item.get("shorts_hook", ""),
            "narration": item.get("script", ""),
            "description": item.get("youtube_description", ""),
            "tags": item.get("youtube_tags", []),
            "url": item["url"],
            "viral_score": item["viral_score"],
            "scheduled_slot": item["scheduled_slot"],
            "publish_at_local": upload_info["publish_at_local"],
            "youtube_url": upload_info["youtube_url"],
        })
        logger.info("Planlandı: %s -> %s", item["scheduled_slot"], item["title"])

    save_json(PLAN_FILE, {"generated_at": now_tr().isoformat(), "videos": plan_rows})
    save_json(HISTORY_FILE, update_history(history, selected))
    save_json(SELECTED_FILE, {"generated_at": now_tr().isoformat(), "selected_news": selected})
    logger.info("Tamamlandı. 3 global haber videosu planlandı ve history güncellendi")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.error("Çalışma hatası: %s\n%s", exc, traceback.format_exc())
        sys.exit(1)

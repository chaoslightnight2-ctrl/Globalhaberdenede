"""Runtime integration for the fail-closed Shorts quality gate."""
from __future__ import annotations

import os
import re

import main as bot
from quality_gate import (
    caption_chunks,
    compact,
    validate_caption_timing,
    validate_package,
    validate_rendered_video,
    validate_visual_query,
    tts_text,
)


CHANNEL_NAME = "Global Haber" if "global" in bot.__doc__.lower() else "Türkiye’den Haber"
_original_generate = bot.generate_news_script
_original_voiceover = bot.create_voiceover
_original_build = bot.build_video_for_item
_original_upload = bot.upload_to_youtube


def _split_generated_script(item, raw_script: str):
    if all(item.get(name) for name in ("quality_hook", "quality_narration", "quality_cta")):
        return item["quality_hook"], item["quality_narration"], item["quality_cta"]
    raw = compact(raw_script)
    hook = compact(item.get("shorts_hook", ""))
    remainder = raw
    if hook and remainder.casefold().startswith(hook.casefold()):
        remainder = remainder[len(hook):].lstrip()
    matches = list(re.finditer(r"[^.!?]*(?:abone|takipte kal)[^.!?]*[.!?]?", remainder, re.I))
    if not matches:
        raise ValueError("konuşma metninde ayrı ve tek bir CTA bulunamadı")
    match = matches[-1]
    narration = remainder[:match.start()].strip()
    cta = match.group(0).strip()
    if not narration:
        raise ValueError("haber anlatımı boş")
    return hook, narration, cta


def generate_news_script(item):
    raw = _original_generate(item)
    hook, narration, cta = _split_generated_script(item, raw)
    source_headline = item.get("source_headline", "")
    headline_source = source_headline.rsplit(" - ", 1)[-1] if " - " in source_headline else ""
    checked = validate_package(
        title=item.get("title", ""),
        hook=hook,
        narration=narration,
        cta=cta,
        description=item.get("youtube_description", ""),
        source_text=f"{item.get('source_headline', item.get('title', ''))} {item.get('article_text') or item.get('summary', '')}",
        channel_name=CHANNEL_NAME,
        source_names=(item.get("source_name", ""), headline_source),
    )
    item["shorts_hook"] = checked["hook"]
    item["spoken_text"] = checked["spoken_text"]
    item["tts_text"] = tts_text([hook, *item.get("quality_narration_parts", [narration]), cta])
    item["visual_query"] = validate_visual_query(item.get("visual_query", ""))
    return checked["spoken_text"]


async def create_voiceover(script, audio_path):
    word_ts = await _original_voiceover(script, audio_path)
    audio = bot.AudioFileClip(str(audio_path))
    try:
        duration = float(audio.duration)
    finally:
        audio.close()
    validate_caption_timing(caption_chunks(word_ts), duration)
    return word_ts


def build_video_for_item(item, index):
    spoken = item.get("script", "")
    tts = item.get("tts_text", "")
    if not spoken or not tts:
        raise ValueError("temiz konuşma metni veya TTS metni yok")
    item["script"] = tts
    try:
        result = _original_build(item, index)
    finally:
        item["script"] = spoken
    validate_rendered_video(result["video_path"])
    return result


def upload_to_youtube(video_path, item, publish_at):
    validate_rendered_video(video_path)
    if item.get("script") != item.get("spoken_text"):
        raise ValueError("yükleme öncesi konuşma metni kalite kapısından farklı")
    if os.getenv("DRY_RUN", "0") == "1":
        return _original_upload(video_path, item, publish_at)
    return _original_upload(video_path, item, publish_at)


def build_background_queries(item):
    # A missing exact query is a generation failure. Broad visual fallbacks are
    # deliberately disabled because they produced unrelated countries/subjects.
    return [validate_visual_query(item.get("visual_query", ""))]


bot.generate_news_script = generate_news_script
bot.create_voiceover = create_voiceover
bot.chunk_timestamps = caption_chunks
bot.build_background_queries = build_background_queries
bot.build_video_for_item = build_video_for_item
bot.upload_to_youtube = upload_to_youtube

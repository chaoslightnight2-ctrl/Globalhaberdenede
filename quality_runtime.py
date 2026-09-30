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
    from news_generation import generate
    return generate(item, bot, CHANNEL_NAME)


async def create_voiceover(script, audio_path):
    from voice_sync import synthesize
    word_ts = await synthesize(script, audio_path, bot)
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
        raise ValueError("Upload narration differs from validated text")
    at = publish_at.astimezone(bot.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if os.getenv("DRY_RUN", "0") == "1":
        return {"video_id": "dry-run", "youtube_url": f"DRY-RUN artifact: {video_path}", "publish_at_local": publish_at.isoformat(), "publish_at_utc": at}
    description = item["youtube_description"] + "\n\n" + item["youtube_hashtags"]
    body = {"snippet": {"title": item["title"], "description": description, "tags": item["youtube_tags"], "categoryId": bot.YOUTUBE_CATEGORY_ID},
            "status": {"privacyStatus": "private", "publishAt": at, "selfDeclaredMadeForKids": False}}
    youtube = bot.get_youtube_service()
    request = youtube.videos().insert(part="snippet,status", body=body,
        media_body=bot.MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024))
    response = None
    while response is None:
        _, response = request.next_chunk(num_retries=3)
    video_id = response.get("id")
    if not video_id:
        raise RuntimeError("YouTube insert returned no video ID")
    return {"video_id": video_id, "youtube_url": f"https://youtu.be/{video_id}", "publish_at_local": publish_at.isoformat(), "publish_at_utc": at, "upload_status": "api_insert_confirmed"}


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

from batch_runtime import run as run_batch
bot.main = lambda: run_batch(bot)

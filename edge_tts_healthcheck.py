import asyncio
import os
from pathlib import Path

import edge_tts

VOICE = os.getenv("VOICE", "tr-TR-AhmetNeural")
RATE = os.getenv("VOICE_RATE", "+18%")
PITCH = os.getenv("VOICE_PITCH", "-4Hz")
OUT = Path("edge_tts_healthcheck.mp3")

async def main() -> None:
    if OUT.exists():
        OUT.unlink()
    print(f"Edge TTS healthcheck voice={VOICE} rate={RATE} pitch={PITCH}")
    print(f"edge_tts module={edge_tts.__file__}")
    communicate = edge_tts.Communicate(
        "Bu kısa bir erkek ses testi.",
        VOICE,
        rate=RATE,
        pitch=PITCH,
    )
    word_count = 0
    with open(OUT, "wb") as f:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_count += 1
    if not OUT.exists() or OUT.stat().st_size == 0:
        raise RuntimeError("Edge TTS healthcheck empty audio")
    print(f"Edge TTS OK bytes={OUT.stat().st_size} word_boundaries={word_count}")

if __name__ == "__main__":
    asyncio.run(main())

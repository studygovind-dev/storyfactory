#!/usr/bin/env python3
"""Sends a short Hindi sample of each chosen ElevenLabs voice to Telegram (about 1 minute, a few credits).
Used by the "Test voices" workflow, so no video is made and nothing is posted."""
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import ELEVEN_DEFAULTS, env, load_dotenv  # noqa: E402

LOVE = "उसने कभी नहीं बताया कि वह हर शाम स्टेशन पर इंतज़ार करता था। पर आज, जब वह ट्रेन से उतरी, तो वह सारे शब्द भूल गया।"
SCARY = "रात के बारह बजे थे। दादी के कमरे से आवाज़ आ रही थी, पर दादी तो कब की जा चुकी थीं।"
SAMPLES = [  # (label, voice key, text)
    ("Love-story female (FEMALE_YOUNG)", "HINDI_FEMALE_YOUNG", LOVE),
    ("Normal female narrator", "HINDI_NARRATOR_FEMALE", LOVE),
    ("Deep female, scary stories", "HINDI_NARRATOR_FEMALE_DEEP", SCARY),
    ("Male narrator (current)", "HINDI_NARRATOR_MALE", LOVE),
]


def main():
    load_dotenv()
    key, token, chat = env("ELEVEN_API_KEY"), env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    for label, vk, text in SAMPLES:
        r = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_DEFAULTS[vk]}?output_format=mp3_44100_128",
            headers={"xi-api-key": key},
            json={"text": text, "model_id": "eleven_multilingual_v2",
                  "voice_settings": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.5, "speed": 1.15}}, timeout=120)
        if not r.ok:
            sys.exit(f"ElevenLabs refused {label}: {r.status_code} {r.text[:300]}")
        t = requests.post(f"https://api.telegram.org/bot{token}/sendAudio",
                          data={"chat_id": chat, "title": label, "caption": f"🎙 {label}"},
                          files={"audio": (f"{vk}.mp3", r.content)}, timeout=120)
        t.raise_for_status()
        print("sent", label)


if __name__ == "__main__":
    main()

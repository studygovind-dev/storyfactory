#!/usr/bin/env python3
"""
Writes today's story with Gemini (free tier text model) as 3 episode files:
  series/daily/<date>_part1.json, _part2.json, _part3.json

Each part is about 3 minutes and ends on a cliffhanger, so viewers come back
for the next part later the same day. Past titles are kept in
series/daily/history.txt so stories do not repeat.

Usage:
  python pipeline/write_story.py              # today's date (India time)
  python pipeline/write_story.py 2026-10-27   # a specific date
"""
import datetime, json, os, re, sys, time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import EDGE_VOICES, ROOT, env, load_dotenv  # noqa: E402

DAILY = ROOT / "series" / "daily"
SCENES_PER_PART = 38          # ~4.4 s each at natural pace -> under 3 minutes (Shorts limit)
# Mostly love stories (what viewers connect with most), plus dog and cat stories.
# Rotates one per day: 5 of every 7 days are love stories.
GENRES = [
    "love story: two strangers keep meeting by chance and slowly fall in love",
    "pet story: a loyal dog who waits for its owner and changes a lonely person's life",
    "love story: childhood sweethearts separated for years who meet again",
    "love story: a quiet, shy person secretly in love with a friend, and the moment it is finally said",
    "pet story: a stray cat that brings a broken family back together",
    "love story: a married couple's small daily gestures, and a misunderstanding that tests their love",
    "love story: a long-distance love that survives everything",
]

PROMPT = """You write viral short-drama series for vertical video (YouTube Shorts, Instagram Reels).
Write ONE original story told in exactly 3 parts. Genre today: {genre}.
These stories were already made. Your story must have a DIFFERENT title, DIFFERENT
character names, a DIFFERENT setting and a DIFFERENT twist from every one of them:
{history}

Rules:
- Each part has exactly {n} scenes. Each scene is one picture and one spoken line.
- Scenes come in GROUPS OF 3 (1-3, 4-6, ...): all three share the first scene's picture,
  so the three lines of a group must happen in the same moment and place.
- Keep the story MOVING: something new happens every group. No slow scene-setting.
- The first line of each part is a character speaking (or a gripping question), never a calm
  description. At most 2 narrator lines in a row.
- Each line is 10-18 words, simple English, warm, tender and emotional, like a whispered
  confession. Ordinary, relatable people and everyday places, so viewers feel "this could be me".
- Feelings over action: small gestures, longing looks, first touches of hands, letters, rain,
  waiting. No villains, guns or crime. Romance stays sweet and tasteful (a hug or a kiss at most).
- In pet stories the animal never talks; the narrator and the humans tell its story.
- Mix narrator lines with character dialogue.
- Part 1 and part 2 MUST end on a strong cliffhanger. Part 3 ends with a satisfying payoff.
- The first line of every part must hook the viewer in 3 seconds.
- 2 to 4 characters plus a narrator. Give every character a fixed visual "look":
  name, age, face, hair, clothing, so pictures stay consistent. Lovers are adults.
  A pet character gets a look too (breed, colour, markings, collar) and voice narrator_female.
- "image" describes ONE realistic film shot (who, where, action, light). Refer to characters
  as [[key]] using the character keys you define. No text or signs in the picture.
- "motion" is a short camera/movement note.
- Use only these voice names: {voices}. The narrator uses narrator_male or narrator_female.
- Family friendly enough for YouTube: no gore, no sexual content.

Return ONLY JSON in this exact shape:
{{
  "series": "<catchy series name>",
  "premise": "<one sentence: who, where, what the twist is>",
  "style": "cinematic live-action film still, 35mm, shallow depth of field, realistic skin, natural light, vertical 9:16",
  "characters": {{"<key>": {{"look": "...", "voice": "<voice name>"}}, "narrator": {{"look": "", "voice": "narrator_male"}}}},
  "parts": [
    {{"title": "...", "caption": "<1 line + 3 hashtags>",
     "yt_title": "<YouTube title under 90 characters: emotional hook + 'Part N'>",
     "description": "<2-3 short lines that tease the story without spoiling the twist>",
     "hashtags": ["<15 popular hashtags for this genre, mix broad (#shorts #drama #story) and specific>"],
     "scenes": [{{"image": "...", "motion": "...", "speaker": "<character key>", "line": "..."}}]}},
    {{...part 2...}},
    {{...part 3...}}
  ]
}}"""


def ask_gemini(prompt):
    model = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
    for attempt in range(6):  # Gemini is sometimes "overloaded" for a few minutes; wait and retry
        try:
            r = requests.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                headers={"x-goog-api-key": env("GEMINI_API_KEY")},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseMimeType": "application/json", "temperature": 1.0}},
                timeout=300)
        except requests.RequestException as e:
            print(f"Gemini connection error ({type(e).__name__}), retrying...", flush=True)
        else:
            if r.ok:
                return json.loads(r.json()["candidates"][0]["content"]["parts"][0]["text"])
            if r.status_code not in (429, 500, 502, 503, 504):
                sys.exit(f"Gemini error {r.status_code}: {r.text[:800]}")
            print(f"Gemini busy ({r.status_code}), retrying...", flush=True)
        time.sleep(30 * (attempt + 1))
    sys.exit("Gemini stayed busy for 10 minutes; the next scheduled run will try again.")


def check(story, history):
    """Return a list of problems; empty means the story is usable."""
    errs = []
    used = {h.split(" | ")[0].strip().lower() for h in history}
    if story.get("series", "").strip().lower() in used:
        errs.append(f"title '{story.get('series')}' was already used")
    chars = story.get("characters", {})
    if len(story.get("parts", [])) != 3:
        errs.append("needs exactly 3 parts")
    for k, c in chars.items():
        if c.get("voice") not in EDGE_VOICES:
            c["voice"] = "narrator_male" if k == "narrator" else "male_deep"  # repair, not fail
    for p in story.get("parts", []):
        if not SCENES_PER_PART - 5 <= len(p.get("scenes", [])) <= SCENES_PER_PART + 1:
            errs.append(f"part '{p.get('title')}' has {len(p.get('scenes', []))} scenes")
        for s in p.get("scenes", []):
            if s.get("speaker") not in chars:
                errs.append(f"unknown speaker {s.get('speaker')}")
            for name in re.findall(r"\[\[(\w+)\]\]", s.get("image", "")):
                if name not in chars:
                    errs.append(f"unknown character [[{name}]]")
    return errs


def main():
    load_dotenv()
    day = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date().isoformat())
    DAILY.mkdir(parents=True, exist_ok=True)
    if (DAILY / f"{day}_part1.json").exists():
        print(f"Story for {day} already written.")
        return
    hist_file = DAILY / "history.txt"
    history = hist_file.read_text(encoding="utf-8").splitlines() if hist_file.exists() else []
    genre = GENRES[datetime.date.fromisoformat(day).toordinal() % len(GENRES)]
    prompt = PROMPT.format(genre=genre, history="\n".join("- " + h for h in history[-90:]) or "none",
                           n=SCENES_PER_PART, voices=", ".join(EDGE_VOICES))

    for attempt in range(3):
        story = ask_gemini(prompt)
        errs = check(story, history)
        if not errs:
            break
        print(f"Story had problems ({'; '.join(errs[:3])}), asking again...")
    else:
        sys.exit("Gemini could not write a valid story after 3 tries.")

    story_no = len(history) + 1  # running count shown as "Story #N"
    for n, part in enumerate(story["parts"], 1):
        tags = [t if t.startswith("#") else "#" + t
                for t in (part.get("hashtags") or []) if isinstance(t, str) and t.strip()]
        ep = {"series": story["series"], "episode": n, "title": part["title"],
              "style": story["style"], "characters": story["characters"],
              "scenes": part["scenes"], "caption": part["caption"],
              "slug": f"{day}_part{n}", "story_no": story_no, "parts": 3,
              "yt_title": part.get("yt_title") or f"{story['series']} - Part {n}",
              "description": part.get("description", ""),
              "hashtags": [t.replace(" ", "") for t in tags][:20]}
        (DAILY / f"{day}_part{n}.json").write_text(json.dumps(ep, indent=1, ensure_ascii=False),
                                                   encoding="utf-8")
    entry = f"{story['series']} | {day} | {story.get('premise', '').strip()}"
    hist_file.write_text("\n".join(history + [entry]) + "\n", encoding="utf-8")
    print(f"Wrote {story['series']} ({day}), 3 parts.")


if __name__ == "__main__":
    main()

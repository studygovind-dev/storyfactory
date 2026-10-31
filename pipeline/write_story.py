#!/usr/bin/env python3
"""
Writes today's 3 short videos with Gemini (free tier text model):
  series/daily/<date>_part1.json  9 AM  realistic animal + human story in English
  series/daily/<date>_part2.json  1 PM  funny cartoon story in Hinglish
  series/daily/<date>_part3.json  5 PM  realistic emotional story in Hinglish (English subtitles)

Each video is ONE complete story of about 3.5-4 minutes: a hook in the first second,
fast picture changes, one narrator, and a twist at the end. Past titles are
kept in series/daily/history.txt so stories do not repeat.

Usage:
  python pipeline/write_story.py              # today's date (India time)
  python pipeline/write_story.py 2026-10-27   # a specific date
"""
import datetime, json, os, re, sys, time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import ROOT, env, load_dotenv  # noqa: E402

DAILY = ROOT / "series" / "daily"
SCENES = 70                 # one line each, about 3 s -> 3.5-4 minute videos

CARTOON_STYLE = ("3D animated movie still in the style of a Pixar film, cute expressive characters with big "
                 "eyes, exaggerated funny facial expressions, vibrant colors, soft cinematic lighting, vertical 9:16")
REAL_STYLE = ("cinematic live-action film still, 35mm, shallow depth of field, realistic skin, "
              "natural light, emotional mood, vertical 9:16")

# Funny cartoon topics: a different one each day so all kinds of viewers are covered.
FUNNY_TOPICS = [
    "a lazy cat who outsmarts the whole family to get food",
    "husband and wife: a tiny argument that gets hilariously out of hand",
    "a kid's school excuse that gets bigger and bigger",
    "an office employee trying to secretly nap during a meeting",
    "a dog who is scared of a very small thing",
    "a strict grandma using a smartphone for the first time",
    "a friend who always says 'just 5 minutes' and is always late",
    "a diet that fails in the funniest way",
    "a parrot that repeats exactly the wrong thing at the wrong time",
    "a student the night before an exam",
    "a delivery guy and a very confusing address",
    "siblings fighting over the TV remote",
    "a wedding where everything goes funny-wrong",
    "a gym first day disaster",
    "a babysitter who can understand baby talk: the baby is secretly the boss of the house",
    "a talking pet cat who complains about the family all day",
    "a baby dragon adopted by an Indian family causes chaos in the kitchen",
    "a dog who can talk only to grandpa, and nobody believes him",
]

# Animal + human stories: easy to follow even without understanding the words.
ANIMAL_TOPICS = [
    "a tiger mother leaves her blind cub with a pregnant village woman, who gets its eyes treated; "
    "the cub and her baby grow up together, and years later the tigress returns to thank her",
    "a lion cub raised by a farmer returns as a grown lion and recognises him years later",
    "a wolf saves a lost child in the snowy forest and leads the rescuers to her",
    "an elephant never forgets the man who freed her from a trap and comes back to save his village",
    "a giant python and a lonely boy: everyone is afraid until the python saves the family",
    "a street dog follows an old woman every day until the day she needs him most",
    "a monkey steals a baby's milk bottle, then comes back with something surprising",
    "an injured eagle nursed back to health by a girl returns every year on the same day",
    "a horse that was going to be sold saves its owner's daughter from a flood",
    "a mother cat brings her kittens one by one to the woman who once fed her",
    "a bear cub separated from its mother and the forest ranger who reunites them",
    "a cow and a farmer's son: the boy sells her to pay for school, she walks back home miles away",
    "a dolphin helps a fisherman's son lost at sea",
    "an abandoned puppy and an old soldier who lost his family",
    "a young nanny who can understand what babies and animals say: a baby dragon tells her why it cries",
    "a girl who can hear animals talk: the zoo's sad old lion tells her his secret",
    "a lonely boy discovers the stray dog he feeds can talk, and it warns him of danger",
    "a forest ranger who understands animal language becomes famous after saving a wolf pack",
]

# Most watched realistic story types on Shorts / Reels (emotional, twist ending, karma, kindness).
REAL_TOPICS = [
    "kindness rewarded: someone helps a stranger who turns out to be important",
    "a parent's hidden sacrifice the child only discovers years later",
    "karma: a rude, arrogant person gets humbled in a satisfying way",
    "a love story with a twist ending",
    "a loyal dog who never gave up on its owner",
    "a poor student's struggle and a surprise ending",
    "a marriage misunderstanding that turns into a heart-touching truth",
    "an old man alone, and the stranger who changed his life",
    "a cheating partner and the clever way the truth came out",
    "a teacher who changed one student's life",
    "a stray cat that saved a family",
    "a rich boy pretending to be poor to find true love",
    "a daughter-in-law and mother-in-law: from enemies to family",
    "a waiter judged by customers, then the twist",
]

PROMPT = """You write viral YouTube Shorts / Instagram Reels stories that people watch to the end and rewatch.
Write ONE complete story for a 3.5-4 minute video. {kind}
Topic: {topic}
These stories were already made. Use a DIFFERENT title, names, setting and twist:
{history}

Rules:
- Exactly {n} scenes. Each scene is one picture and one spoken line. A new picture every line.
- The whole story is 550-650 spoken words. Each line 6-11 words. Simple, gripping {lang}.
- LINE 1 IS THE HOOK: a shocking, curious or funny statement that makes people stop scrolling
  (examples: "My dog stole my wedding ring.", "Everyone laughed at the waiter. Big mistake.").
- Structure: hook -> quick setup -> problem -> 2-3 turns that raise the stakes (a mini cliffhanger
  every 30-40 seconds so nobody leaves) -> the big twist -> payoff -> one strong closing line.
- The last line asks viewers a short question to comment on, or lands the punchline.
- {speech}
- Each scene has a "speaker": "narrator" or a character key. Spoken lines are just the words,
  no quote marks, no "he said".
- Family friendly: no gore, no sexual content.
- 1 to 3 characters. Give each a fixed visual "look" (age, face, hair, clothing; for animals breed,
  colour, collar) so pictures stay consistent. Refer to them in "image" as [[key]].
- "image" describes ONE {shot} (who, where, action, emotion on the face). No text or signs.
- SILENT-MOVIE TEST: the story must be easy to follow with the sound OFF, even for someone who
  does not know the language. Every picture shows exactly what is happening: a clear action,
  big readable emotions (tears, shock, laughter, anger), meaningful objects (a letter, a ring,
  an empty chair), close-ups at emotional moments. The FIRST picture must be dramatic and
  instantly intriguing.{sub_rule}
- "hook_text": 2-5 words shown big on screen in the first seconds (e.g. "SHE LEFT A NOTE...").
- Pick each voice so it matches who is speaking: {voices}{talk_rule}
- Each scene has "fx": the weather/atmosphere layer for that picture: rain, snow, dust
  (sunbeams, warm floating dust, fireflies, magic) or none. Use it where it adds feeling.

Return ONLY JSON:
{{
  "title": "<catchy title>",
  "premise": "<one sentence: who, what, the twist>",
  "hook_text": "...",
  "characters": {{"narrator": {{"look": "", "voice": "..."}}, "<key>": {{"look": "...", "voice": "..."}}}},
  "yt_title": "<title under 70 characters: a specific emotional hook with the key searchable words
               (e.g. 'Rich Customer Insulted the Waiter... Then He Saw His Name Tag'), 1 emoji at most, no ALL CAPS>",
  "description": "<3 short lines: line 1 repeats the hook with searchable words, line 2 teases the twist
                  without spoiling it, line 3 asks the viewers' comment question>",
  "comment_question": "<one short question viewers will want to answer, e.g. 'Would you have forgiven her?'>",
  "hashtags": ["<12 hashtags: 3 broad (#story #emotionalstory #storytime), the rest specific to this
               story's topic and feelings. NO #shorts (the videos are 3-4 minutes long)>"],
  "scenes": [{{"image": "...", "speaker": "<narrator or character key>", "line": "..."{sub_field}, "fx": "<rain|snow|dust|none>"}}]
}}"""

SUB_RULE = """
- Each scene also has "sub": a short, natural ENGLISH translation of the line (shown as subtitles).
  "title", "hook_text", "yt_title" and "description" are in English (Hindi words in English letters are OK)."""

TALK_RULE = """
- Animals and babies MAY talk (people love this): give a talking animal or baby the voice
  cartoon_male or cartoon_female (cute child-like voice). No roars or animal-noise lines."""

CARTOON_VOICES = {
    "narrator_male": "male storyteller (narrator)", "narrator_female": "female storyteller (narrator)",
    "cartoon_male": "funny cartoon voice for boys, kids and male animals (parrot, dog, cat...)",
    "cartoon_female": "funny cartoon voice for girls, baby girls and female animals",
}
REAL_VOICES = {
    "narrator_male": "male storyteller around 30 (narrator)",
    "narrator_female": "female storyteller (narrator)",
    "male_young": "man in his 20s", "female_young": "woman in her 20s",
    "cartoon_male": "cute child-like voice for a talking animal, baby or little boy",
    "cartoon_female": "cute child-like voice for a talking animal, baby or little girl",
}


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


def check(story, used, voices):
    """Return a list of problems; empty means the story is usable."""
    errs = []
    if story.get("title", "").strip().lower() in used:
        errs.append(f"title '{story.get('title')}' was already used")
    chars = story.setdefault("characters", {})
    chars.setdefault("narrator", {"look": ""})
    for k, c in chars.items():
        if c.get("voice") not in voices:  # repair, not fail
            c["voice"] = "narrator_male" if k == "narrator" else next(iter(voices))
    for s in story.get("scenes", []):
        if s.get("speaker") not in chars:
            s["speaker"] = "narrator"
    if not SCENES - 10 <= len(story.get("scenes", [])) <= SCENES + 8:
        errs.append(f"has {len(story.get('scenes', []))} scenes")
    for s in story.get("scenes", []):
        for name in re.findall(r"\[\[(\w+)\]\]", s.get("image", "")):
            if name not in chars:
                errs.append(f"unknown character [[{name}]]")
    return errs


def slots(day):
    """What each of today's 3 videos should be."""
    d = datetime.date.fromisoformat(day).toordinal()
    real = {"style": REAL_STYLE, "shot": "realistic film shot", "lang": "English", "voices": REAL_VOICES,
            "speech": ("Mostly ONE narrator telling it (first person 'I' works best), with a few short "
                       "emotional lines spoken by the characters at key moments.")}
    return [
        {"kind": ("It is an emotional, realistic ANIMAL + HUMAN story (wild or pet animal and people), "
                  "told mostly through pictures so anyone in the world can follow it."),
         "topic": ANIMAL_TOPICS[d % len(ANIMAL_TOPICS)], **real, "mood": "animal"},
        {"kind": "It is a FUNNY cartoon story: light, silly, relatable comedy with a punchline at the end.",
         "topic": FUNNY_TOPICS[d % len(FUNNY_TOPICS)], "style": CARTOON_STYLE,
         "shot": "frame of a 3D animated movie", "voices": CARTOON_VOICES,
         "speech": ("The characters TALK: most lines are the characters speaking (funny back-and-forth), "
                    "a narrator line now and then to move the story on."),
         "hindi_voices": True, "mood": "funny",
         "lang": ("Hinglish (Hindi written in English letters, mixed with English words, the way young "
                  "Indians talk, e.g. 'Bhai, yeh kya ho gaya?')")},
        {"kind": "It is an emotional, realistic story with a twist ending, set in India with Indian characters.",
         "topic": REAL_TOPICS[(2 * d + 1) % len(REAL_TOPICS)], **real, "hindi": True,
         "lang": ("Hinglish (Hindi written in English letters, mixed with English words, the way "
                  "Indians really talk, e.g. 'Maa, main sach bol raha hoon, please trust me.')")},
    ]


def main():
    load_dotenv()
    day = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date().isoformat())
    DAILY.mkdir(parents=True, exist_ok=True)
    if (DAILY / f"{day}_part1.json").exists():
        print(f"Stories for {day} already written.")
        return
    hist_file = DAILY / "history.txt"
    history = hist_file.read_text(encoding="utf-8").splitlines() if hist_file.exists() else []

    eps = []  # written together at the end, so a failed run never leaves half a day
    for n, slot in enumerate(slots(day), 1):
        used = {h.split(" | ")[0].strip().lower() for h in history}
        prompt = PROMPT.format(kind=slot["kind"], topic=slot["topic"], lang=slot["lang"],
                               shot=slot["shot"], n=SCENES, speech=slot["speech"],
                               voices="; ".join(f"{k} = {v}" for k, v in slot["voices"].items()),
                               sub_rule=SUB_RULE if slot.get("hindi") else "", talk_rule=TALK_RULE,
                               sub_field=', "sub": "<English translation>"' if slot.get("hindi") else "",
                               history="\n".join("- " + h for h in history[-90:]) or "none")
        for attempt in range(3):
            story = ask_gemini(prompt)
            errs = check(story, used, slot["voices"])
            if not errs:
                break
            print(f"Story {n} had problems ({'; '.join(errs[:3])}), asking again...")
        else:
            sys.exit(f"Gemini could not write story {n} after 3 tries.")

        chars = {k: {"look": c.get("look", ""), "voice": c["voice"]} for k, c in story["characters"].items()}
        tags = [t if t.startswith("#") else "#" + t
                for t in (story.get("hashtags") or []) if isinstance(t, str) and t.strip()]
        if slot.get("hindi") or slot.get("hindi_voices"):  # Hinglish lines: Hindi voices
            for c in chars.values():
                c["voice"] = "hindi_" + c["voice"]
        ep = {"series": story["title"], "episode": n, "title": story["title"],
              "style": slot["style"], "characters": chars, "short": True,
              "mood": slot.get("mood", "emotional"),
              "hook_text": story.get("hook_text", ""),
              "scenes": [{"image": s["image"], "speaker": s["speaker"], "line": s["line"],
                          "fx": s.get("fx") if s.get("fx") in ("rain", "snow", "dust") else "none",
                          **({"sub": s["sub"]} if s.get("sub") else {})} for s in story["scenes"]],
              "caption": story.get("yt_title", ""), "slug": f"{day}_part{n}",
              "story_no": len(history) + 1,
              "yt_title": story.get("yt_title") or story["title"],
              "description": story.get("description", ""),
              "comment_question": story.get("comment_question", ""),
              "hashtags": [t.replace(" ", "") for t in tags][:20]}
        eps.append(ep)
        history.append(f"{story['title']} | {day} | {story.get('premise', '').strip()}")
        print(f"Story {n}: {story['title']}")
    for ep in eps:
        (DAILY / f"{ep['slug']}.json").write_text(json.dumps(ep, indent=1, ensure_ascii=False),
                                                  encoding="utf-8")
    hist_file.write_text("\n".join(history) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

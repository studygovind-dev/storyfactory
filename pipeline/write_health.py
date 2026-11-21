#!/usr/bin/env python3
"""
Money Mind Health: funny "talking food / body part" health videos, about 55 seconds each.

Writes series/health/<date>_h<N>.json (N = 1..MMH_PER_DAY, default 5) with Gemini. Each video:
  - 2-3 cartoon characters (a food or a body part) that speak to the viewer in street-style Hindi,
  - 6 groups of 3 lines (one picture per group), the speaking character's name shown on screen,
  - safe, general wellness facts only (no cures), a funny hook and a question to comment on.

Usage: python pipeline/write_health.py [YYYY-MM-DD]
"""
import datetime, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import ROOT, load_dotenv  # noqa: E402
from write_story import ask_gemini  # noqa: E402

HEALTH = ROOT / "series" / "health"
PER_DAY = max(1, min(6, int(os.environ.get("MMH_PER_DAY", "5") or 5)))
GROUPS = 6  # 6 pictures x 3 lines = 18 lines, about 55 seconds

STYLE = ("3D animated movie still in the style of a Pixar film, a glossy cute character with big expressive eyes "
         "and a small headband, hyper-detailed macro close-up, cinematic soft lighting, rich colours, "
         "vertical 9:16")

# (subject, the safe, general facts the character may use)
SUBJECTS = [
    ("Namak (salt)", "tastes great in small amounts; too much can raise blood pressure; keep it modest, skip extra salt on food"),
    ("Chini (sugar)", "gives quick energy; too much means weight gain and high blood sugar; hidden in chai, cold drinks, biscuits"),
    ("Cold drink", "a bottle holds many spoons of sugar; water, nimbu paani or chaas are better daily choices"),
    ("Maida", "refined flour has little fibre; whole wheat atta and millets keep you full longer"),
    ("Tel (cooking oil)", "needed in small amounts; too much deep-fried food is heavy for the heart; bake, roast or steam sometimes"),
    ("Chai", "fine in moderation; many sugary cups a day add up; try less sugar"),
    ("Kaddu ke beej (pumpkin seeds)", "have zinc and magnesium; a small handful is good; they are calorie-dense so do not overeat"),
    ("Badam (almonds)", "healthy fats and protein; a small handful a day; soaked or plain"),
    ("Haldi (turmeric)", "a common cooking spice; part of healthy Indian food; not a cure for any disease"),
    ("Amla", "rich in vitamin C; eaten fresh, as murabba or juice without lots of sugar"),
    ("Nimbu paani", "refreshing and hydrating; vitamin C; keep the sugar low"),
    ("Paani (water)", "tiredness and headaches can sometimes be from too little water; sip through the day"),
    ("Dahi (curd)", "has protein and friendly bacteria; good with meals; choose plain over sugary ones"),
    ("Moong aur chana", "protein and fibre; sprouts or boiled make a simple healthy snack"),
    ("Instant noodles", "usually high in salt and low in fibre; fine once in a while, not every day"),
    ("Chips aur namkeen", "high in salt and oil; a small bowl is okay; do not finish the packet"),
    ("Ghee", "good in small amounts; a spoon is enough; too much adds calories quickly"),
    ("Kela (banana)", "easy energy, potassium and fibre; a handy snack before a walk"),
    ("Papita (papaya)", "has fibre and vitamin C; a light, easy fruit for the morning"),
    ("Methi dana", "has fibre; soaked in water is a traditional kitchen habit; not a medicine"),
    ("Jeera aur ajwain", "kitchen spices traditionally used after heavy meals; a warm cup is comforting, not a cure"),
    ("Pet (stomach)", "heavy late-night food and eating too fast make it uncomfortable; eat slowly, early dinner"),
    ("Dil (heart)", "likes a 30 minute daily walk, less salt and less stress; check-ups matter after 30-40"),
    ("Aankhein (eyes)", "get tired from screens; the 20-20-20 habit: every 20 minutes look 20 feet away for 20 seconds"),
    ("Neend (sleep)", "most adults need 7-8 hours; phone in bed steals sleep; keep a fixed bedtime"),
    ("Kidney", "like enough water and not too much salt; do not hold the urge for long"),
    ("Rirh ki haddi (spine)", "hates long slouching; stand up every hour, sit straight, light stretching"),
    ("Dimaag (brain)", "works better with sleep, water and short breaks; stress piles up if you never pause"),
    ("Fefde (lungs)", "love deep breathing and fresh air; five slow deep breaths can calm you"),
    ("Daant (teeth)", "need brushing twice a day; sugary snacks are their enemy; rinse after sweets"),
    ("Tvacha (skin)", "likes water, sleep and sunscreen; no cream replaces sleep"),
    ("Yoga: Tadasana (mountain pose)", "stand tall, feet together, arms up; good for posture; a gentle beginner stretch"),
    ("Yoga: Bhujangasana (cobra pose)", "lie on the stomach, lift the chest slowly; gentle back stretch for beginners; do not force it"),
    ("Yoga: Anulom Vilom (breathing)", "slow alternate-nostril breathing for 5 minutes; feels calming; no medical claims"),
    ("Yoga: Vrikshasana (tree pose)", "balance on one leg; builds focus; hold a wall at first"),
]

PROMPT = """You write funny, useful 55-second Reels for the Facebook Page "Money Mind Health".
FORMAT: a "talking character" health video. The subject below is a cartoon character that talks to the viewer
in first person, like: "Arre main namak hoon! Thoda daalega toh swaad bhi doonga, zyada daalega toh BP bhi
badhaaunga!" (A friendly body-part or food character, plus 1-2 other characters if it makes it funnier.)
SUBJECT: {subject}
SAFE FACTS the characters may use (stay inside them, add nothing risky): {facts}

Rules:
- Exactly 18 scenes in 6 GROUPS of 3 lines. The SAME character speaks all 3 lines of a group (one picture per
  group). 2-3 characters in total; the first line of the video is a funny, loud hook from the subject.
- Language: funny street-style (tapori) Hindi: short punchy lines, words like "arre bhai", "bhidu", "bole toh",
  "lafda", "ekdum", "tension nahi lene ka", "sahi pakde hain". Mostly Hindi words. Each line 6-12 words.
- "say" = the line in Devanagari exactly as spoken, real Hindi words, NEVER English words spelled in Devanagari
  (allowed loanwords: बीपी, शुगर, डॉक्टर, फ़ोन, चाय, योग). "line" = the SAME words in English letters.
- Accuracy and safety: only general wellness advice. Never say it cures or prevents a disease. Use "can", "may",
  "zyada khane se". End with a moderation tip. One line should say to see a doctor if there is a health problem.
- Every character states who it is in its first group, gives one benefit or risk and one simple tip.
- The LAST group ends with a question that makes people comment ("Aap din mein kitni chai peete ho?").
- "tag": the speaker's name in short ENGLISH letters, capitals, e.g. "NAMAK BHAI", "PET BHAI", "CHINI DIDI".
- "image": describe the speaking character in the scene (expression, pose, setting). Put [[key]] where the
  character appears. Each group's 3 scenes use the SAME image description. No text in the picture.
- Characters: each has "look" (a fixed visual description: colour, material, face, headband) and a "voice" from:
  hindi_cartoon_male (small, cute), hindi_cartoon_female (cute, high), hindi_male_deep (gruff, heavy),
  hindi_male_young (lively, young man). Give different characters different voices.
- hook_text: 2-5 English words shown at the start (a curious or funny shout).
- "title", "hook_text", "yt_title", "description", "comment_question" and hashtags are in English / roman letters.
- Family friendly, funny, never scary or disgusting.
These titles were already made. Choose a different title and jokes:
{history}

Return ONLY JSON:
{{"title": "", "hook_text": "",
  "characters": {{"<key>": {{"look": "", "voice": "", "name": ""}}}},
  "yt_title": "<under 70 characters, curious, with the subject name>",
  "description": "<2 short lines>",
  "comment_question": "<a question in Hinglish roman letters that makes people answer>",
  "hashtags": ["<5 hashtags specific to this topic>"],
  "scenes": [{{"image": "", "speaker": "<character key>", "line": "", "say": "", "tag": "", "fx": "none"}}]}}"""

VOICES = ("hindi_cartoon_male", "hindi_cartoon_female", "hindi_male_deep", "hindi_male_young")
TAGS = ["#healthtips", "#healthfacts", "#sehat", "#swasthya", "#hindihealth", "#healthyfood", "#funnyhealth",
        "#reelsindia", "#viralreels", "#facebookreels", "#स्वास्थ्य", "#सेहत"]
DISCLAIMER = "Educational only. Not medical advice. See a doctor if you have a health problem."


def check(story, used):
    errs = []
    if story.get("title", "").strip().lower() in used:
        errs.append("title already used")
    scenes = story.get("scenes") or []
    if len(scenes) != GROUPS * 3:
        errs.append(f"has {len(scenes)} scenes, needs {GROUPS * 3}")
    chars = story.get("characters") or {}
    if not 1 <= len(chars) <= 4:
        errs.append("needs 2-3 characters")
    for c in chars.values():
        if c.get("voice") not in VOICES:
            c["voice"] = VOICES[0]
    for sc in scenes:
        if sc.get("speaker") not in chars:
            errs.append(f"unknown speaker {sc.get('speaker')}")
            break
        if not sc.get("say") or not sc.get("line"):
            errs.append("a scene has no line")
            break
    bad = re.compile(r"(वाज़?|रॉन्ग|राइट|बेबी|टाइम|सडनली|रिमोट|प्लीज़?|सॉरी|ओके|फ़ीलिंग|सरप्राइज़?|गुड|बैड|नो\b|यस\b)")
    if len([m for sc in scenes for m in bad.findall(sc.get("say", ""))]) > 2:
        errs.append("English words spelled in Devanagari")
    return errs


def make_one(day, n, history):
    d = datetime.date.fromisoformat(day).toordinal()
    subject, facts = SUBJECTS[(d * PER_DAY + n) % len(SUBJECTS)]
    used = {h.split(" | ")[0].strip().lower() for h in history}
    prompt = PROMPT.format(subject=subject, facts=facts,
                           history="\n".join("- " + h.split(" | ")[0] for h in history[-80:]) or "none")
    for attempt in range(3):
        story = ask_gemini(prompt)
        errs = check(story, used)
        if not errs:
            break
        print(f"Health video {n} had problems ({'; '.join(errs[:3])}), asking again...")
    else:
        sys.exit(f"Gemini could not write health video {n} after 3 tries.")
    scenes = story["scenes"]
    for g in range(GROUPS):  # one picture per group of 3: same speaker, same picture
        first = scenes[3 * g]
        for sc in scenes[3 * g: 3 * g + 3]:
            sc["speaker"], sc["image"] = first["speaker"], first["image"]
            if not sc.get("tag"):
                sc["tag"] = story["characters"][first["speaker"]].get("name", "").upper()
    chars = {k: {"look": c.get("look", ""), "voice": c["voice"]} for k, c in story["characters"].items()}
    tags = [t if t.startswith("#") else "#" + t for t in story.get("hashtags", []) if isinstance(t, str)]
    all_tags = []
    for t in tags[:5] + TAGS:
        t = t.replace(" ", "")
        if t and t.lower() not in [x.lower() for x in all_tags]:
            all_tags.append(t)
    all_tags = all_tags[:15]
    title = story["title"]
    caption = (f"{story.get('yt_title') or title}\n\n{story.get('description', '').strip()}\n\n"
               f"{story.get('comment_question', '')}\n\n{DISCLAIMER}\n\n"
               "Follow Money Mind Health for a fun health tip every day!\n\n" + " ".join(all_tags))[:2100]
    ep = {"series": title, "episode": n, "title": title, "style": STYLE, "characters": chars, "short": True,
          "mood": "funny", "hook_text": story.get("hook_text", ""),
          "scenes": [{"image": s["image"], "speaker": s["speaker"], "line": s["line"], "say": s["say"],
                      "tag": s.get("tag", ""), "fx": "none"} for s in scenes],
          "caption": story.get("yt_title", title), "slug": f"{day}_h{n}", "story_no": len(history) + 1,
          "yt_title": story.get("yt_title") or title, "description": story.get("description", ""),
          "comment_question": story.get("comment_question", ""), "hashtags": all_tags,
          "caption_text": caption,
          "telegram_caption": f"🥗 Money Mind Health · video {n}\n{title}"}
    return ep


def main():
    load_dotenv()
    day = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date().isoformat())
    HEALTH.mkdir(parents=True, exist_ok=True)
    todo = [n for n in range(1, PER_DAY + 1) if not (HEALTH / f"{day}_h{n}.json").exists()]
    if not todo:
        print(f"Health videos for {day} already written.")
        return
    hist_file = HEALTH / "history.txt"
    history = hist_file.read_text(encoding="utf-8").splitlines() if hist_file.exists() else []
    eps = []
    for n in todo:
        ep = make_one(day, n, history)
        eps.append(ep)
        history.append(f"{ep['title']} | {day} | h{n}")
        print(f"Health video {n}: {ep['title']}")
    for ep in eps:
        (HEALTH / f"{ep['slug']}.json").write_text(json.dumps(ep, indent=1, ensure_ascii=False), encoding="utf-8")
    hist_file.write_text("\n".join(history) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Writes today's 3 short videos with Gemini (free tier text model):
  series/daily/<date>_part1.json  9 AM  realistic animal + human story in Hinglish (English subtitles)
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
SCENES = 16                 # one line each, about 3 s -> 45-55 second Reels (saves ElevenLabs credits)

CARTOON_STYLE = ("3D animated movie still in the style of a Pixar film, cute expressive characters with big "
                 "eyes, exaggerated funny facial expressions, vibrant colors, soft cinematic lighting, vertical 9:16")
REAL_STYLE = ("cinematic film still, shot on ARRI Alexa with a 40mm anamorphic lens, dramatic motivated lighting "
              "with a soft rim light, rich warm-and-teal colour grade, fine film grain, shallow depth of field, "
              "moody atmosphere, beautiful young Indian people with clear natural light wheatish skin, "
              "expressive emotional faces and sharp detailed eyes, vertical 9:16")

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

LOVE_TOPICS = [
    "a quiet love story with a twist: the letters she kept getting were written by someone she knew",
    "two strangers keep missing each other at the same railway station, until one rainy evening",
    "she rejects an arranged-marriage proposal, then finds out who he really is",
    "a love that waited ten years and the one phone call that changed everything",
    "a shy boy and the girl who sits next to him on the bus every day",
    "a wedding called off at the last minute, and the person who stood up in the crowd",
    "a husband secretly learns to cook for his sick wife; she finds out in the end",
    "an old couple's anniversary and the surprise only the grandfather remembers",
    "a rich boy pretending to be poor to find true love",
    "a long-distance love story that ends at an airport",
    "a girl finds an old diary and falls for the boy who wrote it",
    "her mother-in-law was against the love marriage, until one night in the hospital",
]


# Every seed below is a COMPLETE plot (setup -> problem -> turning point -> ending), so the story always
# makes sense. "Classic" seeds are public-domain stories (Panchatantra, Premchand, Akbar-Birbal and
# Nasruddin folk tales): free to retell in our own words.
LOVE_PLOTS = [
    "Meera gets anonymous letters that give her courage to open her tailoring shop. On opening day she "
    "learns the writer is old postman Raghu kaka, who lost his own daughter and wrote to feel less alone. "
    "She makes him the guest of honour and he becomes her family.",
    "A girl leaves an umbrella on a station bench every rainy day for anyone who needs it. A boy keeps "
    "borrowing it and leaves a thank-you note each time. After a month she hides to see him. They finally "
    "meet and share the one umbrella.",
    "Riya refuses Aman's arranged-marriage proposal because she wants a career. Aman secretly loves her "
    "sketches, tells his family he will wait, and quietly helps her get her first exhibition. At the "
    "exhibition she finds out it was him and chooses him because he backed her dream.",
    "Sunita is in hospital for a month. Her husband, who never cooked, secretly learns to cook, burns "
    "everything, then improves. She comes home to a kitchen of his recipes and a diary of his mistakes, "
    "and cries when she tastes his dal.",
    "At a 50th anniversary party the grandson finds a box with 50 notes from his grandfather, one per year, "
    "each saying 'I choose you again'. He reads them out. The grandmother, who thought he never said such "
    "things, finally cries and says it back.",
    "Rich Aarav pretends to be poor to find true love. Flower-seller Kajal shares her only lunch with him. "
    "When he admits the truth she says she knew from his clean shoes the first day and was waiting for him "
    "to be honest.",
    "Neha in Pune and Karan in Dubai miss each other's birthdays by flight delays. On her birthday his "
    "flight is cancelled again, so he drives from the airport at 3 AM and knocks on her door with a cake.",
    "Savitri hates her new daughter-in-law Pooja's love marriage and ignores her. When Savitri is in "
    "hospital Pooja secretly gives blood. The nurse tells Savitri, who brings Pooja a gold bangle and "
    "calls her 'beti'.",
]
CLASSIC_EMOTIONAL = [
    "Premchand's Idgah (retell): orphan boy Hamid lives with his grandmother Amina. At the Eid fair his "
    "friends buy toys and sweets but Hamid spends his 3 paise on iron tongs, because Amina burns her hands "
    "making rotis. Friends laugh; Hamid argues his tongs are better than their toys. Amina sees the tongs "
    "and hugs him in tears.",
    "Premchand's Panch Parmeshwar (retell): Jumman and Algu are best friends. Jumman's old aunt gives him "
    "her house but he neglects her; the village panchayat is called and Algu is the judge. Algu rules in the "
    "aunt's favour. Jumman turns against him. Later Jumman becomes the judge in Algu's own case and "
    "chooses justice too; the friendship returns.",
    "Premchand's Bade Bhai Sahab (retell): a strict elder brother studies hard but keeps failing, while the "
    "younger brother plays and passes. The elder explains that marks are not wisdom and that his life "
    "experience protects the younger one. The younger finally understands and touches his feet.",
]
CLASSIC_ANIMAL = [
    "Panchatantra, the clever rabbit and the lion: a lion kills one jungle animal daily. When it is the "
    "rabbit's turn he arrives late and says another lion in a well stole his friends. The lion jumps in "
    "to fight his own reflection and drowns.",
    "Panchatantra, the monkey and the crocodile: a monkey shares fruit with a crocodile. The crocodile's wife "
    "wants the monkey's heart, so he tricks him onto his back mid-river and confesses. The monkey says his "
    "heart is left on the tree, gets back to the tree and escapes. The crocodile loses a friend.",
    "Panchatantra, the blue jackal: a jackal falls in indigo dye and becomes blue. Animals crown him king. "
    "When he hears jackals howling he howls too, is exposed, and is chased away.",
    "Panchatantra, the pigeons and the net: a flock of pigeons is trapped in a hunter's net. Instead of "
    "struggling alone they all fly up together with the net and reach their mouse friend, who cuts them free.",
    "Panchatantra, the crow and the snake: a snake keeps eating a crow family's chicks. The crow steals the "
    "queen's necklace and drops it near the snake's hole. Guards chasing it find and kill the snake.",
    "Premchand's Do Bailon ki Katha (retell): two bullocks, Heera and Moti, are loyal friends sent to a cruel "
    "new owner. They escape, face a bull, get locked in a cattle pound, and finally find their way back to "
    "their kind owner Jhuri.",
    "Aesop, the lion and the mouse: a lion lets a small mouse go. Later the lion is caught in a hunter's net "
    "and the mouse gnaws it free. Kindness to the small comes back.",
]
CLASSIC_JOKE = [
    "Akbar-Birbal, the khichdi: Akbar promises a reward to a poor man who stands all night in a cold lake. "
    "He survives by looking at a far lamp. Akbar refuses the reward, saying the lamp warmed him. Birbal "
    "'cooks' khichdi in a pot hung high above a fire. 'It will never cook!' says Akbar. 'Then how did a "
    "far lamp warm him?' Akbar laughs and pays the man.",
    "Akbar-Birbal, the crows: Akbar asks how many crows are in the city. Birbal gives an exact number. "
    "'And if there are more?' 'Then some crows came to visit their relatives.' 'Fewer?' 'Then some went to "
    "visit theirs.' Akbar laughs.",
    "Akbar-Birbal, the shorter line: Akbar draws a line and says 'make it shorter without touching it'. "
    "Birbal draws a longer line beside it. Akbar smiles at the clever answer.",
    "Nasruddin searches the street for his lost key. People help. Someone asks where he dropped it. "
    "'In my house, but the light is better out here.'",
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
Write ONE complete story for a 45-55 second vertical video. {kind}
Topic: {topic}
These stories were already made. Use a DIFFERENT title, names, setting and twist:
{history}

Rules:
- Exactly {n} scenes. Each scene is one picture and one spoken line. A new picture every line.
- The whole story is 110-130 spoken words. Each line 6-11 words. Simple, gripping {lang}.
- LINE 1 IS THE HOOK, spoken in the first 2 seconds: a shocking, curious or funny statement that makes
  people stop scrolling (examples: "My dog stole my wedding ring.", "Everyone laughed at the waiter. Big mistake.").
- Structure: hook -> very quick setup -> one problem -> one turn that raises the stakes -> the big
  twist -> payoff -> one strong closing line. No filler: every line moves the story forward.
- COMPLETE STORY (the most important rule): the story must make full sense to a stranger in 50 seconds.
  Plan it first in "outline": who the main person is and what they want, the problem, the TURNING POINT
  (a clever idea, a choice, or a revealed secret) and the ENDING that resolves everything. Every secret,
  injury or mystery you mention must be explained before the last line. No unexplained twists, no
  cliffhanger, no "to be continued". If the topic is a classic or folk tale, keep its plot and its ending,
  retold in your own words. Name speakers clearly: when a second person speaks, say who they are.
- COMMENT BAIT (growth): the story must leave ONE hard moral dilemma that splits viewers
  into two sides, so people NEED to answer. The LAST spoken line asks that dilemma directly to the viewer
  ("Aapki jagah hoti toh aap kya karti? Maaf ya saza?"). Jokes: end with a "kaun sahi tha?" style question.
  Never end with a plain "like and subscribe".
- {speech}
- Each scene has a "speaker": "narrator" or a character key. Spoken lines are just the words,
  no quote marks, no "he said".
- Family friendly: no gore, no sexual content.
- 1 to 3 characters. Give each a fixed visual "look" (age, face, hair, clothing; for animals breed,
  colour, collar) so pictures stay consistent. Refer to them in "image" as [[key]].
  Indian characters have fair, light wheatish, clear skin and bright soft light on the face. Young women
  look graceful and pretty: long soft wavy dark-brown hair, natural makeup, small bindi or earrings,
  elegant pastel kurta or saree (or neat casual clothes in a city story).
- "image" describes ONE {shot} (who, where, action, emotion on the face). No text or signs.
- LANGUAGE QUALITY: write the way a real Indian talks: everyday Hindi words ("dadi", "doodh", "pyaar",
  "ghar", "bacha", "naraz"), short sentences, correct grammar and gender ("meri dadi ne doodh piya").
  Do NOT mix in English sentences or phrases ("I was wrong", "suddenly", "fuss") and do not translate
  word for word. No heavy literary Hindi either. Read each line back: if a native Hindi speaker would
  find it odd or half-English, rewrite it in simple Hindi.
- STYLE MODEL for the Hindi narration (copy this voice: clear, concrete, emotional, real Hindi words,
  short flowing sentences, no English):
  "दफ्तर बंद हो चुका था। सूखे की वजह से खेतों की सारी फसलें बर्बाद हो चुकी थीं। लोगों के घरों में खाने के
  लिए एक दाना तक नहीं बचा था। गरीबी इस कदर बढ़ चुकी थी कि लोग अपनी ज़रूरतें तक बेचने लगे थे।"
  Tell it like a storyteller, with the details a person would notice (what they saw, felt, said).
- SILENT-MOVIE TEST: the story must be easy to follow with the sound OFF, even for someone who
  does not know the language. Every picture shows exactly what is happening: a clear action,
  big readable emotions (tears, shock, laughter, anger), meaningful objects (a letter, a ring,
  an empty chair), close-ups at emotional moments. The FIRST picture must be dramatic and
  instantly intriguing.{sub_rule}
- "hook_text": 2-6 words shown big on screen in the first seconds: a curiosity question or shock (e.g. "WHO WROTE THIS LETTER?").
- "title", "hook_text", "yt_title", "description", "comment_question" and hashtags are always in
  plain ENGLISH, even when the spoken lines are Hinglish.
- Pick each voice so it matches who is speaking: {voices}{talk_rule}
- Each scene has "fx": the weather/atmosphere layer for that picture: rain, snow, dust
  (sunbeams, warm floating dust, fireflies, magic) or none. Use it where it adds feeling.

Return ONLY JSON:
{{
  "title": "<catchy title>",
  "outline": {{"who_wants_what": "", "problem": "", "turning_point": "", "ending": ""}},
  "premise": "<one sentence: who, what, the twist>",
  "hook_text": "...",
  "characters": {{"narrator": {{"look": "", "voice": "..."}}, "<key>": {{"look": "...", "voice": "..."}}}},
  "yt_title": "<title under 70 characters: a specific emotional hook with the key searchable words
               (e.g. 'Rich Customer Insulted the Waiter... Then He Saw His Name Tag'), 1 emoji at most, no ALL CAPS>",
  "description": "<3 short lines: line 1 repeats the hook with searchable words, line 2 teases the twist
                  without spoiling it, line 3 asks the viewers' comment question>",
  "comment_question": "<a 4-8 word dilemma question in Hinglish ROMAN letters that forces a side, e.g. 'Aap hoti toh maaf karti? Haan ya Na?'>",
  "hashtags": ["<12 hashtags: 3 broad (#story #emotionalstory #storytime), the rest specific to this
               story's topic and feelings. NO #shorts (Reels)>"],
  "scenes": [{{"image": "...", "speaker": "<narrator or character key>", "line": "..."{sub_field}, "fx": "<rain|snow|dust|none>"}}]
}}"""

SUB_RULE = """
- Each scene also has "sub": a short, natural ENGLISH translation of the line (shown as subtitles).
  "title", "hook_text", "yt_title" and "description" are in English (Hindi words in English letters are OK)."""

# Voices read Hindi in English letters with a foreign accent, so Hinglish lines also come
# in Devanagari ("say"): that is what gets spoken; the English-letter "line" stays for captions.
SAY_RULE = """
- Each scene also has "say": the SAME line written in Devanagari script exactly as it is spoken by a
  native Hindi speaker. HARD RULES for "say":
  * Use real Hindi words. NEVER spell English words or English phrases in Devanagari. Forbidden:
    "आई वाज़ रॉन्ग", "बेबी सेट", "फ़स", "नैप", "टाइम", "रिमोट", "सडनली".
  * Say it in Hindi instead: "मैं गलत थी", "बच्चे की देखभाल", "नखरे", "झपकी / सोना", "समय",
    "अचानक".
  * Only these loanwords may stay in Devanagari: फ़ोन, स्कूल, ऑफ़िस, टीवी, बस, डॉक्टर, स्टेशन, मम्मी, पापा.
  * Natural spoken Hindi, short sentences, correct grammar and gender, like a person telling a story.
  * "line" (English letters) must be the exact same words as "say", so the captions match the voice."""

TALK_RULE = """
- Animals and babies MAY talk (people love this): give a talking animal or baby the voice
  cartoon_male or cartoon_female (cute child-like voice). No roars or animal-noise lines."""

CARTOON_VOICES = {
    "narrator_male": "male storyteller (narrator)", "narrator_female": "female storyteller (narrator)",
    "cartoon_male": "funny cartoon voice for boys, kids and male animals (parrot, dog, cat...)",
    "cartoon_female": "funny cartoon voice for girls, baby girls and female animals",
}
ADULT_VOICES = {
    "narrator_male": "male storyteller around 30 (narrator)",
    "narrator_female": "female storyteller (narrator)",
    "male_young": "man in his 20s", "female_young": "woman in her 20s",
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
    # Hindi voices mangle English spelled in Devanagari: ask Gemini to rewrite the story if it did that
    bad = re.compile(r"(वाज़?|रॉन्ग|राइट|बेबी|नैप|फ़?स|टाइम|सडनली|रिमोट|प्लीज़?|सॉरी|थैंक|ओके|फ़ीलिंग|सरप्राइज़?|"
                     r"गुड|बैड|लव|फ़ेल|वेट|नो|यस|वाओ|क्रेज़ी|फ़न्नी)")
    hits = [m.group(0) for sc in story.get("scenes", []) for m in bad.finditer(sc.get("say", ""))]
    if len(hits) > 2:
        errs.append(f"spoken lines contain English words written in Devanagari ({', '.join(sorted(set(hits))[:6])})")
    if not SCENES - 4 <= len(story.get("scenes", [])) <= SCENES + 4:
        errs.append(f"has {len(story.get('scenes', []))} scenes")
    for s in story.get("scenes", []):
        for name in re.findall(r"\[\[(\w+)\]\]", s.get("image", "")):
            if name not in chars:
                errs.append(f"unknown character [[{name}]]")
    return errs


TAGS_COMMON = ["#hindikahani", "#hindistory", "#kahani", "#storytime", "#reelsindia", "#viralreels",
               "#facebookreels", "#हिंदीकहानी", "#कहानी"]
TAGS_BY_KIND = {
    "love": ["#lovestory", "#premkahani", "#emotionalstory", "#sachapyaar", "#प्रेमकहानी"],
    "animal": ["#moralstory", "#animalstory", "#pyaarkikahani", "#sachhidosti", "#नैतिककहानी"],
    "joke": ["#hindijokes", "#funnyreels", "#comedy", "#chutkule", "#मज़ेदारकहानी"],
}
TAGS_CLASSIC = {"panchatantra": "#panchatantra", "akbar-birbal": "#akbarbirbal", "premchand": "#premchand",
                "nasruddin": "#nasruddin", "aesop": "#aesopfables"}


def build_tags(kind, story_tags, topic):
    """Audience-targeted hashtags: the kind's tags first (YouTube shows the first 3), then topic tags,
    then the common Hindi-story reach tags. At most 15."""
    classic = [tag for key, tag in TAGS_CLASSIC.items() if key in (topic or "").lower()]
    kind_tags = TAGS_BY_KIND.get(kind, [])
    out = []
    for t in kind_tags[:3] + classic + list(story_tags)[:5] + kind_tags[3:] + TAGS_COMMON:
        t = t.replace(" ", "")
        if t and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out[:15]


def slots(day):
    """Today's 2 videos. Three content types rotate (love, animal + human bond, funny), 2 per day,
    so every type gets posted regularly without making more videos than ElevenLabs credits allow."""
    d = datetime.date.fromisoformat(day).toordinal()
    lead = (" The MAIN CHARACTER is a woman or girl (young, warm, relatable); tell it in her voice "
            "(first person, narrator_female or female_young).")
    real = {"style": REAL_STYLE, "shot": "realistic film shot", "voices": REAL_VOICES,
            "speech": ("Mostly ONE narrator telling it (first person 'I' works best), with a few short "
                       "emotional lines spoken by the characters at key moments.")}
    hinglish = ("simple everyday HINDI (written in English letters). At least 90% of the words must be "
                "Hindi. Only a few very common loanwords are allowed (phone, school, office, TV, bus, doctor). "
                "Example: 'Maa, main sach bol raha hoon, mujhpe bharosa karo.'")
    kinds = {
        "love": {"kind": ("It is an emotional LOVE story set in India with Indian characters and a twist "
                          "ending. Mature, adult tone: grown-up dialogue, never childish." + lead),
                 "topic": (LOVE_PLOTS + CLASSIC_EMOTIONAL)[d % len(LOVE_PLOTS + CLASSIC_EMOTIONAL)], "key": "love", **real, "voices": ADULT_VOICES, "hindi": True,
                 "lang": hinglish},
        "animal": {"kind": ("It is an emotional ANIMAL + HUMAN BOND story (wild or pet animal and people), "
                            "told mostly through pictures so anyone can follow it." + lead),
                   "topic": (CLASSIC_ANIMAL + ANIMAL_TOPICS)[d % len(CLASSIC_ANIMAL + ANIMAL_TOPICS)], "key": "animal", **real, "mood": "animal", "hindi": True,
                   "talk": True, "lang": hinglish},
        "joke": {"kind": ("It is a FUNNY cartoon JOKE-story to help people relax and laugh: a quick "
                          "setup and a punchline at the end. Light, silly, relatable, family friendly."),
                 "topic": (CLASSIC_JOKE + FUNNY_TOPICS)[d % len(CLASSIC_JOKE + FUNNY_TOPICS)], "key": "joke", "style": CARTOON_STYLE,
                 "shot": "frame of a 3D animated movie", "voices": CARTOON_VOICES,
                 "speech": ("The characters TALK: most lines are the characters speaking (funny back-and-forth), "
                            "a narrator line now and then to move the story on."),
                 "hindi_voices": True, "mood": "funny", "talk": True,
                 "lang": ("simple everyday HINDI (written in English letters). At least 90% Hindi words, only a "
                          "few very common loanwords (phone, school, TV). Example: 'Bhai, yeh kya ho gaya?'")},
    }
    first, second = (("love", "animal") if d % 2 else ("animal", "love"))
    return [kinds[first], kinds["joke"], kinds[second]]  # 9 AM story, 1 PM joke, 5 PM story



def main():
    load_dotenv()
    day = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date().isoformat())
    DAILY.mkdir(parents=True, exist_ok=True)
    todo = [n for n in (1, 2, 3) if not (DAILY / f"{day}_part{n}.json").exists()]
    if not todo:
        print(f"Stories for {day} already written.")
        return
    hist_file = DAILY / "history.txt"
    history = hist_file.read_text(encoding="utf-8").splitlines() if hist_file.exists() else []

    eps = []  # written together at the end, so a failed run never leaves half a day
    for n, slot in enumerate(slots(day), 1):
        if n not in todo:  # this part was already written earlier today
            continue
        used = {h.split(" | ")[0].strip().lower() for h in history}
        hinglish = slot.get("hindi") or slot.get("hindi_voices")
        prompt = PROMPT.format(kind=slot["kind"], topic=slot["topic"], lang=slot["lang"],
                               shot=slot["shot"], n=SCENES, speech=slot["speech"],
                               voices="; ".join(f"{k} = {v}" for k, v in slot["voices"].items()),
                               sub_rule=(SUB_RULE if slot.get("hindi") else "") + (SAY_RULE if hinglish else ""),
                               talk_rule=TALK_RULE if slot.get("talk") else "",
                               sub_field=(', "sub": "<English translation>"' if slot.get("hindi") else "")
                               + (', "say": "<same line in Devanagari>"' if hinglish else ""),
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
                          **({"sub": s["sub"]} if s.get("sub") else {}),
                          **({"say": s["say"]} if hinglish and s.get("say") else {})}
                         for s in story["scenes"]],
              "caption": story.get("yt_title", ""), "slug": f"{day}_part{n}",
              "story_no": len(history) + 1,
              "yt_title": story.get("yt_title") or story["title"],
              "description": story.get("description", ""),
              "comment_question": story.get("comment_question", ""),
              "hashtags": build_tags(slot.get("key"), tags, slot.get("topic"))}
        eps.append(ep)
        history.append(f"{story['title']} | {day} | {story.get('premise', '').strip()}")
        print(f"Story {n}: {story['title']}")
    for ep in eps:
        (DAILY / f"{ep['slug']}.json").write_text(json.dumps(ep, indent=1, ensure_ascii=False),
                                                  encoding="utf-8")
    hist_file.write_text("\n".join(history) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

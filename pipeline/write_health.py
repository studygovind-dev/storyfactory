#!/usr/bin/env python3
"""
Money Mind Health: 5 videos a day (MMH_PER_DAY, 1-6), about 55 seconds each, three pillars:

  HEALTH  funny "talking food / body part" characters, plus calm yoga how-to videos
  MONEY   funny "talking money idea" characters (SIP, emergency fund, UPI fraud...), SEBI-safe, educational
  MIND    "psychology fact" lectures: a glowing brain picture and a calm male teacher's voice

Writes series/health/<date>_h<N>.json with Gemini. Usage: python pipeline/write_health.py [YYYY-MM-DD]
"""
import datetime, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import ROOT, load_dotenv  # noqa: E402
from write_story import ask_gemini  # noqa: E402

HEALTH = ROOT / "series" / "health"
PER_DAY = max(1, min(6, int(os.environ.get("MMH_PER_DAY", "5") or 5)))
SLOT_PILLARS = ["Health", "Mind", "Money", "Health", "Mind", "Money"]  # video 1..6
SCENES = 18  # about 55 seconds
HANDLE = "MONEY MIND & HEALTH"

STYLE_CHARACTER = ("3D animated movie still in the style of a Pixar film, one cute glossy non-human cartoon "
                   "mascot character with big expressive eyes, arms and legs and a small headband, centered, "
                   "simple clean colourful background, sharp focus, hyper-detailed, soft cinematic lighting, "
                   "vertical 9:16")
SUFFIX_CHARACTER = ("The character is NOT a person: no human face, no girl, no boy, no extra people. "
                    "No text, no watermark, no logos.")
STYLE_BRAIN = ("cinematic 3D render of a glowing human brain with neon blue and violet neural pathways, "
               "dark background, soft volumetric light, ultra detailed, vertical 9:16")
SUFFIX_BRAIN = "No people, no faces, no text, no watermark, no logos."
STYLE_YOGA = ("natural photo of a young Indian woman in simple comfortable yoga clothes doing a yoga pose on a "
              "mat in a bright clean room, soft daylight, full body visible, calm expression, vertical 9:16")
SUFFIX_YOGA = "One woman only, correct anatomy, no text, no watermark, no logos."

# ---------------------------------------------------------------- HEALTH (talking characters)
HEALTH_SUBJECTS = [
    ("Namak (salt)", "tastes great in small amounts; too much can raise blood pressure; skip extra salt on food"),
    ("Chini (sugar)", "quick energy; too much means weight gain and high blood sugar; hidden in chai, cold drinks, biscuits"),
    ("Cold drink", "a bottle holds many spoons of sugar; water, nimbu paani or chaas are better daily choices"),
    ("Maida", "refined flour has little fibre; whole wheat atta and millets keep you full longer"),
    ("Tel (cooking oil)", "needed in small amounts; too much deep-fried food is heavy for the heart"),
    ("Chai", "fine in moderation; many sugary cups a day add up; try less sugar"),
    ("Kaddu ke beej (pumpkin seeds)", "have zinc and magnesium; a small handful is good; calorie-dense so do not overeat"),
    ("Badam (almonds)", "healthy fats and protein; a small handful a day"),
    ("Haldi (turmeric)", "a common cooking spice; part of healthy Indian food; not a cure for any disease"),
    ("Nimbu paani", "refreshing, hydrating, vitamin C; keep the sugar low"),
    ("Paani (water)", "tiredness and headaches can sometimes be from too little water; sip through the day"),
    ("Dahi (curd)", "has protein and friendly bacteria; choose plain over sugary ones"),
    ("Moong aur chana", "protein and fibre; sprouts or boiled make a simple healthy snack"),
    ("Instant noodles", "usually high in salt and low in fibre; fine once in a while, not every day"),
    ("Chips aur namkeen", "high in salt and oil; a small bowl is okay; do not finish the packet"),
    ("Ghee", "good in small amounts; a spoon is enough; too much adds calories quickly"),
    ("Kela (banana)", "easy energy, potassium and fibre; a handy snack before a walk"),
    ("Methi dana", "has fibre; soaked in water is a kitchen habit; not a medicine"),
    ("Pet (stomach)", "heavy late-night food and eating too fast make it uncomfortable; eat slowly, early dinner"),
    ("Acidity (seene ki jalan)", "common triggers are oily, spicy food and big late meals; eat smaller, do not lie down right after eating; see a doctor if it happens often"),
    ("Gas aur pet phoolna", "eating fast, fizzy drinks and long gaps can cause gas; walk 10 minutes after meals; see a doctor if it persists"),
    ("Kabz (constipation)", "fibre from fruits, vegetables, dal and enough water help; a daily walk helps; see a doctor if it lasts long"),
    ("Baal jhadna (hair fall)", "stress, poor sleep and low protein or iron can play a part; eat dal, eggs, greens, nuts; no miracle oil; see a doctor if hair falls in patches or suddenly"),
    ("Tvacha (skin)", "likes water, sleep and sunscreen; wash the face twice a day; do not pick pimples; see a skin doctor for stubborn problems"),
    ("Dil (heart)", "likes a 30 minute daily walk, less salt and less stress; get check-ups after 30-40"),
    ("Aankhein (eyes)", "get tired from screens; 20-20-20: every 20 minutes look 20 feet away for 20 seconds; carrots and greens are good food"),
    ("Neend (sleep)", "most adults need 7-8 hours; phone in bed steals sleep; keep a fixed bedtime"),
    ("Kidney", "like enough water and not too much salt; do not hold the urge for long"),
    ("Rirh ki haddi (spine)", "hates long slouching; stand up every hour, sit straight, light stretching"),
    ("Ghutne (knees)", "stay healthier with regular walking, strong leg muscles and healthy weight; see a doctor for lasting pain"),
    ("Dimaag (brain)", "works better with sleep, water and short breaks"),
    ("Fefde (lungs)", "love deep breathing and fresh air; five slow deep breaths can calm you"),
    ("Daant (teeth)", "need brushing twice a day; sugary snacks are the enemy; rinse after sweets"),
    ("Vitamin D (dhoop)", "sunlight for 15-20 minutes helps the body make it; deficiency is common; get a test and ask a doctor before taking supplements"),
    ("Vitamin C", "found in amla, guava, oranges, nimbu, capsicum; eat fresh; no vitamin is a cure"),
    ("Vitamin A", "found in carrot, spinach, papaya, eggs, milk; good for eyes and skin; too much from supplements can be harmful"),
    ("Vitamin B12", "found in milk, curd, eggs; some vegetarians run low; get a blood test and ask a doctor"),
    ("Vitamin B-complex", "found in whole grains, dals, nuts and greens; eat a varied thali"),
    ("Vitamin E", "found in nuts, seeds and cooking oils; a handful of nuts is plenty"),
    ("Iron (khoon ki kami)", "found in spinach, jaggery, dal, rajma; vitamin C like lemon helps absorb it; get tested; see a doctor if you feel very weak"),
    ("Calcium", "found in milk, curd, paneer, ragi, sesame; helps bones; walking in the sun helps too"),
    ("Protein", "found in dal, paneer, eggs, sprouts, curd; include some in every meal"),
    ("Fibre", "found in oats, fruits, vegetables, whole grains; keeps you full and helps digestion"),
    ("Zinc aur magnesium", "found in pumpkin seeds, chana, nuts and greens; eat a variety"),
    ("Omega-3", "found in walnuts, flaxseed, some fish; a spoon of flaxseed or a few walnuts a day is simple"),
    ("Mithai", "tastes wonderful; keep it for festivals and small portions; sugar adds up quickly"),
    ("Soft drinks aur energy drinks", "full of sugar and caffeine; water, chaas and nimbu paani are better; children should avoid energy drinks"),
    ("Biscuit aur bakery items", "often have refined flour, sugar and unhealthy fats; read the label; choose fruit or nuts more often"),
    ("Late night khana", "heavy food right before bed disturbs sleep and digestion; try dinner 2-3 hours before sleeping"),
    ("Subah ki walk", "30 minutes of brisk walking most days is a simple habit for heart, mood and weight"),
    ("Immunity", "no single food boosts it; sleep, fruits and vegetables, hygiene, exercise and hand washing all help"),
    ("Sardi-khansi", "rest, warm fluids and honey-ginger tea are comforting; see a doctor if it lasts more than a few days"),
    ("Garmi mein sehat", "drink water often, wear light cotton, avoid peak afternoon sun; ORS and nimbu paani help in heavy sweating"),
    ("Barish mein sehat", "drink boiled or filtered water, wash vegetables, avoid street food during heavy rain"),
    ("Haath dhona", "wash hands with soap for 20 seconds before eating and after the toilet; it prevents many infections"),
    ("Screen time", "too much scrolling tires the eyes and spoils sleep; take breaks and keep the phone away at night"),
    ("Posture", "slouching strains the neck and back; keep the screen at eye level, feet flat, shoulders relaxed"),
    ("Weight aur crash diet", "crash diets rarely last; small steady changes, walking and portion control work better"),
    ("Blood pressure", "less salt, a daily walk and regular checks help; take medicines as the doctor says"),
    ("Sugar (diabetes) se bachav", "balanced food, walking and a healthy weight lower the risk; get tested if family history; ask a doctor"),
]
YOGA_SUBJECTS = [
    ("Yoga: Tadasana (mountain pose)", "stand tall, feet together, arms up and stretch; for posture; gentle for beginners"),
    ("Yoga: Bhujangasana (cobra pose)", "lie on the stomach, lift the chest slowly with hands under shoulders; gentle back stretch; do not force it"),
    ("Yoga: Vrikshasana (tree pose)", "balance on one leg with hands folded; builds focus; hold a wall at first"),
    ("Yoga: Trikonasana (triangle pose)", "feet wide, bend sideways with one arm down and one up; stretches the sides; go slowly"),
    ("Yoga: Vajrasana (thunderbolt pose)", "sit on the heels with a straight back; can be done after meals; stop if the knees hurt"),
    ("Yoga: Balasana (child's pose)", "kneel and fold forward with arms stretched; a restful stretch for back and shoulders"),
    ("Yoga: Pawanmuktasana (wind-relieving pose)", "lie on the back and hug one knee at a time; gentle for gas and a tight stomach; stop if it hurts"),
    ("Yoga: Surya Namaskar basics", "a flowing set of postures; learn slowly from a teacher; stop if you feel dizzy or pain"),
    ("Yoga: Shavasana (relaxation)", "lie on the back, eyes closed, breathe slowly for 5 minutes; helps you rest and unwind"),
    ("Yoga: Anulom Vilom (breathing)", "slow alternate-nostril breathing for 5 minutes; feels calming; no medical claims"),
    ("Yoga: Bhramari (humming breath)", "close the ears gently and hum on the exhale; a calming habit for a few minutes"),
]

# ---------------------------------------------------------------- MONEY (talking money ideas, SEBI-safe)
MONEY_SUBJECTS = [
    ("Emergency fund", "keep roughly 3 to 6 months of expenses in a safe, easy-to-reach place for surprises like illness or job loss"),
    ("SIP (investing a fixed amount regularly)", "a way to invest a small fixed amount every month; build the habit; investments are subject to market risks; no returns are guaranteed"),
    ("Inflation", "prices rise over time, so money kept idle buys less each year; think about it when planning, without chasing risky shortcuts"),
    ("Credit card", "paying the full bill on time costs nothing extra; carrying a balance means very high interest"),
    ("EMI aur loan", "check the total interest, not just the EMI; avoid loans for wants; pay on time"),
    ("Budget: 50-30-20 rule", "a simple guide: about half for needs, thirty percent for wants, twenty percent for savings; adjust to your life"),
    ("Insurance", "term and health insurance protect your family from big shocks; buy from regulated insurers; keep protection separate from investing"),
    ("Fixed Deposit (FD)", "gives a fixed interest and feels safe; the interest may not beat inflation; bank deposits are insured up to Rs 5 lakh per bank"),
    ("UPI fraud", "never share your OTP or PIN; you never need a PIN to receive money; report fraud on cyber crime helpline 1930"),
    ("Stock tips aur finfluencer", "investment advice should come only from SEBI-registered advisers; check registration on the SEBI website; be careful with Telegram and WhatsApp tips"),
    ("Double your money scheme", "guaranteed high returns are the biggest red flag of a scam; if it sounds too good to be true, it usually is"),
    ("Compound interest", "money earns on money over time, so starting early matters; examples are only illustrations, not promises"),
    ("Savings vs investing", "savings are for safety and near-term needs; investing aims to grow money over a long time with some risk"),
    ("Credit score", "paying bills and EMIs on time and not maxing out cards helps; a score around 750 or more is generally seen as good"),
    ("Don't put all eggs in one basket", "spreading money across different kinds of assets can reduce the damage of one going wrong; this is general education only"),
    ("Pay yourself first", "move a fixed amount to savings right after salary arrives, then spend the rest"),
    ("Impulse buying", "wait 24 hours before a big non-essential purchase; most urges fade"),
    ("Subscriptions", "small monthly subscriptions you forgot about leak money; review them once a month"),
    ("Needs vs wants", "ask 'is it a need or a want?' before spending; wants are fine in a planned amount"),
    ("Expense tracking", "write down every expense for one month; most people are surprised where money goes"),
    ("Loan apps", "instant loan apps often charge huge interest and misuse data; borrow only from regulated lenders"),
    ("Financial goals", "write a goal with an amount and a date, like a 2 lakh emergency fund in 12 months, then divide by months"),
]

# ---------------------------------------------------------------- MIND (psychology facts)
MIND_FACTS = [
    ("Mere exposure effect", "we tend to like things and people more the more often we see them"),
    ("Zeigarnik effect", "unfinished tasks stay in our mind more than finished ones; writing a plan can calm the mind"),
    ("Halo effect", "one good quality, like looks, makes us assume other good qualities"),
    ("Confirmation bias", "we notice facts that match what we already believe and ignore the rest"),
    ("Anchoring bias", "the first number we hear sways our later judgement, like a first price in a bargain"),
    ("Dunning-Kruger effect", "people with little knowledge can feel very confident, while experts often doubt themselves"),
    ("Bystander effect", "in a crowd each person feels less responsible to help; pointing at one person to help works better"),
    ("Spotlight effect", "we think others notice our mistakes much more than they really do"),
    ("Sunk cost fallacy", "we keep going with something because we already spent time or money, even when it is not worth it"),
    ("Hedonic adaptation", "we get used to new things and the happiness fades; gratitude resets it"),
    ("Peak-end rule", "we judge an experience mostly by its most intense moment and its ending"),
    ("Ben Franklin effect", "people who do us a small favour tend to like us more afterwards"),
    ("Pratfall effect", "a small mistake can make a capable person more likeable"),
    ("Reciprocity", "when someone does something for us we feel a pull to return it"),
    ("Social proof", "we copy what many others are doing, especially when unsure"),
    ("Loss aversion", "losing something hurts about twice as much as gaining the same thing feels good"),
    ("Paradox of choice", "too many options make it harder to decide and less satisfying"),
    ("Decision fatigue", "after many decisions our choices get worse; make important ones early in the day"),
    ("Frequency illusion (Baader-Meinhof)", "after noticing something new, we suddenly see it everywhere"),
    ("Pygmalion effect", "high expectations from others often lift performance, low expectations lower it"),
    ("Attachment styles", "early relationships shape how secure, anxious or avoidant we feel in close relationships; it can be changed with awareness"),
    ("Intermittent reinforcement", "unpredictable rewards, like a message that sometimes arrives, keep us hooked more than steady ones"),
    ("Thin-slicing (first impressions)", "people form a first impression in seconds, and it is hard to change"),
    ("Chameleon effect", "we unconsciously copy the posture and speech of people we like; it builds rapport"),
    ("Stonewalling", "some people go silent when overwhelmed in an argument; naming it and taking a 20 minute break helps"),
    ("Active listening", "people feel close to those who truly listen; repeat what you heard before you reply"),
    ("Overthinking", "going round and round in thoughts rarely solves anything; writing it down or taking a walk breaks the loop"),
    ("Imposter feeling", "many capable people feel like frauds; it is common and not proof that you are one"),
    ("Habit loop", "a habit has a cue, a routine and a reward; change the routine, keep the cue"),
    ("Two-minute rule", "starting a task for just two minutes makes it much easier to continue"),
    ("Delayed gratification", "people who can wait for a bigger reward often do better in the long run; practise in small steps"),
    ("Placebo and belief", "expectations can change how we feel; it shows the mind-body link, not that illness is imaginary"),
    ("Cognitive dissonance", "we feel uneasy when our actions clash with our beliefs, and we often change the story to feel better"),
    ("Fundamental attribution error", "we blame other people's behaviour on their character, but our own on the situation"),
    ("Mirror of self-talk", "the way we talk to ourselves shapes our confidence; speak to yourself like a friend"),
    ("Gaslighting (awareness)", "making someone doubt their own memory or feelings is manipulation; trust your feelings and ask a trusted person"),
    ("Love bombing (awareness)", "extreme flattery and attention very early can be a sign of manipulation; healthy love grows steadily"),
    ("Boundaries", "saying no politely protects your time and energy; good people respect it"),
    ("Sleep and mood", "poor sleep makes us more irritable and anxious; fixing sleep helps the mind"),
]

# ---------------------------------------------------------------- prompts
CHAR_PROMPT = """You write funny, useful 55-second Reels for the Facebook Page "Money Mind Health".
PILLAR: {pillar}
FORMAT: a "talking character" video. The subject below is a cartoon NON-HUMAN mascot that talks to the viewer in
first person, like: "Arre main namak hoon! Thoda daalega toh swaad bhi doonga, zyada daalega toh BP bhi
badhaaunga!" (Add 1-2 more mascots only if it makes it funnier.)
SUBJECT: {subject}
SAFE FACTS the characters may use (stay inside them, add nothing risky): {facts}
{pillar_rules}

Rules:
- Exactly 18 scenes in 6 GROUPS of 3 lines. The SAME character speaks all 3 lines of a group (one picture per
  group). 2-3 characters in total; the first line of the video is a funny, loud hook from the subject.
- Language: funny street-style (tapori) Hindi: short punchy lines, words like "arre bhai", "bhidu", "bole toh",
  "lafda", "ekdum", "tension nahi lene ka". Mostly Hindi words. Each line 6-12 words.
- "say" = the line in Devanagari exactly as spoken, real Hindi words, NEVER English phrases spelled in Devanagari
  (common loanwords like बीपी, शुगर, डॉक्टर, फ़ोन, चाय, टेंशन are fine). "line" = the SAME words in English letters.
- Accuracy and safety: only general educational advice. Never say it cures or prevents a disease. Use "can",
  "may". End with a moderation tip. One line says to see a doctor / expert if there is a real problem.
- Every character says who it is in its first group, gives one fact and one simple tip.
- The LAST group ends with a question that makes people comment.
- "tag": the speaker's name in short ENGLISH capitals, e.g. "NAMAK BHAI", "SIP BHAI", "CHINI DIDI".
- "image": describe ONE speaking mascot in the scene (expression, pose). Put [[key]] where it appears. Each group's
  3 scenes use the SAME image description. The mascot must be the actual subject made into a cute object
  character (for example a salt shaker, a sugar cube, a stomach, a golden coin, a credit card) with arms, legs, big
  eyes and a headband. NEVER a person, girl or boy. No text in the picture.
- Characters: each has "look" (a fixed visual description of the NON-HUMAN mascot: material, colour, face,
  headband) and a "voice" from: hindi_cartoon_male (small, cute), hindi_cartoon_female (cute, high),
  hindi_male_deep (gruff, heavy), hindi_male_young (lively young man). Different characters, different voices.
- hook_text: 2-5 English words shown at the start. Titles, hook_text, yt_title, description, comment_question,
  hashtags are in English / roman letters. Family friendly, funny, never scary.
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

LECTURE_PROMPT = """You write 55-second Reels for the Facebook Page "Money Mind Health".
PILLAR: Mind. FORMAT: a "psychology fact" lecture. One calm, confident male teacher ("Psychology Sir") speaks
to the viewer in clear Hindi while a glowing brain picture is shown. No jokes needed; make it fascinating.
TOPIC: {subject}
SAFE FACTS (stay inside them, add nothing invented): {facts}

Rules:
- Exactly 18 scenes, one short sentence each (6-12 words), one speaker only: the key "sir".
- Structure: (1) a hook that makes people curious, like "Kya aapne kabhi socha hai ki..."; (2) the name of the
  effect in simple words (English term + what it means in Hindi); (3) a relatable everyday Indian example in
  2-3 lines (friends, family, shopping, work, relationships); (4) what researchers have generally observed (no
  invented studies or numbers); (5) how it affects the viewer; (6) two practical ways to use it or protect
  yourself; (7) last line: a question that makes people comment.
- Accuracy: only well-established psychology. Do NOT make claims about "girls" or "boys" as groups; talk about
  people and relationships in general. No diagnosing, no therapy advice, no manipulation tips. Say "often",
  "tends to", "many people".
- "say" = the line in Devanagari exactly as spoken, real Hindi words, NEVER English phrases spelled in Devanagari
  (the English name of the effect may stay as a name). "line" = the SAME words in English letters.
- Calm teacher tone, short sentences, no slang.
- "tag" on every scene: "PSYCHOLOGY FACT". "speaker": "sir".
- "image": for scene 1 describe the glowing brain (e.g. "a glowing brain with neon blue neural pathways, slow
  light pulses"); for scene 10 describe another view of the brain (e.g. "a brain with warm orange and violet
  light, close-up of neurons"). Other scenes may repeat the text. No people, no text.
- hook_text: 2-5 English words, the effect's name or a curious question. Titles etc. in English / roman letters.
These titles were already made. Choose a different title and examples:
{history}

Return ONLY JSON:
{{"title": "", "hook_text": "",
  "characters": {{"sir": {{"look": "calm male psychology teacher (voice only)", "voice": "hindi_narrator_male", "name": "Psychology Sir"}}}},
  "yt_title": "<under 70 characters, curious>",
  "description": "<2 short lines>",
  "comment_question": "<a question in Hinglish roman letters that makes people answer>",
  "hashtags": ["<5 hashtags specific to this topic>"],
  "scenes": [{{"image": "", "speaker": "sir", "line": "", "say": "", "tag": "PSYCHOLOGY FACT", "fx": "none"}}]}}"""

YOGA_PROMPT = """You write calm 55-second yoga how-to Reels for the Facebook Page "Money Mind Health".
PILLAR: Health. FORMAT: a yoga demo. A picture of a young Indian woman doing the pose is shown, while a calm
male teacher ("Yoga Sir") speaks to the viewer in clear, warm Hindi.
POSE: {subject}
SAFE FACTS (stay inside them, add nothing risky): {facts}

Rules:
- Exactly 18 scenes, one short sentence each (6-12 words), one speaker only: the key "sir".
- Structure: (1) a friendly hook; (2) the pose name (Sanskrit name + Hindi meaning); (3) three clear steps, one
  or two lines each, easy for a beginner; (4) the gentle benefit (no cures, no medical claims, say "can help you
  feel", "gentle stretch"); (5) a caution: go slowly, stop if there is pain, do not do it with an injury or
  health problem without asking a doctor or a trained teacher; (6) last line: a question to comment on.
- "say" = the line in Devanagari exactly as spoken, real Hindi words, no English phrases spelled in Devanagari
  (the pose name may stay). "line" = the SAME words in English letters.
- "tag" on every scene: "YOGA TIP". "speaker": "sir".
- "image": for scene 1 describe the woman starting the pose (standing or sitting ready); for scene 7 the
  woman in the finished pose; for scene 13 the same pose seen a little differently or her relaxed afterwards.
  One woman only, simple clothes, bright clean room, no text.
- hook_text: 2-5 English words (the pose name). Titles etc. in English / roman letters.
These titles were already made. Choose a different title:
{history}

Return ONLY JSON:
{{"title": "", "hook_text": "",
  "characters": {{"sir": {{"look": "calm male yoga teacher (voice only)", "voice": "hindi_narrator_male", "name": "Yoga Sir"}}}},
  "yt_title": "<under 70 characters>",
  "description": "<2 short lines>",
  "comment_question": "<a question in Hinglish roman letters that makes people answer>",
  "hashtags": ["<5 hashtags specific to this pose>"],
  "scenes": [{{"image": "", "speaker": "sir", "line": "", "say": "", "tag": "YOGA TIP", "fx": "none"}}]}}"""

MONEY_RULES = """MONEY RULES (SEBI-safe): educational only. NEVER name any stock, mutual fund, scheme, broker, bank, app or
product. NEVER promise or imply returns, never say "buy" or "sell", never predict markets. Where investing is
mentioned, one line must say "investments are subject to market risks" and one that advice should come from a
SEBI-registered adviser. Do not tell people to invest; explain ideas and habits. No 'get rich quick'. Be honest
that nothing is guaranteed."""
HEALTH_RULES = "HEALTH RULES: general wellness only; never diagnose, never promise a cure; suggest seeing a doctor for real problems."

VOICES = ("hindi_cartoon_male", "hindi_cartoon_female", "hindi_male_deep", "hindi_male_young", "hindi_narrator_male")
DISCLAIMERS = {
    "Health": "Educational only. Not medical advice. See a doctor if you have a health problem.",
    "Money": ("Educational only. Not investment advice. Investments are subject to market risks; read all "
              "scheme-related documents. Consult a SEBI-registered adviser."),
    "Mind": "Educational only. Not a substitute for professional mental-health care.",
}
TAGS = {
    "Health": ["#healthtips", "#healthfacts", "#sehat", "#swasthya", "#hindihealth", "#healthyfood", "#yoga"],
    "Money": ["#moneytips", "#personalfinance", "#paisa", "#financialliteracy", "#savemoney", "#moneymindset", "#budgeting"],
    "Mind": ["#psychologyfacts", "#psychology", "#mindset", "#humanbehavior", "#brainfacts", "#selfimprovement", "#mindblown"],
}
TAGS_COMMON = ["#reelsindia", "#viralreels", "#facebookreels", "#हिंदी"]
EMOJI = {"Health": "🥗", "Money": "💰", "Mind": "🧠"}


def pick_subject(pillar, d, n):
    """The subject for video n of day d: rotates through each pillar's list, no repeats for many days."""
    slots = SLOT_PILLARS[:PER_DAY]
    k = slots[:n].count(pillar) - 1
    per = max(1, slots.count(pillar))
    i = d * per + k
    if pillar == "Health":
        # every third health video is a yoga how-to
        if i % 3 == 2:
            s = YOGA_SUBJECTS[(i // 3) % len(YOGA_SUBJECTS)]
            return "yoga", s
        return "character", HEALTH_SUBJECTS[(i - i // 3) % len(HEALTH_SUBJECTS)]
    if pillar == "Money":
        return "character", MONEY_SUBJECTS[i % len(MONEY_SUBJECTS)]
    return "lecture", MIND_FACTS[i % len(MIND_FACTS)]


def check(story, used, fmt):
    errs = []
    if story.get("title", "").strip().lower() in used:
        errs.append("title already used")
    if re.search(r"[ऀ-ॿ]", (story.get("title") or "") + (story.get("yt_title") or "") + (story.get("hook_text") or "")):
        errs.append("title or hook_text must be in English letters, not Devanagari")
    scenes = story.get("scenes") or []
    if len(scenes) != SCENES:
        errs.append(f"has {len(scenes)} scenes, needs {SCENES}")
    chars = story.get("characters") or {}
    if fmt == "character" and not 1 <= len(chars) <= 4:
        errs.append("needs 2-3 characters")
    if fmt != "character" and "sir" not in chars:
        errs.append("needs the character 'sir'")
    for c in chars.values():
        if c.get("voice") not in VOICES:
            c["voice"] = "hindi_narrator_male" if fmt != "character" else VOICES[0]
        if fmt != "character":
            c["voice"] = "hindi_narrator_male"
    for sc in scenes:
        if sc.get("speaker") not in chars:
            errs.append(f"unknown speaker {sc.get('speaker')}")
            break
        if not sc.get("say") or not sc.get("line"):
            errs.append("a scene has no line")
            break
    bad = re.compile(r"(वाज़?|रॉन्ग|राइट|बेबी|सडनली|रिमोट|प्लीज़?|सॉरी|ओके|फ़ीलिंग|सरप्राइज़?|गुड|बैड|नो\b|यस\b)")
    if len([m for sc in scenes for m in bad.findall(sc.get("say", ""))]) > 2:
        errs.append("English words spelled in Devanagari")
    return errs


def make_one(day, n, history):
    d = datetime.date.fromisoformat(day).toordinal()
    pillar = SLOT_PILLARS[n - 1]
    fmt, (subject, facts) = pick_subject(pillar, d, n)
    used = {h.split(" | ")[0].strip().lower() for h in history}
    hist = "\n".join("- " + h.split(" | ")[0] for h in history[-80:]) or "none"
    if fmt == "lecture":
        prompt = LECTURE_PROMPT.format(subject=subject, facts=facts, history=hist)
    elif fmt == "yoga":
        prompt = YOGA_PROMPT.format(subject=subject, facts=facts, history=hist)
    else:
        prompt = CHAR_PROMPT.format(pillar=pillar, subject=subject, facts=facts, history=hist,
                                    pillar_rules=MONEY_RULES if pillar == "Money" else HEALTH_RULES)
    for attempt in range(3):
        story = ask_gemini(prompt)
        errs = check(story, used, fmt)
        if not errs:
            break
        print(f"Video {n} ({pillar}) had problems ({'; '.join(errs[:3])}), asking again...")
    else:
        sys.exit(f"Gemini could not write video {n} after 3 tries.")
    scenes = story["scenes"]
    keys = list(story["characters"])
    for sc in scenes:  # repair: a picture may only name characters that exist
        sc["image"] = re.sub(r"\[\[(\w+)\]\]",
                             lambda m: f"[[{m.group(1) if m.group(1) in keys else sc['speaker']}]]", sc["image"])
    if fmt == "character":
        for g in range(SCENES // 3):  # one picture per group of 3: same speaker, same picture
            first = scenes[3 * g]
            for sc in scenes[3 * g: 3 * g + 3]:
                sc["speaker"], sc["image"] = first["speaker"], first["image"]
                if not sc.get("tag"):
                    sc["tag"] = story["characters"][first["speaker"]].get("name", "").upper()
        style, suffix, pic_group = STYLE_CHARACTER, SUFFIX_CHARACTER, 3
    elif fmt == "lecture":
        style, suffix, pic_group = STYLE_BRAIN, SUFFIX_BRAIN, 9
    else:
        style, suffix, pic_group = STYLE_YOGA, SUFFIX_YOGA, 6
    chars = {k: {"look": c.get("look", ""), "voice": c["voice"]} for k, c in story["characters"].items()}
    tags = [t if t.startswith("#") else "#" + t for t in story.get("hashtags", []) if isinstance(t, str)]
    all_tags = []
    for t in tags[:5] + TAGS[pillar] + TAGS_COMMON:
        t = t.replace(" ", "")
        if t and t.lower() not in [x.lower() for x in all_tags]:
            all_tags.append(t)
    all_tags = all_tags[:15]
    title = story["title"]
    caption = (f"{story.get('yt_title') or title}\n\n{story.get('description', '').strip()}\n\n"
               f"{story.get('comment_question', '')}\n\n{DISCLAIMERS[pillar]}\n\n"
               "Follow Money Mind & Health for a new tip every day!\n\n" + " ".join(all_tags))[:2100]
    ep = {"series": title, "episode": n, "title": title, "style": style, "img_suffix": suffix,
          "pic_group": pic_group, "handle": HANDLE, "characters": chars, "short": True,
          "mood": {"Money": "emotional", "Mind": "emotional", "Health": "funny"}[pillar],
          "hook_text": story.get("hook_text", ""),
          "scenes": [{"image": s["image"], "speaker": s["speaker"], "line": s["line"], "say": s["say"],
                      "tag": s.get("tag", ""), "fx": "none"} for s in scenes],
          "caption": story.get("yt_title", title), "slug": f"{day}_h{n}", "story_no": len(history) + 1,
          "yt_title": story.get("yt_title") or title, "description": story.get("description", ""),
          "comment_question": story.get("comment_question", ""), "hashtags": all_tags,
          "caption_text": caption, "pillar": pillar, "format": fmt,
          "telegram_caption": f"{EMOJI[pillar]} Money Mind Health · {pillar} · video {n}\n{title}"}
    return ep


def main():
    load_dotenv()
    day = sys.argv[1] if len(sys.argv) > 1 else (
        datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date().isoformat())
    HEALTH.mkdir(parents=True, exist_ok=True)
    todo = [n for n in range(1, PER_DAY + 1) if not (HEALTH / f"{day}_h{n}.json").exists()]
    if not todo:
        print(f"Videos for {day} already written.")
        return
    hist_file = HEALTH / "history.txt"
    history = hist_file.read_text(encoding="utf-8").splitlines() if hist_file.exists() else []
    eps = []
    for n in todo:
        ep = make_one(day, n, history)
        eps.append(ep)
        history.append(f"{ep['title']} | {day} | h{n}")
        print(f"Video {n} ({ep['pillar']}, {ep['format']}): {ep['title']}")
    for ep in eps:
        (HEALTH / f"{ep['slug']}.json").write_text(json.dumps(ep, indent=1, ensure_ascii=False), encoding="utf-8")
    hist_file.write_text("\n".join(history) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

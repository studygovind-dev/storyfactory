#!/usr/bin/env python3
"""
Story Factory - turns an episode JSON into a finished vertical video.

Steps (each result is cached in output/<series>_epXX/, so re-running only
redoes what is missing - you never pay twice for the same clip):
  1. image  : one still per scene   (Gemini image model)
  2. video  : animate each still    (Kling image-to-video)
  3. voice  : speak each line       (ElevenLabs)
  4. build  : join everything with subtitles + music (ffmpeg)
  5. send   : deliver to your Telegram for review

Usage:
  python pipeline/make_episode.py series/quiet_man_ep01.json            # real run
  python pipeline/make_episode.py series/quiet_man_ep01.json --dry-run  # free test, no APIs
  python pipeline/make_episode.py series/quiet_man_ep01.json --no-send
  python pipeline/make_episode.py series/quiet_man_ep01.json --free     # $0: Pollinations + edge-tts + zoom
"""
import argparse, base64, hmac, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
W, H = 1080, 1920
SCENE_MIN = 3.0      # shortest a scene may be (seconds)
PAD = 0.15           # breathing room after each spoken line


# ---------------------------------------------------------------- helpers
def env(name, required=True):
    v = os.environ.get(name, "").strip().lstrip("﻿")  # Windows tools can add an invisible BOM
    if required and not v:
        sys.exit(f"Missing {name}. Put it in .env (see .env.example).")
    return v


def load_dotenv():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg/ffprobe failed:\n{' '.join(map(str, cmd))}\n{r.stderr[-1500:]}")
    return r.stdout


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
               "-of", "default=nw=1:nk=1", str(path)])
    return float(out.strip())


def expand(text, chars):
    """Replace [[name]] with that character's fixed visual description."""
    return re.sub(r"\[\[(\w+)\]\]", lambda m: chars[m.group(1)]["look"], text)


# ---------------------------------------------------------------- 1. images
POLLEN_EMPTY = False  # set once the account balance runs out, so later scenes skip straight to the fallback


def make_image_free(ep, i, scene, out):
    """Picture from Pollinations. Uses the account key (realistic faces) while it has pollen,
    then falls back to the no-account server so the video still gets made."""
    global POLLEN_EMPTY
    prompt = (f"{ep['style']}. {expand(scene['image'], ep['characters'])}. "
              "No text, no watermark, no logos.")
    key = "" if POLLEN_EMPTY else os.environ.get("POLLINATIONS_KEY", "").strip().lstrip("﻿")
    q = requests.utils.quote(prompt[:1500], safe="")
    if key:
        url = "https://gen.pollinations.ai/image/" + q
        model = os.environ.get("POLLINATIONS_MODEL", "black-forest-labs/flux.2-klein-4b")
    else:  # no-account server: weaker model, busy often, stamps a logo
        url = "https://image.pollinations.ai/prompt/" + q
        model = "flux"
    params = {"width": 720, "height": 1280, "seed": 1000 + i, "nologo": "true", "model": model}
    hdr = {"Authorization": f"Bearer {key}"} if key else {}
    for attempt in range(30):  # up to ~8 minutes per picture
        try:
            r = requests.get(url, params=params, headers=hdr, timeout=180)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                raw = out.with_suffix(".jpg")
                raw.write_bytes(r.content)
                # The no-account server stamps a small logo at the bottom; cut that strip off.
                vf = "null" if key else "crop=iw:ih*0.93:0:0"
                run(["ffmpeg", "-y", "-i", str(raw), "-vf", vf, str(out)])
                raw.unlink()
                return
            if r.status_code in (401, 403):
                sys.exit(f"Pollinations refused the key ({r.status_code}): {r.text[:300]}")
            if key and r.status_code == 402:
                print("  Pollinations balance is empty (top up at enter.pollinations.ai), "
                      "using the free no-account pictures for the rest of this video.")
                POLLEN_EMPTY = True
                return make_image_free(ep, i, scene, out)
            print(f"  picture server busy ({r.status_code}), retrying...")
        except requests.RequestException as e:
            print(f"  picture server error ({type(e).__name__}), retrying...")
        params["seed"] += 100  # a new seed sometimes gets through faster
        time.sleep(15)
    sys.exit(f"Free picture server kept refusing scene {i}. Try again later.")


def make_image(ep, i, scene, out, dry):
    if out.exists():
        return
    if dry:
        colors = ["0x1b2a41", "0x324a5f", "0x0c1821", "0x3d2c2e"]
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={colors[i % 4]}:s={W}x{H}",
             "-frames:v", "1", str(out)])
        return
    prompt = (f"{ep['style']}. {expand(scene['image'], ep['characters'])}. "
              "No text, no watermark, no logos.")
    parts = [{"text": prompt}]
    # Optional: reference photos keep faces consistent across scenes/episodes.
    # Put a PNG at assets/characters/<name>.png for each character.
    for name in re.findall(r"\[\[(\w+)\]\]", scene["image"]):
        ref = ROOT / "assets" / "characters" / f"{name}.png"
        if ref.exists():
            parts.append({"inline_data": {"mime_type": "image/png",
                                          "data": base64.b64encode(ref.read_bytes()).decode()}})
    model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(url, headers={"x-goog-api-key": env("GEMINI_API_KEY")},
                      json={"contents": [{"parts": parts}]}, timeout=180)
    if not r.ok:
        sys.exit(f"Gemini error {r.status_code} on scene {i}: {r.text[:800]}")
    for cand in r.json().get("candidates", []):
        for p in cand["content"]["parts"]:
            data = p.get("inlineData") or p.get("inline_data")
            if data:
                out.write_bytes(base64.b64decode(data["data"]))
                return
    sys.exit(f"Gemini returned no image for scene {i}: {r.text[:500]}")


# ---------------------------------------------------------------- 2. video
def kling_token():
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=")
    head = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    body = b64(json.dumps({"iss": env("KLING_ACCESS_KEY"), "exp": now + 1800, "nbf": now - 5}).encode())
    sig = b64(hmac.new(env("KLING_SECRET_KEY").encode(), head + b"." + body, hashlib.sha256).digest())
    return (head + b"." + body + b"." + sig).decode()


def make_clip(ep, i, scene, img, out, dry, zoom=False):
    if out.exists():
        return
    if dry or zoom:  # free mode: camera move on the still picture (no Kling needed)
        step = 0.004 if ep.get("short") else 0.0015  # shorts change picture every ~2.5 s: move faster
        z = (f"min(zoom+{step},1.25)" if i % 2 == 0
             else f"if(eq(on,0),1.25,max(zoom-{step},1.0))")  # alternate zoom in / zoom out
        run(["ffmpeg", "-y", "-loop", "1", "-i", str(img), "-t", "5", "-r", "24",
             "-vf", (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase,crop={W * 2}:{H * 2},"
                     f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=120:s={W}x{H}:fps=24"),
             "-pix_fmt", "yuv420p", str(out)])
        return
    base = os.environ.get("KLING_BASE", "https://api.klingai.com")
    hdr = {"Authorization": f"Bearer {kling_token()}", "Content-Type": "application/json"}
    payload = {
        "model_name": os.environ.get("KLING_MODEL", "kling-v2-1"),
        "mode": os.environ.get("KLING_MODE", "std"),
        "duration": "5",
        "aspect_ratio": "9:16",
        "image": base64.b64encode(img.read_bytes()).decode(),
        "prompt": f"{scene['motion']}. Cinematic, natural realistic movement, no text.",
    }
    r = requests.post(f"{base}/v1/videos/image2video", headers=hdr, json=payload, timeout=120)
    r.raise_for_status()
    task = r.json()["data"]["task_id"]
    for _ in range(120):  # up to ~20 min
        time.sleep(10)
        hdr["Authorization"] = f"Bearer {kling_token()}"
        s = requests.get(f"{base}/v1/videos/image2video/{task}", headers=hdr, timeout=60).json()["data"]
        if s["task_status"] == "succeed":
            url = s["task_result"]["videos"][0]["url"]
            out.write_bytes(requests.get(url, timeout=300).content)
            return
        if s["task_status"] == "failed":
            sys.exit(f"Kling failed on scene {i}: {s.get('task_status_msg')}")
    sys.exit(f"Kling timed out on scene {i}")


# ---------------------------------------------------------------- 3. voice
# Free Microsoft voices (edge-tts) for each voice name used in the series files.
# Chosen for love stories: Neerja (Indian English) for women, Andrew (warm) for men,
# spoken a little slower and lower so it sounds close and intimate.
EDGE_VOICES = {
    "narrator_male": "en-US-AndrewNeural", "narrator_female": "en-IN-NeerjaExpressiveNeural",
    "male_young": "en-US-BrianNeural", "male_young2": "en-US-AndrewNeural",
    "male_adult": "en-US-AndrewNeural", "male_old": "en-US-GuyNeural",
    "female_young": "en-IN-NeerjaExpressiveNeural", "female_adult": "en-IN-NeerjaExpressiveNeural",
    "female_old": "en-IN-NeerjaExpressiveNeural",
    "child_girl": "en-US-AnaNeural", "child_boy": "en-US-AnaNeural",
    # older story files
    "male_deep": "en-US-GuyNeural", "male_gruff": "en-US-GuyNeural",
    "male_smooth": "en-US-AndrewNeural", "female_warm": "en-IN-NeerjaExpressiveNeural",
    "female_soft": "en-IN-NeerjaExpressiveNeural",
    "cartoon_male": "en-US-AnaNeural", "cartoon_female": "en-US-AnaNeural",
}

# ElevenLabs voices matched to age (public library voices). A VOICE_<NAME> setting in .env
# or GitHub Secrets wins; women and children fall back to VOICE_FEMALE / VOICE_CHILD.
ELEVEN_DEFAULTS = {  # all chosen by ear from the ElevenLabs voice library
    "MALE_YOUNG": "3XOBzXhnDY98yeWQ3GdM",      # men in their 20s
    "FEMALE_YOUNG": "Bsa1HP3wF8JGRzGouFEa",    # women in their 20s
    "NARRATOR_MALE": "WyxfC66zZ4F16RqcMMHI",   # male storyteller, around 30
    "NARRATOR_FEMALE": "DtsPFCrhbCbbJkwZsb3d", # female storyteller
    "CARTOON_MALE": "XjGYkUkzth8BPs29fmcV",    # cartoon boys, male animals
    "CARTOON_FEMALE": "XJ2fW4ybq7HouelYYGcL",  # cartoon girls, baby girls, female animals
}
# Older voice names map onto the chosen ones.
for _k, _v in {"MALE_YOUNG2": "MALE_YOUNG", "MALE_ADULT": "NARRATOR_MALE", "MALE_OLD": "NARRATOR_MALE",
               "MALE_DEEP": "NARRATOR_MALE", "MALE_GRUFF": "NARRATOR_MALE", "MALE_SMOOTH": "MALE_YOUNG",
               "FEMALE_ADULT": "NARRATOR_FEMALE", "FEMALE_OLD": "NARRATOR_FEMALE",
               "CHILD_BOY": "CARTOON_MALE", "CHILD_GIRL": "CARTOON_FEMALE"}.items():
    ELEVEN_DEFAULTS[_k] = ELEVEN_DEFAULTS[_v]
VOICE_RATE, VOICE_PITCH = "+5%", "-3Hz"   # natural pace, slightly lower pitch for warmth


def make_voice_free(ep, i, scene, out):
    voice_key = ep["characters"][scene["speaker"]]["voice"].lower()
    voice = EDGE_VOICES.get(voice_key) or (
        "en-US-AnaNeural" if voice_key.startswith("child") else
        EDGE_VOICES["female_soft"] if "female" in voice_key else EDGE_VOICES["male_smooth"])
    text = scene["line"].replace("*", "").replace("_", " ")  # drop markdown emphasis
    for attempt in range(6):  # the free voice service sometimes refuses a request; wait and retry
        r = subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice, "--text", text,
                            f"--rate={VOICE_RATE}", f"--pitch={VOICE_PITCH}",
                            "--write-media", str(out)], capture_output=True, text=True)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            return
        print(f"  voice service refused scene {i + 1}, retrying...")
        time.sleep(10 * (attempt + 1))
    sys.exit(f"Free voice failed on scene {i} (pip install edge-tts):\n{r.stderr[-800:]}")


def make_voice(ep, i, scene, out, dry):
    if out.exists():
        return
    if dry:  # a quiet tone whose length matches the words, just to test timing
        secs = max(2.0, len(scene["line"].split()) * 0.4)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", f"sine=frequency=220:duration={secs}",
             "-af", "volume=0.05", str(out)])
        return
    voice_key = ep["characters"][scene["speaker"]]["voice"]
    # Simple setup: only 3 voices needed (VOICE_MALE, VOICE_FEMALE, VOICE_CHILD).
    # A specific VOICE_<NAME> in .env still wins if you set one.
    k = voice_key.upper()
    fallback = "VOICE_CHILD" if k.startswith("CHILD") else (
        "VOICE_FEMALE" if "FEMALE" in k else "VOICE_MALE")
    # The voices picked by ear (ELEVEN_DEFAULTS) win over older VOICE_* settings.
    voice_id = (ELEVEN_DEFAULTS.get(k) or os.environ.get("VOICE_" + k, "").strip()
                or env(fallback))
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128",
        headers={"xi-api-key": env("ELEVEN_API_KEY")},
        json={"text": scene["line"].replace("*", ""),
              "model_id": os.environ.get("ELEVEN_MODEL", "eleven_multilingual_v2"),
              # lower stability + more style = softer, more emotional delivery
              "voice_settings": {"stability": 0.35, "similarity_boost": 0.8, "style": 0.5}},
        timeout=120)
    r.raise_for_status()
    out.write_bytes(r.content)


ELEVEN_OFF = False  # set when ElevenLabs credits run out, so the rest of the video uses free voices


def make_voice_best(ep, i, scene, out):
    """ElevenLabs voice when a key is set (best, most natural), free voice as backup."""
    global ELEVEN_OFF
    if not ELEVEN_OFF and os.environ.get("ELEVEN_API_KEY", "").strip():
        for attempt in range(3):
            try:
                make_voice(ep, i, scene, out, False)
                return
            except requests.HTTPError as e:
                code = e.response.status_code
                if code in (401, 402, 403) or "quota" in e.response.text:
                    print(f"  ElevenLabs refused ({code}: {e.response.text[:150]}); "
                          "using free voices for the rest of this video.")
                    ELEVEN_OFF = True
                    break
                print(f"  ElevenLabs busy ({code}), retrying...")
            except requests.RequestException:
                print("  ElevenLabs connection error, retrying...")
            time.sleep(10 * (attempt + 1))
    make_voice_free(ep, i, scene, out)


# ---------------------------------------------------------------- 4. build
def ts(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


HANDLE = "@storybitetv2"


def word_captions(line, start, end):
    """Show the line 2-3 words at a time (big, centre), timed by word length, the key word yellow."""
    words = line.replace("*", "").replace("\n", " ").split()
    chunks = [words[k:k + 3] for k in range(0, len(words), 3)]
    if len(chunks) > 1 and len(chunks[-1]) == 1:  # no lonely last word
        last = chunks.pop()
        chunks[-1] += last
    total = sum(len(" ".join(c)) for c in chunks) or 1
    out, t = [], start
    for c in chunks:
        d = (end - start) * len(" ".join(c)) / total
        longest = max(range(len(c)), key=lambda k: len(c[k]))
        text = " ".join(r"{\c&H0000E5FF&}" + w + r"{\c&HFFFFFF&}" if k == longest else w
                        for k, w in enumerate(c))
        out.append(f"Dialogue: 0,{ts(t)},{ts(t + d)},Word,,0,0,0,,{{\\fscx80\\fscy80\\t(0,120,\\fscx100\\fscy100)}}{text}")
        t += d
    return out


def build(ep, work, final):
    short = ep.get("short")
    seg_files, ass_events, t = [], [], 0.0
    for i, sc in enumerate(ep["scenes"]):
        clip, voice = work / f"clip_{i}.mp4", work / f"voice_{i}.mp3"
        d = max(1.2, duration(voice) + 0.05) if short else max(SCENE_MIN, duration(voice) + PAD)
        seg = work / f"seg_{i}.mp4"
        # Hold the last frame if the speech is longer than the clip; trim if shorter.
        vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
              f"fps=24,tpad=stop_mode=clone:stop_duration=10,trim=duration={d:.3f},setpts=PTS-STARTPTS")
        af = f"adelay=150|150,apad,atrim=duration={d:.3f}"
        run(["ffmpeg", "-y", "-i", str(clip), "-i", str(voice),
             "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-ar", "44100", "-ac", "2", str(seg)])
        seg_files.append(seg)
        if short:
            ass_events += word_captions(sc["line"], t + 0.15, t + d)
            t += d
            continue
        text = sc["line"].replace("\n", " ")
        if len(text) > 38:  # split long lines into two caption lines
            mid = text.rfind(" ", 0, len(text) // 2 + 8)
            text = text[:mid] + "\\N" + text[mid + 1:]
        ass_events.append(f"Dialogue: 0,{ts(t + 0.1)},{ts(t + d - 0.1)},Cap,,0,0,0,,{text}")
        t += d

    if ep.get("parts"):  # daily stories: keep "Part 2 of 3" on screen so viewers know there is more
        ass_events.insert(0, f"Dialogue: 0,{ts(0)},{ts(t)},Top,,0,0,0,,"
                             f"PART {ep['episode']} OF {ep['parts']}")
    if short:
        ass_events.append(f"Dialogue: 1,{ts(0)},{ts(t)},Mark,,0,0,0,,{HANDLE}")
        if ep.get("hook_text"):
            ass_events.append(f"Dialogue: 1,{ts(0)},{ts(min(3.0, t))},Hook,,0,0,0,,"
                              f"{ep['hook_text'].upper()}")
        ass_events.append(f"Dialogue: 1,{ts(max(0, t - 3.0))},{ts(t)},Hook,,0,0,0,,"
                          f"FOLLOW {HANDLE.upper()}\\NFOR MORE STORIES")

    ass = work / "subs.ass"
    ass.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,"
        "MarginL,MarginR,MarginV,Encoding\n"
        "Style: Cap,Arial,64,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,70,70,330,1\n"
        "Style: Top,Arial,52,&H0000D7FF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,1,4,1,8,70,70,170,1\n"
        # shorts: big word-by-word captions in the middle, hook / follow text at the top, small handle
        "Style: Word,Arial,96,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1\n"
        "Style: Hook,Arial,78,&H0000E5FF,&H000000FF,&H00000000,&HA0000000,-1,0,0,0,100,100,1,0,3,6,0,8,60,60,230,1\n"
        "Style: Mark,Arial,40,&H90FFFFFF,&H000000FF,&H90000000,&H00000000,-1,0,0,0,100,100,1,0,1,2,0,9,50,50,90,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n" % (W, H)
        + "\n".join(ass_events) + "\n")

    lst = work / "list.txt"
    lst.write_text("".join(f"file '{p.name}'\n" for p in seg_files))
    joined = work / "joined.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)])

    music = ROOT / "assets" / "music.mp3"   # optional royalty-free track
    cmd = ["ffmpeg", "-y", "-i", str(joined)]
    sub = f"subtitles={ass.name}"
    if music.exists():
        cmd += ["-stream_loop", "-1", "-i", str(music), "-filter_complex",
                f"[0:v]{sub}[v];[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                "-map", "[v]", "-map", "[a]"]
    else:
        cmd += ["-vf", sub]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)]
    r = subprocess.run(cmd, cwd=work, capture_output=True, text=True)
    if r.returncode:
        sys.exit("Final render failed:\n" + r.stderr[-1500:])
    return t


MAX_SECS = 178.0  # Shorts / Reels limit is 3:00; keep a little margin
SHORT_MAX_SECS = 62.0  # daily single stories aim for under about a minute


def speed_to_fit(final, total, limit=MAX_SECS):
    """Speed the whole video up slightly (voice pitch unchanged) so it ends under the limit."""
    f = total / limit
    if f > 1.25:
        print(f"Warning: video is {total:.0f}s; speeding up only 25%, it will stay over {limit:.0f}s.")
        f = 1.25
    tmp = final.with_name("final_fast.mp4")
    run(["ffmpeg", "-y", "-i", str(final), "-filter_complex",
         f"[0:v]setpts=PTS/{f:.4f}[v];[0:a]atempo={f:.4f}[a]", "-map", "[v]", "-map", "[a]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(tmp)])
    tmp.replace(final)
    print(f"Sped up {f:.2f}x to fit under {limit:.0f}s.")
    return total / f


# ---------------------------------------------------------------- 5. send
TELEGRAM_MAX_MB = 48  # bots may send up to 50 MB


def fit_for_telegram(final):
    """Re-encode at a lower bitrate if the video is too big for a Telegram bot."""
    if final.stat().st_size <= TELEGRAM_MAX_MB * 1024 * 1024:
        return final
    secs = duration(final)
    kbps = int(TELEGRAM_MAX_MB * 8192 * 0.92 / secs) - 128  # leave room for 128k audio
    small = final.with_name("final_small.mp4")
    run(["ffmpeg", "-y", "-i", str(final), "-c:v", "libx264", "-preset", "medium",
         "-b:v", f"{kbps}k", "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(small)])
    return small


def send_telegram(final, ep):
    token, chat = env("TELEGRAM_BOT_TOKEN"), env("TELEGRAM_CHAT_ID")
    final = fit_for_telegram(final)
    if ep.get("short"):
        cap = f"📌 Story #{ep['story_no']} · Video {ep['episode']} of 3 today\n{ep['title']}"
    elif ep.get("story_no"):
        cap = (f"📌 Story #{ep['story_no']} · Part {ep['episode']} of {ep['parts']}\n"
               f"{ep['series']}: {ep['title']}")
    else:
        cap = f"{ep['series']} - Ep {ep['episode']}: {ep['title']}\n\n{ep['caption']}"
    with open(final, "rb") as f:
        r = requests.post(f"https://api.telegram.org/bot{token}/sendVideo",
                          data={"chat_id": chat, "caption": cap[:1000], "supports_streaming": "true"},
                          files={"video": f}, timeout=600)
    r.raise_for_status()
    if ep.get("story_no"):
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": post_kit(ep)[:4000]}, timeout=60).raise_for_status()
    print("Sent to Telegram.")


NEXT_AT = {1: "1 PM", 2: "6 PM"}


def post_kit(ep):
    """Copy-ready posting details sent right after each daily video."""
    tags = " ".join(ep.get("hashtags") or ["#shorts", "#drama", "#story"])
    if ep.get("short"):
        follow = f"👉 Follow {HANDLE} for 3 new stories every day!"
        return (
            f"📌 Story #{ep['story_no']}\n\n"
            f"━━ TITLE (YouTube / Facebook) ━━\n{ep['yt_title']}\n\n"
            f"━━ DESCRIPTION ━━\n{ep.get('description', '').strip()}\n\n{follow}\n\n"
            f"━━ HASHTAGS ━━\n{tags}\n\n"
            f"━━ INSTAGRAM CAPTION ━━\n{ep['yt_title']}\n{follow}\n\n{tags}\n\n"
            "⚠️ Turn ON the AI-generated content label when posting.\n"
            "📍 Pin a comment that repeats the question from the end of the video."
        )
    n, total = ep["episode"], ep["parts"]
    nxt = (f"👉 Part {n + 1} today at {NEXT_AT[n]}. Follow so you don't miss it!"
           if n < total else "✅ Final part. Follow for a new story every day!")
    return (
        f"📌 Story #{ep['story_no']} · Part {n} of {total}\n\n"
        f"━━ TITLE (YouTube / Facebook) ━━\n{ep['yt_title']}\n\n"
        f"━━ DESCRIPTION ━━\n{ep.get('description', '').strip()}\n\n{nxt}\n\n"
        f"━━ HASHTAGS ━━\n{tags}\n\n"
        f"━━ INSTAGRAM CAPTION ━━\n{ep['yt_title']}\n{nxt}\n\n{tags}\n\n"
        "⚠️ Turn ON the AI-generated content label when posting.\n"
        "📍 YouTube: add to the playlist for this story. Pin a comment: \"Which part was best?\""
    )


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episode")
    ap.add_argument("--dry-run", action="store_true", help="free test with placeholder media")
    ap.add_argument("--no-send", action="store_true")
    ap.add_argument("--no-kling", action="store_true",
                    help="real pictures + real voice, but slow zoom instead of Kling video (cheap)")
    ap.add_argument("--free", action="store_true",
                    help="$0: free pictures (Pollinations) + free voices (edge-tts) + slow zoom")
    a = ap.parse_args()
    load_dotenv()

    ep = json.loads(Path(a.episode).read_text(encoding="utf-8"))
    tag = "_dry" if a.dry_run else "_free" if a.free else "_zoom" if a.no_kling else ""
    if ep.get("slug"):  # daily stories: output/<date>_partN_free
        work = ROOT / "output" / f"{ep['slug']}{tag}"
    else:
        slug = re.sub(r"\W+", "_", ep["series"].lower()).strip("_")
        work = ROOT / "output" / f"{slug}_ep{ep['episode']:02d}{tag}"
    work.mkdir(parents=True, exist_ok=True)
    # Budget mode: in --free runs, animate the first N scenes of each part with Kling (paid).
    kling_first = int(os.environ.get("KLING_CLIPS_PER_PART", "0") or 0) if a.free else 0

    for i, sc in enumerate(ep["scenes"]):
        print(f"scene {i + 1}/{len(ep['scenes'])}")
        img, voice = work / f"img_{i}.png", work / f"voice_{i}.mp3"
        if a.free:
            # Pictures cost pollen: one picture covers 3 scenes (each gets a different zoom).
            # Shorts get a new picture every line (fast cuts keep viewers watching).
            img = work / f"img_{i if ep.get('short') else i - i % 3}.png"
            if not img.exists():
                make_image_free(ep, i, sc, img)
            if not voice.exists():
                make_voice_best(ep, i, sc, voice)
        else:
            make_image(ep, i, sc, img, a.dry_run)
            make_voice(ep, i, sc, voice, a.dry_run)
        zoom = a.no_kling or (a.free and i >= kling_first)
        make_clip(ep, i, sc, img, work / f"clip_{i}.mp4", a.dry_run, zoom)

    final = work / "final.mp4"
    total = build(ep, work, final)
    limit = SHORT_MAX_SECS if ep.get("short") else MAX_SECS
    if (ep.get("parts") or ep.get("short")) and total > limit:  # must fit the Shorts length
        total = speed_to_fit(final, total, limit)
    print(f"Done: {final}  ({total:.1f}s)")
    if not a.no_send and not a.dry_run:
        send_telegram(final, ep)


if __name__ == "__main__":
    main()

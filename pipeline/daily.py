#!/usr/bin/env python3
"""
Daily runner (used by GitHub Actions). Sends today's 2 short videos at 9:00 and 17:00 India time.

GitHub starts scheduled runs late or skips them on busy days, so this is
safe to run many times a day: each run makes every part that is due and
not sent yet, waits until its send time if it is early, then sends it.
A marker file series/daily/<date>_partN.sent records what was delivered.

Usage:
  python pipeline/daily.py           # do whatever is due now
  python pipeline/daily.py --part 2  # make and send part 2 now (manual)
"""
import argparse, datetime, json, os, subprocess, sys, time

import requests
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import ROOT, env, load_dotenv, send_telegram  # noqa: E402
from post_social import post_all  # noqa: E402

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
SEND_AT = {1: (9, 0), 2: (17, 0)}  # 2 short videos a day (saves ElevenLabs credits)
START_EARLY = datetime.timedelta(minutes=120)  # a 50-second video takes about 10-20 minutes to make
DAILY = ROOT / "series" / "daily"


def sh(*cmd):
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def save_to_repo(msg):
    """Commit story/marker files so later runs (fresh GitHub machines) can see them."""
    sh("git", "add", "series/daily")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        sh("git", "commit", "-q", "-m", msg)
        for _ in range(3):
            if sh("git", "push", "-q") == 0:
                return
            sh("git", "pull", "-q", "--rebase")


def eleven_credits_ok():
    """False (and a Telegram warning) when ElevenLabs credits are too low for a video, so we never
    post a video in the robotic free voice."""
    key = os.environ.get("ELEVEN_API_KEY", "").strip()
    if not key or os.environ.get("AZURE_SPEECH_KEY", "").strip():
        return True  # no ElevenLabs, or Azure Speech is the backup voice
    try:
        r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key},
                         timeout=30)
        if not r.ok:
            return True  # cannot tell: let the video try
        sub = r.json()
        left = sub["character_limit"] - sub["character_count"]
    except (requests.RequestException, KeyError, ValueError):
        return True
    if left >= 1500:
        return True
    requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
                  data={"chat_id": env("TELEGRAM_CHAT_ID"),
                        "text": f"⚠️ ElevenLabs credits are almost out ({left} left). Videos will use the free "
                                "backup voice until you add credits or the monthly reset."},
                  timeout=60)
    return True  # still make the video: the free voice covers it


def make_and_send(day, part, wait):
    ep_file = DAILY / f"{day}_part{part}.json"
    marker = DAILY / f"{day}_part{part}.sent"
    if marker.exists():
        print(f"Part {part} already sent today.")
        return True
    if not eleven_credits_ok():
        return False
    if subprocess.run([sys.executable, str(ROOT / "pipeline" / "make_episode.py"),
                       str(ep_file), "--free", "--no-send"], cwd=ROOT).returncode:
        print(f"Making part {part} failed.")
        return False
    h, m = SEND_AT[part]
    send_time = datetime.datetime.now(IST).replace(hour=h, minute=m, second=0, microsecond=0)
    early = (send_time - datetime.datetime.now(IST)).total_seconds()
    if wait and early > 0:
        print(f"Part {part} is ready; waiting {early / 60:.0f} min until {h:02d}:{m:02d}.", flush=True)
        time.sleep(early)
    ep = json.loads(ep_file.read_text(encoding="utf-8"))
    video = ROOT / "output" / f"{day}_part{part}_free" / "final.mp4"
    send_telegram(video, ep)
    teaser = video.with_name("teaser.mp4")
    if teaser.exists():  # the under-90 s cut, for YouTube Shorts / Reels
        with open(teaser, "rb") as f:
            requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendVideo",
                          data={"chat_id": env("TELEGRAM_CHAT_ID"), "supports_streaming": "true",
                                "caption": "🎬 Short version (under 90 s) for YouTube Shorts / Reels"},
                          files={"video": f}, timeout=600)
    problems = post_all(video, ep)  # Facebook + Instagram, when FB_PAGE_ID / FB_PAGE_TOKEN are set
    if problems:  # tell the owner so they can post that one by hand
        requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
                      data={"chat_id": env("TELEGRAM_CHAT_ID"),
                            "text": "⚠️ Auto-posting failed, please post this one by hand:\n"
                                    + "\n".join(problems)}, timeout=60)
    marker.write_text(datetime.datetime.now(IST).isoformat() + "\n")
    save_to_repo(f"Sent part {part} for {day}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, choices=[1, 2], help="make and send this part now")
    ap.add_argument("--day", help="story date YYYY-MM-DD (default: today, India time)")
    a = ap.parse_args()
    load_dotenv()
    now = datetime.datetime.now(IST)
    day = a.day or now.date().isoformat()

    if a.part:
        due = [a.part]
    else:
        due = [p for p, (h, m) in SEND_AT.items()
               if now >= now.replace(hour=h, minute=m, second=0, microsecond=0) - START_EARLY
               and not (DAILY / f"{day}_part{p}.sent").exists()]
    if not due:
        print(f"Nothing due right now ({now:%H:%M} IST).")
        return

    if not (DAILY / f"{day}_part1.json").exists():
        if sh(sys.executable, str(ROOT / "pipeline" / "write_story.py"), day):
            sys.exit("Could not write today's story.")
        save_to_repo(f"Story for {day}")

    failed = [p for p in due if not make_and_send(day, p, wait=not a.part)]
    if failed:
        sys.exit(f"Parts {failed} failed; the next scheduled run will try again.")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Daily runner (used by GitHub Actions). Sends today's story in 3 parts:
  story at 9:00, cartoon at 13:00, story at 17:00 India time.

GitHub starts scheduled runs late or skips them on busy days, so this is
safe to run many times a day: each run makes every part that is due and
not sent yet, waits until its send time if it is early, then sends it.
A marker file series/daily/<date>_partN.sent records what was delivered.

Usage:
  python pipeline/daily.py           # do whatever is due now
  python pipeline/daily.py --part 2  # make and send part 2 now (manual)
"""
import argparse, datetime, json, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import ROOT, load_dotenv, send_telegram  # noqa: E402

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
SEND_AT = {1: (9, 0), 2: (13, 0), 3: (17, 0)}
START_EARLY = datetime.timedelta(minutes=170)  # a 4-minute video takes 40-70 minutes to make
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


def make_and_send(day, part, wait):
    ep_file = DAILY / f"{day}_part{part}.json"
    marker = DAILY / f"{day}_part{part}.sent"
    if marker.exists():
        print(f"Part {part} already sent today.")
        return True
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
    send_telegram(ROOT / "output" / f"{day}_part{part}_free" / "final.mp4", ep)
    marker.write_text(datetime.datetime.now(IST).isoformat() + "\n")
    save_to_repo(f"Sent part {part} for {day}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, choices=[1, 2, 3], help="make and send this part now")
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

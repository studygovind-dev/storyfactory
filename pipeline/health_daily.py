#!/usr/bin/env python3
"""
Money Mind Health runner (used by GitHub Actions): makes and posts the day's funny health videos.

Send times (India time): 8:00, 10:30, 13:00, 15:30, 18:00, 20:30. MMH_PER_DAY (default 5) of them are used.
Like pipeline/daily.py, it is safe to run many times a day: each run makes every video that is due and not
sent yet, waits until its send time, sends it to Telegram and posts it to the Money Mind Health Page.
A marker series/health/<date>_h<N>.sent records what was delivered.

Usage:
  python pipeline/health_daily.py                # do whatever is due now
  python pipeline/health_daily.py --part 1       # make video 1 right now (manual)
  python pipeline/health_daily.py --part 1 --dry # make it and send to Telegram only, do not post or mark
"""
import argparse, datetime, json, os, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import ROOT, env, load_dotenv, send_telegram  # noqa: E402
from post_social import mmh_token_problem, post_mmh  # noqa: E402

IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
ALL_TIMES = [(8, 0), (10, 30), (13, 0), (15, 30), (18, 0), (20, 30)]
PER_DAY = max(1, min(6, int(os.environ.get("MMH_PER_DAY", "5") or 5)))
SEND_AT = {n + 1: ALL_TIMES[n] for n in range(PER_DAY)}
START_EARLY = datetime.timedelta(minutes=75)
HEALTH = ROOT / "series" / "health"


def sh(*cmd):
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT).returncode


def save_to_repo(msg):
    sh("git", "add", "series/health")
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        sh("git", "commit", "-q", "-m", msg)
        for _ in range(3):
            if sh("git", "push", "-q") == 0:
                return
            sh("git", "pull", "-q", "--rebase")


def make_and_send(day, part, wait, dry):
    ep_file = HEALTH / f"{day}_h{part}.json"
    marker = HEALTH / f"{day}_h{part}.sent"
    if marker.exists() and not dry:
        print(f"Health video {part} already sent today.")
        return True
    if subprocess.run([sys.executable, str(ROOT / "pipeline" / "make_episode.py"),
                       str(ep_file), "--free", "--no-send"], cwd=ROOT).returncode:
        print(f"Making health video {part} failed.")
        return False
    ep = json.loads(ep_file.read_text(encoding="utf-8"))
    video = ROOT / "output" / f"{day}_h{part}_free" / "final.mp4"
    if not dry:
        h, m = SEND_AT[part]
        send_time = datetime.datetime.now(IST).replace(hour=h, minute=m, second=0, microsecond=0)
        early = (send_time - datetime.datetime.now(IST)).total_seconds()
        if wait and early > 0:
            print(f"Health video {part} is ready; waiting {early / 60:.0f} min until {h:02d}:{m:02d}.", flush=True)
            time.sleep(early)
    send_telegram(video, ep)
    if dry:
        import requests
        for img in sorted(video.parent.glob("img_*.png"))[:6]:  # the pictures themselves, to judge their quality
            with open(img, "rb") as fh:
                requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendPhoto",
                              data={"chat_id": env("TELEGRAM_CHAT_ID"), "caption": f"picture {img.stem}"},
                              files={"photo": fh}, timeout=120)
        print("Dry run: not posting and not marking as sent.")
        return True
    problems = post_mmh(video, ep)
    if problems:
        import requests
        requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
                      data={"chat_id": env("TELEGRAM_CHAT_ID"),
                            "text": "⚠️ Money Mind Health: auto-posting failed, please post this one by hand:\n"
                                    + "\n".join(problems)}, timeout=60)
    marker.write_text(datetime.datetime.now(IST).isoformat() + "\n")
    save_to_repo(f"Sent health video {part} for {day}")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", type=int, help="make this video now")
    ap.add_argument("--day", help="date YYYY-MM-DD (default today, India time)")
    ap.add_argument("--dry", action="store_true", help="Telegram only: do not post, do not mark as sent")
    a = ap.parse_args()
    load_dotenv()
    now = datetime.datetime.now(IST)
    day = a.day or now.date().isoformat()
    if a.part:
        if a.part not in SEND_AT:
            sys.exit(f"Part must be 1..{PER_DAY}")
        due = [a.part]
    else:
        due = [p for p, (h, m) in SEND_AT.items()
               if now >= now.replace(hour=h, minute=m, second=0, microsecond=0) - START_EARLY
               and not (HEALTH / f"{day}_h{p}.sent").exists()]
    if not due:
        print(f"Nothing due right now ({now:%H:%M} IST).")
        return
    if not a.dry:  # a dead Facebook token: say so once and do not waste an hour making videos nobody can post
        problem = mmh_token_problem()
        if problem:
            import requests
            print(f"Facebook token problem: {problem}")
            marker = HEALTH / f"{day}_token_alert.sent"
            if not marker.exists():
                requests.post(f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/sendMessage",
                              data={"chat_id": env("TELEGRAM_CHAT_ID"),
                                    "text": "⚠️ Money Mind Health: the Facebook token has expired, so no video is being "
                                            "made. Make a new long-lived Page token and update the GitHub secret "
                                            f"MM_FB_PAGE_TOKEN.\n{problem[:200]}"}, timeout=60)
                marker.write_text("alerted\n")
                save_to_repo(f"Token alert for {day}")
            return
    if any(not (HEALTH / f"{day}_h{p}.json").exists() for p in SEND_AT):
        if sh(sys.executable, str(ROOT / "pipeline" / "write_health.py"), day):
            sys.exit("Could not write today's health videos.")
        save_to_repo(f"Health videos for {day}")
    failed = []
    last_post = None
    for p in due:
        # never post several videos back to back: keep at least 40 minutes between posts in one run
        if last_post and not a.part and not a.dry:
            gap = 40 * 60 - (time.time() - last_post)
            if gap > 0:
                print(f"Waiting {gap / 60:.0f} min so posts are spread out.", flush=True)
                time.sleep(gap)
        if make_and_send(day, p, wait=not a.part, dry=a.dry):
            last_post = time.time()
        else:
            failed.append(p)
    if failed:
        sys.exit(f"Health videos {failed} failed; the next scheduled run will try again.")


if __name__ == "__main__":
    main()

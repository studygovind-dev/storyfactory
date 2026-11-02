#!/usr/bin/env python3
"""
Posts a finished daily video to the Facebook Page and to Instagram (as a Reel),
using Meta's official Graph API. Needs two GitHub Secrets:
  FB_PAGE_ID     the Page's id
  FB_PAGE_TOKEN  a Page access token with pages_manage_posts + instagram_content_publish
The Instagram account is found from the Page (it must be linked to it).

Usage (manual test):
  python pipeline/post_social.py output/<slug>_free/final.mp4 series/daily/<slug>.json [--fb-only|--ig-only]
"""
import json, os, subprocess, sys, time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import HANDLE, env, load_dotenv  # noqa: E402

GRAPH = "https://graph.facebook.com/" + os.environ.get("META_GRAPH_VERSION", "v24.0")


def caption(ep):
    tags = " ".join(ep.get("hashtags") or ["#story", "#viral"])
    return (f"{ep['yt_title']}\n\n{ep.get('description', '').strip()}\n\n"
            f"👉 Follow {HANDLE} for 3 new stories every day!\n\n{tags}")[:2100]


def check(r, what):
    if not r.ok:
        raise RuntimeError(f"{what} failed ({r.status_code}): {r.text[:400]}")
    return r.json()


TEST = os.environ.get("POST_TEST") == "1"  # upload but do not publish (for checking the setup)


def post_facebook(video, ep, page, token, hidden=False):
    """Chunked ("resumable") upload: the simple upload refuses files this big (error 413).
    hidden=True keeps the video unpublished (used to give Instagram a link to fetch)."""
    url = f"https://graph-video.facebook.com/{GRAPH.rsplit('/', 1)[1]}/{page}/videos"
    data = Path(video).read_bytes()
    s = check(requests.post(url, data={"access_token": token, "upload_phase": "start",
                                       "file_size": len(data)}, timeout=120), "Facebook upload start")
    start, end = int(s["start_offset"]), int(s["end_offset"])
    while start < end:
        r = check(requests.post(url, data={"access_token": token, "upload_phase": "transfer",
                                           "upload_session_id": s["upload_session_id"],
                                           "start_offset": start},
                                files={"video_file_chunk": ("chunk", data[start:end])}, timeout=600),
                  "Facebook upload")
        start, end = int(r["start_offset"]), int(r["end_offset"])
    check(requests.post(url, data={"access_token": token, "upload_phase": "finish",
                                   "upload_session_id": s["upload_session_id"],
                                   "title": ep["yt_title"][:250], "description": caption(ep),
                                   "published": "false" if (TEST or hidden) else "true"}, timeout=300),
          "Facebook upload finish")
    if not hidden:
        print(f"Facebook: {'uploaded (unpublished test)' if TEST else 'posted'} video {s.get('video_id')}")
    return s["video_id"]


def post_facebook_reel(video, ep, page, token):
    """Facebook Reels (reach new people far more than normal Page videos)."""
    url = f"{GRAPH}/{page}/video_reels"
    s = check(requests.post(url, data={"upload_phase": "start", "access_token": token}, timeout=60),
              "Facebook Reel start")
    data = Path(video).read_bytes()
    check(requests.post(s["upload_url"], data=data, timeout=1800,
                        headers={"Authorization": f"OAuth {token}", "offset": "0",
                                 "file_size": str(len(data))}), "Facebook Reel upload")
    check(requests.post(url, data={"upload_phase": "finish", "video_id": s["video_id"],
                                   "video_state": "DRAFT" if TEST else "PUBLISHED",
                                   "description": caption(ep), "access_token": token}, timeout=120),
          "Facebook Reel publish")
    print(f"Facebook Reels: {'uploaded as draft (test)' if TEST else 'posted'} reel {s['video_id']}")


def public_link(video):
    """Upload the file to the repo's 'reels' release (public repo) and return a direct link."""
    name = f"{int(time.time())}_{Path(video).parent.name}.mp4"
    subprocess.run(["gh", "release", "create", "reels", "--title", "Reels (temporary)",
                    "--notes", "Temporary copies for Instagram to fetch; deleted after posting."],
                   capture_output=True)  # fails harmlessly if it already exists
    tmp = Path(video).with_name(name)
    tmp.write_bytes(Path(video).read_bytes())
    r = subprocess.run(["gh", "release", "upload", "reels", str(tmp), "--clobber"],
                       capture_output=True, text=True)
    tmp.unlink()
    if r.returncode:
        raise RuntimeError(f"Could not make a public link for the reel: {r.stderr[-300:]}")
    url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/reels/{name}"
    # Instagram does not follow redirects well: hand it the final download address
    loc = requests.head(url, allow_redirects=False, timeout=60).headers.get("location") or url
    return loc, name


def post_instagram(video, ep, page, token):
    ig = check(requests.get(f"{GRAPH}/{page}", params={"fields": "instagram_business_account",
                                                       "access_token": token}, timeout=60),
               "Finding the Instagram account").get("instagram_business_account", {}).get("id")
    if not ig:
        raise RuntimeError("No Instagram account is linked to this Facebook Page.")
    # 1. Instagram's direct upload keeps failing, so put the reel on the public GitHub repo as a
    #    temporary download, give Instagram that link, and delete it again afterwards.
    src, asset = public_link(video)
    c = check(requests.post(f"{GRAPH}/{ig}/media",
                            data={"media_type": "REELS", "video_url": src, "caption": caption(ep),
                                  "share_to_feed": "true", "access_token": token}, timeout=120),
              "Instagram container")
    # 2. wait until Instagram has processed the video, then publish it
    for _ in range(60):
        st = check(requests.get(f"{GRAPH}/{c['id']}", params={"fields": "status_code,status",
                                                               "access_token": token}, timeout=60),
                   "Instagram status")
        if st.get("status_code") == "FINISHED":
            break
        if st.get("status_code") == "ERROR":
            raise RuntimeError(f"Instagram could not process the video: {st.get('status')}")
        time.sleep(15)
    else:
        raise RuntimeError("Instagram took over 15 minutes to process the video.")
    if asset:  # Instagram has its own copy now
        subprocess.run(["gh", "release", "delete-asset", "reels", asset, "-y"], capture_output=True)
    if TEST:
        print("Instagram: uploaded and processed OK (test, not published)")
        return
    r = check(requests.post(f"{GRAPH}/{ig}/media_publish",
                            data={"creation_id": c["id"], "access_token": token}, timeout=120),
              "Instagram publish")
    print(f"Instagram: posted reel {r.get('id')}")


def post_all(video, ep):
    """Post everywhere that is set up. Returns the list of problems (empty = all fine)."""
    page, token = os.environ.get("FB_PAGE_ID", "").strip(), os.environ.get("FB_PAGE_TOKEN", "").strip()
    if not (page and token):
        return []  # auto-posting not set up: nothing to do
    problems = []
    teaser = Path(video).with_name("teaser.mp4")  # Reels must be under 90 s
    jobs = [("Facebook", post_facebook, video, ep)]
    if teaser.exists():
        reel = {**ep, "yt_title": ep["yt_title"] + "\n\n▶️ Full story on our Facebook page & YouTube"}
        jobs.append(("Instagram", post_instagram, teaser, reel))
        jobs.append(("Facebook Reels", post_facebook_reel, teaser, reel))
    for name, fn, file, info in jobs:
        if os.environ.get("POST_ONLY") and os.environ["POST_ONLY"] != name:
            continue
        try:
            fn(file, info, page, token)
        except (RuntimeError, requests.RequestException) as e:
            print(f"{name}: {e}")
            problems.append(f"{name}: {e}")
    return problems


if __name__ == "__main__":
    load_dotenv()
    if "--fb-only" in sys.argv:
        os.environ["POST_ONLY"] = "Facebook"
    if "--ig-only" in sys.argv:
        os.environ["POST_ONLY"] = "Instagram"
    env("FB_PAGE_ID"), env("FB_PAGE_TOKEN")
    sys.exit(1 if post_all(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
             else 0)

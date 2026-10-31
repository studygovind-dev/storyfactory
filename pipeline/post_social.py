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
import json, os, sys, time
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


def post_facebook(video, ep, page, token):
    with open(video, "rb") as f:
        r = requests.post(f"https://graph-video.facebook.com/{GRAPH.rsplit('/', 1)[1]}/{page}/videos",
                          data={"access_token": token, "title": ep["yt_title"][:250],
                                "description": caption(ep)},
                          files={"source": f}, timeout=1800)
    print(f"Facebook: posted video {check(r, 'Facebook upload').get('id')}")


def post_instagram(video, ep, page, token):
    ig = check(requests.get(f"{GRAPH}/{page}", params={"fields": "instagram_business_account",
                                                       "access_token": token}, timeout=60),
               "Finding the Instagram account").get("instagram_business_account", {}).get("id")
    if not ig:
        raise RuntimeError("No Instagram account is linked to this Facebook Page.")
    # 1. create a Reel container for a direct (resumable) upload of our file
    c = check(requests.post(f"{GRAPH}/{ig}/media",
                            data={"media_type": "REELS", "upload_type": "resumable",
                                  "caption": caption(ep), "share_to_feed": "true",
                                  "access_token": token}, timeout=60), "Instagram container")
    data = Path(video).read_bytes()
    check(requests.post(c["uri"], data=data, timeout=1800,
                        headers={"Authorization": f"OAuth {token}", "offset": "0",
                                 "file_size": str(len(data))}), "Instagram upload")
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
    for name, fn in (("Facebook", post_facebook), ("Instagram", post_instagram)):
        if os.environ.get("POST_ONLY") and os.environ["POST_ONLY"] != name:
            continue
        try:
            fn(video, ep, page, token)
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

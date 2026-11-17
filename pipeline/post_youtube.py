#!/usr/bin/env python3
"""
Uploads a finished short video to YouTube (as a Short) with the official YouTube Data API.
Needs three GitHub Secrets (get them once with pipeline/youtube_auth.py):
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN

Usage (manual test, uploads as PRIVATE):
  POST_TEST=1 python pipeline/post_youtube.py output/<slug>_free/final.mp4 series/daily/<slug>.json
"""
import json, os, sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from make_episode import HANDLE, env, load_dotenv  # noqa: E402

TEST = os.environ.get("POST_TEST") == "1"  # private upload, for checking the setup


def configured():
    return all(os.environ.get(k, "").strip() for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"))


def access_token():
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": os.environ["YT_CLIENT_ID"].strip(), "client_secret": os.environ["YT_CLIENT_SECRET"].strip(),
        "refresh_token": os.environ["YT_REFRESH_TOKEN"].strip(), "grant_type": "refresh_token"}, timeout=60)
    if not r.ok:
        raise RuntimeError(f"YouTube login failed ({r.status_code}): {r.text[:300]}")
    return r.json()["access_token"]


def post_youtube(video, ep, *_):
    tags = [t.lstrip("#") for t in (ep.get("hashtags") or [])][:15]
    desc = (f"{ep.get('description', '').strip()}\n\n👉 Follow {HANDLE} for new stories every day!\n\n"
            + " ".join(["#Shorts"] + (ep.get("hashtags") or [])))[:4900]
    body = {
        "snippet": {"title": ep["yt_title"][:100], "description": desc, "tags": tags, "categoryId": "24"},
        "status": {"privacyStatus": "private" if TEST else "public", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": True},  # AI-made pictures and voice: label it honestly
    }
    token = access_token()
    data = Path(video).read_bytes()
    init = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8",
                 "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(len(data))},
        data=json.dumps(body), timeout=120)
    if not init.ok:
        raise RuntimeError(f"YouTube upload start failed ({init.status_code}): {init.text[:400]}")
    up = requests.put(init.headers["Location"], data=data, headers={"Content-Type": "video/mp4"}, timeout=1800)
    if not up.ok:
        raise RuntimeError(f"YouTube upload failed ({up.status_code}): {up.text[:400]}")
    print(f"YouTube: {'uploaded as private test' if TEST else 'posted'} video {up.json().get('id')}")


if __name__ == "__main__":
    load_dotenv()
    for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN"):
        env(k)
    try:
        post_youtube(Path(sys.argv[1]), json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    except (RuntimeError, requests.RequestException) as e:
        sys.exit(str(e))

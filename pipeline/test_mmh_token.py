#!/usr/bin/env python3
"""Diagnostic for the Money Mind Health Facebook token. Prints what Facebook says about it (never the token)."""
import os, sys

import requests

page = os.environ.get("MM_FB_PAGE_ID", "").strip()
token = os.environ.get("MM_FB_PAGE_TOKEN", "").strip()
print("page id set:", bool(page), "| token set:", bool(token), "| token length:", len(token),
      "| has spaces/quotes:", any(c in token for c in ' "\'\n\r'))
if not (page and token):
    sys.exit("secrets missing")

d = requests.get("https://graph.facebook.com/debug_token",
                 params={"input_token": token, "access_token": token}, timeout=60)
print("debug_token:", d.status_code)
try:
    j = d.json().get("data", {})
    for k in ("type", "app_id", "is_valid", "expires_at", "data_access_expires_at", "profile_id", "scopes",
              "granular_scopes"):
        print(f"  {k}: {j.get(k)}")
    if j.get("error"):
        print("  error:", j["error"])
except ValueError:
    print(d.text[:300])

for v in ("v24.0", "v26.0"):
    r = requests.get(f"https://graph.facebook.com/{v}/{page}", params={"fields": "id,name,can_post", "access_token": token},
                     timeout=60)
    print(f"GET page {v}: {r.status_code} {r.text[:200]}")
    r = requests.post(f"https://graph.facebook.com/{v}/{page}/video_reels",
                      data={"upload_phase": "start", "access_token": token}, timeout=60)
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    shown = {k: ("(hidden)" if k in ("upload_url",) else v) for k, v in body.items()}
    print(f"POST video_reels start {v}: {r.status_code} {shown}")

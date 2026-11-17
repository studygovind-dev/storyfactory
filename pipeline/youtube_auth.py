#!/usr/bin/env python3
"""
One-time helper (run on your own PC): signs in to YouTube and prints the refresh token.

  python pipeline/youtube_auth.py <CLIENT_ID> <CLIENT_SECRET>

A browser window opens; choose the Google account that owns the YouTube channel and allow access.
Then copy the printed refresh token into the GitHub Secret YT_REFRESH_TOKEN.
Nothing is saved by this script.
"""
import http.server, sys, threading, urllib.parse, webbrowser

import requests

PORT = 8765
REDIRECT = f"http://localhost:{PORT}"
SCOPE = "https://www.googleapis.com/auth/youtube.upload"


def main():
    if len(sys.argv) == 2 and sys.argv[1].lower().endswith(".json"):  # the file from "Download JSON"
        import json
        info = json.load(open(sys.argv[1], encoding="utf-8"))
        info = info.get("installed") or info.get("web") or info
        cid, secret = info["client_id"].strip(), info["client_secret"].strip()
    elif len(sys.argv) == 3:
        cid, secret = sys.argv[1].strip(), sys.argv[2].strip()
    elif len(sys.argv) <= 2:  # no secret given: ask for it (typing is hidden)
        import getpass
        cid = sys.argv[1].strip() if len(sys.argv) == 2 else input("Client ID: ").strip()
        secret = getpass.getpass("Paste the client secret here (nothing shows while you paste), then press Enter: ").strip()
    else:
        sys.exit(__doc__)
    if secret.upper().startswith("PASTE") or len(secret) < 20:
        sys.exit("That is not a real client secret. Add a new secret in Google Cloud and paste it when asked.")
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            got["code"] = (q.get("code") or [""])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"Done. You can close this tab and go back to the terminal.")
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *a):
            pass

    url = ("https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent"}))
    print("Opening the browser. If it does not open, paste this link into Chrome:\n", url)
    webbrowser.open(url)
    http.server.HTTPServer(("localhost", PORT), H).serve_forever()
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "code": got.get("code"), "client_id": cid, "client_secret": secret,
        "redirect_uri": REDIRECT, "grant_type": "authorization_code"}, timeout=60)
    if not r.ok or "refresh_token" not in r.json():
        sys.exit(f"Failed: {r.text[:400]}")
    print("\nYT_REFRESH_TOKEN =", r.json()["refresh_token"])


if __name__ == "__main__":
    main()

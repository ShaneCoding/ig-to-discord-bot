# check_ig.py
import os, json, time
import base64
import pathlib
import instaloader
import requests

# Config via env
IG_MAP = os.environ.get("IG_MAP", "").strip()
SESSIONFILE = os.environ.get("IG_SESSIONFILE", "session-bloxtech8").strip()
IG_LOGIN_USER = os.environ.get("IG_LOGIN_USER", "").strip()

LAST_FILE = "last_seen.json"

def parse_map(text):
    # accepts ';;;' separated single-line or multi-line input
    if ";;;" in text:
        parts = [p.strip() for p in text.split(";;;") if p.strip()]
    else:
        parts = [p.strip() for p in text.splitlines() if p.strip()]
    entries = []
    for line in parts:
        if not line or line.startswith("#"):
            continue
        fields = [f.strip() for f in line.split("|")]
        if len(fields) < 2:
            print("Skipping malformed IG_MAP line:", line)
            continue
        username = fields[0]
        webhook = fields[1]
        extra = fields[2] if len(fields) >= 3 else ""
        entries.append((username, webhook, extra))
    return entries

# Load last seen dict
if os.path.exists(LAST_FILE):
    with open(LAST_FILE, "r", encoding="utf-8") as f:
        last_seen = json.load(f)
else:
    last_seen = {}

# Parse targets
entries = parse_map(IG_MAP)
if not entries:
    print("No entries found in IG_MAP. Exiting.")
    raise SystemExit(1)

# Initialize Instaloader and load session
L = instaloader.Instaloader(dirname_pattern=None, download_pictures=False, download_videos=False, download_comments=False)
if IG_LOGIN_USER and os.path.exists(SESSIONFILE):
    try:
        L.load_session_from_file(IG_LOGIN_USER, SESSIONFILE)
        print(f"Loaded session file {SESSIONFILE} for {IG_LOGIN_USER}")
    except Exception as e:
        print("Failed to load session file:", e)
else:
    print("Warning: no session file found or IG_LOGIN_USER not set — may be rate-limited or blocked.")

# For each account, check latest post and post to webhook if new
for username, webhook, extra in entries:
    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except Exception as e:
        print(f"[{username}] ERROR fetching profile: {e}")
        continue

    try:
        posts = profile.get_posts()
        latest = None
        for p in posts:
            latest = p
            break
        if latest is None:
            print(f"[{username}] no posts found.")
            continue

        shortcode = latest.shortcode  # unique ID for the post
        if last_seen.get(username) == shortcode:
            print(f"[{username}] no new posts (latest {shortcode})")
            continue

        caption = latest.caption or ""
        post_url = f"https://www.instagram.com/p/{shortcode}/"
        content = f"New post from @{username}:\n{caption}\n{post_url}"

        # Send to Discord webhook
        payload = {"content": content}
        r = requests.post(webhook, json=payload, timeout=15)
        if r.status_code in (200, 204):
            print(f"[{username}] Posted to Discord: {post_url}")
            last_seen[username] = shortcode
            # Small delay to be polite
            time.sleep(1)
        else:
            print(f"[{username}] Discord webhook returned {r.status_code}: {r.text}")

    except Exception as e:
        print(f"[{username}] ERROR during check/post: {e}")

# Save updated last_seen
with open(LAST_FILE, "w", encoding="utf-8") as f:
    json.dump(last_seen, f, indent=2)
print("Done.")

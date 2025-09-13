# check_ig.py
import os
import json
import time
import traceback
import instaloader
import requests

# Optional: load local .env file (ignored on GitHub)
if os.path.exists(".env"):
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print("[debug] Loaded local .env file")
    except ImportError:
        print("[debug] python-dotenv not installed; skipping .env")


print("== Starting Instagram -> Discord check ==")

# Config via env
IG_MAP = os.environ.get("IG_MAP", "").strip()
SESSIONFILE = os.environ.get("IG_SESSIONFILE", "session-bloxtech8").strip()
IG_LOGIN_USER = os.environ.get("IG_LOGIN_USER", "bloxtech8").strip()

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
print("Parsed", len(entries), "entries from IG_MAP")
if not entries:
    print("No entries found in IG_MAP. Exiting.")
    raise SystemExit(1)

# Initialize Instaloader
L = instaloader.Instaloader(
    dirname_pattern=None,
    download_pictures=False,
    download_videos=False,
    download_comments=False,
)

# Load session file (robust)
print("Looking for session file:", SESSIONFILE)
if IG_LOGIN_USER and os.path.exists(SESSIONFILE):
    try:
        L.load_session_from_file(IG_LOGIN_USER, SESSIONFILE)
        print(f"[OK] Loaded session file {SESSIONFILE} for {IG_LOGIN_USER}")
        # quick sanity check: fetch own profile
        try:
            me = instaloader.Profile.from_username(L.context, IG_LOGIN_USER)
            print(f"[OK] Session test: fetched own profile {me.username}")
        except Exception as e:
            print("[WARN] Session test: could not fetch own profile; result:", repr(e))
    except Exception as e:
        print("[ERR] Failed to load session file:", repr(e))
        traceback.print_exc()
        print("Exiting due to session load failure.")
        raise SystemExit(1)
else:
    print("[WARN] IG_LOGIN_USER not set or session file missing. Exiting.")
    raise SystemExit(1)

# Function to post to discord
def post_to_discord(webhook_url, content):
    try:
        r = requests.post(webhook_url, json={"content": content}, timeout=15)
        if r.status_code in (200, 204):
            return True, None
        else:
            return False, f"{r.status_code} {r.text}"
    except Exception as e:
        return False, repr(e)

# Main loop: check each account once
for username, webhook, extra in entries:
    print(f"[MAIN] Checking {username} ...")
    # polite per-account delay (avoid rapid-fire)
    time.sleep(4)

    try:
        profile = instaloader.Profile.from_username(L.context, username)
    except Exception as e:
        print(f"[{username}] ERROR fetching profile: {repr(e)}")
        traceback.print_exc()
        continue

    try:
        posts = profile.get_posts()
        latest = next(posts, None)
        if latest is None:
            print(f"[{username}] no posts found.")
            continue

        shortcode = latest.shortcode
        if last_seen.get(username) == shortcode:
            print(f"[{username}] no new posts (latest {shortcode})")
            continue

        caption = latest.caption or ""
        # Trim the caption to avoid giant messages; keep first 1000 chars
        if len(caption) > 1000:
            caption = caption[:1000] + "…"

        post_url = f"https://www.instagram.com/p/{shortcode}/"
        content = f"New post from @{username}:\n{caption}\n{post_url}"

        ok, err = post_to_discord(webhook, content)
        if ok:
            print(f"[{username}] Posted to Discord: {post_url}")
            last_seen[username] = shortcode
        else:
            print(f"[{username}] Failed to post to Discord: {err}")

    except Exception as e:
        print(f"[{username}] ERROR during check/post: {repr(e)}")
        traceback.print_exc()

# Save updated last_seen
with open(LAST_FILE, "w", encoding="utf-8") as f:
    json.dump(last_seen, f, indent=2)

print("== Done ==")

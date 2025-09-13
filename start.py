# start.py
import os
import subprocess
import time
import base64
from threading import Thread
from flask import Flask

# --- Config: names
SESSION_ENV_B64 = "IG_SESSION_B64"   # Railway secret containing base64(session file)
SESSION_FILENAME_ENV = "IG_SESSIONFILE"  # name to write session file as
IG_MAP_ENV = "IG_MAP"  # single-line mapping secret (username | webhook | optional_args) separated by ';;;'

# --- Write session file from base64 env if present
session_b64 = os.environ.get(SESSION_ENV_B64, "").strip()
session_filename = os.environ.get(SESSION_FILENAME_ENV, "session-bloxtech8").strip()

if session_b64:
    try:
        raw = base64.b64decode(session_b64)
        with open(session_filename, "wb") as f:
            f.write(raw)
        print(f"[INIT] Wrote session file to {session_filename} from {SESSION_ENV_B64}")
    except Exception as e:
        print(f"[ERROR] Failed to decode/write session file: {e}")

# --- Parse IG_MAP (single-line with ';;;' separators or multiline)
MAP_TEXT = os.environ.get(IG_MAP_ENV, "")
if not MAP_TEXT or not MAP_TEXT.strip():
    print("ERROR: IG_MAP not set. Set the IG_MAP env var (see docs).")
    raise SystemExit(1)

def get_raw_entries(text):
    if ";;;" in text:
        parts = [p.strip() for p in text.split(";;;") if p.strip()]
    else:
        parts = [p.strip() for p in text.splitlines() if p.strip()]
    return parts

def parse_map_entries(raw_entries):
    entries = []
    for line in raw_entries:
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            print("Skipping malformed line:", line)
            continue
        username = parts[0]
        webhook = parts[1]
        extra = parts[2] if len(parts) >= 3 else ""
        entries.append((username, webhook, extra))
    return entries

raw_entries = get_raw_entries(MAP_TEXT)
entries = parse_map_entries(raw_entries)
if not entries:
    print("ERROR: No valid entries in IG_MAP. Exiting.")
    raise SystemExit(1)

# --- start instawebhooks processes
processes = {}

def build_cmd(username, webhook, extra_args):
    cmd = ["instawebhooks", username, webhook]
    if extra_args:
        cmd += extra_args.split()
    # If a session file exists on disk, add it automatically
    if os.path.exists(session_filename):
        cmd += ["--sessionfile", session_filename]
    return cmd

def start_account(username, webhook, extra_args):
    cmd = build_cmd(username, webhook, extra_args)
    print(f"[BOOT] Starting {username} -> {webhook}  args: {extra_args}")
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    except FileNotFoundError as e:
        print("[ERROR] instawebhooks binary not found. Did pip install succeed? Exception:", e)
        raise
    processes[username] = (p, webhook, extra_args)

def monitor_processes():
    while True:
        for username, (p, webhook, extra_args) in list(processes.items()):
            if p.poll() is not None:
                print(f"[MONITOR] {username} exited (code {p.returncode}). Restarting...")
                start_account(username, webhook, extra_args)
        time.sleep(20)

# Start them
for username, webhook, extra in entries:
    start_account(username, webhook, extra)

# Monitor thread
t = Thread(target=monitor_processes, daemon=True)
t.start()

# Tiny webserver for keepalive
app = Flask("keepalive")
@app.route("/")
def home():
    return "OK", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()

# Main loop: print child outputs
try:
    while True:
        for username, (p, webhook, extra) in list(processes.items()):
            try:
                if p and p.stdout:
                    line = p.stdout.readline()
                    if line:
                        print(f"[{username}] {line.rstrip()}")
            except Exception as e:
                print(f"[ERROR] reading stdout for {username}: {e}")
        time.sleep(0.5)
except KeyboardInterrupt:
    print("Shutting down...")
    for username, (p, _, _) in processes.items():
        try:
            p.terminate()
        except:
            pass

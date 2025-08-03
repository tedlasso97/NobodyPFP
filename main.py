#!/usr/bin/env python3
import os
import json
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v1, get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

# Path to our recipients file in persistent storage
RECIPIENTS_FILE = "/data/recipients.json"

def bootstrap_recipients():
    """
    On startup, seed recipients.json with everyone
    we've already replied to in our bot’s timeline,
    so they don’t get a second PFP.
    """
    seen = set()
    if os.path.exists(RECIPIENTS_FILE):
        with open(RECIPIENTS_FILE, "r") as f:
            seen = set(json.load(f))

    client = get_twitter_conn_v1()
    # Pull up to 200 of our own most recent tweets
    for status in client.user_timeline(count=200, tweet_mode="extended"):
        if status.in_reply_to_screen_name:
            seen.add(status.in_reply_to_screen_name.lower())

    with open(RECIPIENTS_FILE, "w") as f:
        json.dump(list(seen), f)

# Create clients once for the process
client_v1 = get_twitter_conn_v1()  # v1.1 for media upload
client_v2 = get_twitter_conn_v2()  # v2 for fetching & posting tweets

def job():
    now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now_local.strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Running fetch job…")
    respond_to_mentions(client_v2, client_v1)

def serve_job():
    now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now_local.strftime('%Y-%m-%d %H:%M:%S')}] 🤖 Running serve job…")
    serve_from_queue(client_v1, client_v2)

if __name__ == '__main__':
    # Seed recipients before polling so we never double-serve
    bootstrap_recipients()

    scheduler = BlockingScheduler()
    # Poll for new mentions every 5 minutes
    scheduler.add_job(job, 'interval', minutes=5)
    # Send one reply every 5 minutes (avoids rate limits)
    scheduler.add_job(serve_job, 'interval', minutes=5)

    print("✅ Nobody bot is running… fetching every 5 minutes, replying every 5 minutes.")
    scheduler.start()

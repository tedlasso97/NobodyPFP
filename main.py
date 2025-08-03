#!/usr/bin/env python3
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v1, get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

# v1 client for media upload; v2 client for fetching & posting tweets
client_v1 = get_twitter_conn_v1()
client_v2 = get_twitter_conn_v2()

def job():
    try:
        now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
        print(f"[{now_local.strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Running fetch job…")
        respond_to_mentions(client_v2, client_v1)
    except Exception as e:
        print(f"❌ Unhandled error in fetch job: {e}")

def serve_job():
    try:
        now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
        print(f"[{now_local.strftime('%Y-%m-%d %H:%M:%S')}] 🤖 Running serve job…")
        serve_from_queue(client_v1, client_v2)
    except Exception as e:
        print(f"❌ Unhandled error in serve job: {e}")

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    # Fetch new mentions every 2 minutes
    scheduler.add_job(job, 'interval', minutes=2)
    # Serve queued replies every 45 seconds
    scheduler.add_job(serve_job, 'interval', seconds=45)

    print("✅ Nobody bot is running… fetching every 2 m, replying every 45 s.")
    scheduler.start()

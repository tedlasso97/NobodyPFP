#!/usr/bin/env python3
import time
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.blocking import BlockingScheduler
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v1, get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

# v1 = media upload; v2 = search & tweet post
client_v1 = get_twitter_conn_v1()
client_v2 = get_twitter_conn_v2()

def fetch_job():
    now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now_local:%Y-%m-%d %H:%M:%S}] 🔍 Running fetch job…")
    respond_to_mentions(client_v2, client_v1)

def serve_job():
    now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now_local:%Y-%m-%d %H:%M:%S}] 🤖 Running serve job…")
    serve_from_queue(client_v1, client_v2)

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    scheduler.add_job(fetch_job, 'interval', minutes=2)
    scheduler.add_job(serve_job, 'interval', seconds=60)
    print("✅ Nobody bot is running… fetch every 2m, serve every 60s.")
    scheduler.start()

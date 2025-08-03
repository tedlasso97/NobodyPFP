#!/usr/bin/env python3
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

client = get_twitter_conn_v2()  # single v2 client

def fetch_job():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🔍 Fetching mentions…")
    respond_to_mentions(client)

def serve_job():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🤖 Serving replies…")
    serve_from_queue(client)

if __name__ == "__main__":
    sched = BlockingScheduler()
    sched.add_job(fetch_job, "interval", minutes=2)    # fetch every 2m
    sched.add_job(serve_job, "interval", minutes=5)    # reply every 5m
    print("✅ Bot running: fetch every 2 m, reply every 5 m.")
    sched.start()

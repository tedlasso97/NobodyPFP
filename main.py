#!/usr/bin/env python3
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v1, get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

client_v1 = get_twitter_conn_v1()
client_v2 = get_twitter_conn_v2()

def job():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🔍 Fetching mentions…")
    respond_to_mentions(client_v2, client_v1)

def serve_job():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🤖 Serving replies…")
    serve_from_queue(client_v1)

if __name__ == "__main__":
    sched = BlockingScheduler()
    sched.add_job(job,       'interval', minutes=2)  # fetch new mentions
    sched.add_job(serve_job, 'interval', minutes=5)  # post replies much slower

    print("✅ Bot running: fetch every 2 m, serve every 5 m.")
    sched.start()

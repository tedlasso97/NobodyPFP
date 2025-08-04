#!/usr/bin/env python3
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone

from auth import get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

client_v2 = get_twitter_conn_v2()

def job_fetch():
    now = datetime.now(timezone.utc).astimezone()
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🔍 Fetching & enqueuing…")
    respond_to_mentions(client_v2)

def job_serve():
    now = datetime.now(timezone.utc).astimezone()
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🤖 Drip-serving replies…")
    serve_from_queue(client_v2)

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    # pull new mentions every 2m, drip replies every 1m (or adjust)
    scheduler.add_job(job_fetch, 'interval', minutes=2)
    scheduler.add_job(job_serve, 'interval', minutes=1)
    print("✅ Nobody bot started — fetch every 2m, reply drip every 1m.")
    scheduler.start()

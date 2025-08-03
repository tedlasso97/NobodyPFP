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
    now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now_local:%Y-%m-%d %H:%M:%S}] 🔍 Running fetch job…")
    respond_to_mentions(client_v2, client_v1)

def serve_job():
    now_local = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now_local:%Y-%m-%d %H:%M:%S}] 🤖 Running serve job…")
    serve_from_queue(client_v1)

if __name__ == '__main__':
    sched = BlockingScheduler()
    # fetch every 2 minutes, no overlap
    sched.add_job(job,        'interval', minutes=2,  max_instances=1)
    # reply every 75 seconds, no overlap
    sched.add_job(serve_job,  'interval', seconds=75, max_instances=1)

    print("✅ Nobody bot is running… fetching every 2 m, replying every 75 s.")
    sched.start()

#!/usr/bin/env python3
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v1, get_twitter_conn_v2
from utils import process_one_mention

client_v1 = get_twitter_conn_v1()  # v1.1 for media + status
client_v2 = get_twitter_conn_v2()  # v2 for fetching

def job():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🔍 Checking one mention…")
    process_one_mention(client_v2, client_v1)

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    # run *once per minute* => ~60 tweets/hour < 300/3h limit
    scheduler.add_job(job, "interval", minutes=1)
    print("✅ Nobody bot running — 1 reply per minute.")
    scheduler.start()

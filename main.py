#!/usr/bin/env python3
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v2
from utils import run_once

def job():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🔍 fetch & reply …")
    try:
        client_v2 = get_twitter_conn_v2()
        run_once(client_v2)
    except Exception as e:
        print("❌ unexpected error:", e)

if __name__ == "__main__":
    scheduler = BlockingScheduler()
    scheduler.add_job(job, "interval", minutes=5)
    print("✅ bot started — running every 5 minutes")
    job()             # immediate first pass
    scheduler.start()

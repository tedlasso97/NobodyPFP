#!/usr/bin/env python3
# main.py

import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v1, get_twitter_conn_v2
import utils

client_v1 = get_twitter_conn_v1()
client_v2 = get_twitter_conn_v2()

def run_enqueue():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🔍 batch_enqueue")
    utils.batch_enqueue(client_v2)

def run_drip():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🤖 drip_reply")
    utils.drip_reply(client_v1)

if __name__ == "__main__":
    sched = BlockingScheduler()
    # every 10m, gather new mentions into our queue
    sched.add_job(run_enqueue, 'interval', minutes=10, next_run_time=datetime.now())
    # every 5m, post exactly one reply
    sched.add_job(run_drip,    'interval', minutes=5,  next_run_time=datetime.now())
    print("✅ Nobody bot started — batch every 10m, drip every 5m.")
    sched.start()

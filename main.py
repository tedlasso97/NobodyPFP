#!/usr/bin/env python3
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from auth import get_twitter_conn_v1, get_twitter_conn_v2
import utils

client_v1 = get_twitter_conn_v1()  # v1 for media & update_status
client_v2 = get_twitter_conn_v2()  # v2 for search & user lookup

def run_enqueue():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🤖 batch_enqueue")
    utils.batch_enqueue(client_v2)

def run_drip():
    now = datetime.now(timezone.utc).astimezone(ZoneInfo("America/Edmonton"))
    print(f"[{now:%Y-%m-%d %H:%M:%S}] 🤖 drip_reply")
    utils.drip_reply(client_v1)

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(run_enqueue, 'interval', minutes=10)
    scheduler.add_job(run_drip,     'interval', minutes=5)
    print("✅ Nobody bot started — batch every 10 m, drip every 5 m.")
    scheduler.start()

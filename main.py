#!/usr/bin/env python3
import os
import time
from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timedelta, timezone

from auth import get_twitter_conn_v1, get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

# v1 client for media upload; v2 client for fetching & posting tweets
client_v1 = get_twitter_conn_v1()
client_v2 = get_twitter_conn_v2()

def job():
    now_utc = datetime.now(timezone.utc)
    now_est = now_utc - timedelta(hours=4)
    print(f"[{now_est.strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Running fetch job...")
    # note: pass both v2 (fetching) and v1 (if utils needs it)
    respond_to_mentions(client_v2, client_v1)

def serve_job():
    now_utc = datetime.now(timezone.utc)
    now_est = now_utc - timedelta(hours=4)
    print(f"[{now_est.strftime('%Y-%m-%d %H:%M:%S')}] 🤖 Running serve job...")
    # now serving via v1 (media) and v2 (tweet post)
    serve_from_queue(client_v1, client_v2)

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(job, 'interval', minutes=2)        # fetch new mentions
    scheduler.add_job(serve_job, 'interval', seconds=45) # serve replies
    print("✅ Nobody bot is running... polling every 2 minutes, replying every 45 seconds.")
    scheduler.start()

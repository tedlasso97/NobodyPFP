import os
from datetime import datetime, timedelta
from apscheduler.schedulers.blocking import BlockingScheduler

from auth import get_twitter_conn_v1, get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

# Initialize Twitter API clients
client_v1 = get_twitter_conn_v1()  # Used for posting replies (v1.1 required for media upload)
client_v2 = get_twitter_conn_v2()  # Used for fetching mentions

# Fetch job: look for new mentions every 2 minutes
def job():
    now_utc = datetime.utcnow()
    now_est = now_utc - timedelta(hours=4)  # Adjust for EST if needed
    print(f"[{now_est.strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Running fetch job...")
    respond_to_mentions(client_v2)

# Serve job: post replies from queue every 45 seconds
def serve_job():
    now_utc = datetime.utcnow()
    now_est = now_utc - timedelta(hours=4)
    print(f"[{now_est.strftime('%Y-%m-%d %H:%M:%S')}] 🤖 Running serve job...")
    serve_from_queue(client_v1)

if __name__ == '__main__':
    print("✅ Nobody bot is running... polling every 2 minutes, replying every 45 seconds.")
    scheduler = BlockingScheduler()
    scheduler.add_job(job, 'interval', minutes=2)
    scheduler.add_job(serve_job, 'interval', seconds=45)
    scheduler.start()

print("🚀 Starting main.py...")

from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timezone, timedelta

from auth import get_twitter_conn_v2
from utils import respond_to_mentions, serve_from_queue

client_v2 = get_twitter_conn_v2()

def job():
    now_utc = datetime.now(timezone.utc)
    now_est = now_utc - timedelta(hours=4)
    print(f"[{now_est.strftime('%Y-%m-%d %H:%M:%S')}] Running fetch job...")
    respond_to_mentions(client_v2)

def serve_job():
    now_utc = datetime.now(timezone.utc)
    now_est = now_utc - timedelta(hours=4)
    print(f"[{now_est.strftime('%Y-%m-%d %H:%M:%S')}] Running serve job...")
    serve_from_queue(client_v2)

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(job, 'interval', minutes=2)       # Fetch new mentions
    scheduler.add_job(serve_job, 'interval', seconds=45)  # Serve replies every 45s
    print("✅ Nobody bot is running... polling every 2 minutes, replying every 45 seconds.")
    scheduler.start()

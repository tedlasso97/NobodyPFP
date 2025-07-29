print("🚀 Starting main.py...")

from apscheduler.schedulers.blocking import BlockingScheduler
from datetime import datetime, timedelta

from auth import get_twitter_conn_v2
from utils import respond_to_mentions

client_v2 = get_twitter_conn_v2()

def job():
    now_utc = datetime.utcnow()
    now_est = now_utc - timedelta(hours=4)
    print(f"[{now_est.strftime('%Y-%m-%d %H:%M:%S')}] Running bot job...")
    respond_to_mentions(client_v2)

if __name__ == '__main__':
    scheduler = BlockingScheduler()
    scheduler.add_job(job, 'interval', minutes=2)
    print("✅ Nobody bot is running... polling every 2 minutes.")
    scheduler.start()

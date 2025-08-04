import os, json, random, time, requests
from auth import get_twitter_conn_v1

# ─── CONFIG ────────────────────────────────────────────────────────────────
USED_IMAGES_FILE = "/data/used_images.json"
RECIPIENTS_FILE  = "/data/recipients.json"
STATE_FILE       = "/data/state.json"
IMAGES_DIR       = "images"    # your local folder of 0–9999.png
B2_BASE_URL      = "https://f004.backblazeb2.com/file/NobodyPFPs/"
TEMP_FILE        = "temp.png"

REPLY_TEMPLATES = [
    "Here's your Nobody PFP 👁️ @{screen_name}",
    "Your custom Nobody PFP is ready 👁️ @{screen_name}",
    "All yours 👁️ @{screen_name}",
    "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
    "Cooked just for you 👁️ @{screen_name}",
    "Made with nothingness 👁️ @{screen_name}",
    "👁️ For the void... and @{screen_name}",
]

# ─── HELPERS ────────────────────────────────────────────────────────────────
def _load(path, default):
    if os.path.exists(path):
        with open(path) as f: return json.load(f)
    return default

def _save(obj, path):
    with open(path, "w") as f: json.dump(obj, f)

def load_state():
    return _load(STATE_FILE, {"last_seen_id": None})

def save_state(s):
    _save(s, STATE_FILE)

def load_set(path):
    return set(_load(path, []))

def save_set(s, path):
    _save(list(s), path)

# ─── IMAGE ──────────────────────────────────────────────────────────────────
def pick_image(used):
    all_imgs = os.listdir(IMAGES_DIR)
    avail    = list(set(all_imgs) - used)
    return random.choice(avail) if avail else None

def download_img(fn):
    url = f"{B2_BASE_URL}{fn}"
    r   = requests.get(url); r.raise_for_status()
    with open(TEMP_FILE, "wb") as f: f.write(r.content)
    return TEMP_FILE

# ─── MAIN LOOP ──────────────────────────────────────────────────────────────
def run_once(client_v2):
    # prep
    v1         = get_twitter_conn_v1()
    state      = load_state()
    last_seen  = state.get("last_seen_id")
    used_imgs  = load_set(USED_IMAGES_FILE)
    recipients = load_set(RECIPIENTS_FILE)
    new_last   = last_seen

    # fetch up to 50 new mentions (avoid RTs)
    resp = client_v2.search_recent_tweets(
        query="@nobodypfp create a PFP for me -is:retweet",
        since_id=last_seen,
        max_results=50,
        tweet_fields=["author_id"]
    )
    tweets = resp.data or []

    for tw in reversed(tweets):
        tid = tw.id
        if not new_last or tid > new_last:
            new_last = tid

        # filter exact trigger
        if "create a pfp for me" not in tw.text.lower():
            continue

        user = client_v2.get_user(id=tw.author_id).data.username.lower()
        if user in recipients:
            continue

        # pick & download
        img = pick_image(used_imgs)
        if not img:
            print("⚠️ Out of images.")
            break
        path = download_img(img)

        # upload & reply
        try:
            m   = v1.media_upload(path)
            txt = random.choice(REPLY_TEMPLATES).format(screen_name=user)
            v1.update_status(
                status=txt,
                in_reply_to_status_id=tid,
                auto_populate_reply_metadata=True,
                media_ids=[m.media_id_string]
            )
            print(f"🎉 Replied to @{user}")
        except Exception as e:
            print(f"❌ Reply to @{user} failed:", e)
            break

        # record
        used_imgs.add(img)
        recipients.add(user)
        save_set(used_imgs, USED_IMAGES_FILE)
        save_set(recipients, RECIPIENTS_FILE)

        time.sleep(2)

    # persist cursor
    if new_last and new_last != last_seen:
        save_state({"last_seen_id": new_last})

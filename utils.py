import os
import json
import random
import requests
import tweepy

# ─── CONFIG ───────────────────────────────────────────────────
USED_IMAGES_FILE    = "/data/used_images.json"
RECIPIENTS_FILE     = "/data/recipients.json"
STATE_FILE          = "/data/state.json"
IMAGES_DIR          = "images"   # or wherever your local images live
TEMP_IMAGE_FILE     = "temp.png"
B2_IMAGE_BASE_URL   = "https://f004.backblazeb2.com/file/NobodyPFPs/"

# ─── HELPERS ──────────────────────────────────────────────────
def load_set(path):
    if os.path.exists(path):
        return set(json.load(open(path)))
    return set()

def save_set(s, path):
    with open(path, "w") as f:
        json.dump(list(s), f)

def load_state():
    if os.path.exists(STATE_FILE):
        return json.load(open(STATE_FILE))
    return {"last_id": None}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

# ─── IMAGE PICKER ──────────────────────────────────────────────
def get_unused_image(used):
    all_imgs = [f"{i}.png" for i in range(10000)]
    avail    = list(set(all_imgs) - used)
    return random.choice(avail) if avail else None

def download(img_name):
    url = B2_IMAGE_BASE_URL + img_name
    r = requests.get(url); r.raise_for_status()
    with open(TEMP_IMAGE_FILE, "wb") as f:
        f.write(r.content)
    return TEMP_IMAGE_FILE

# ─── PROCESS ONE MENTION ──────────────────────────────────────
def process_one_mention(client_v2, client_v1):
    used       = load_set(USED_IMAGES_FILE)
    replied    = load_set(RECIPIENTS_FILE)
    state      = load_state()
    last_id    = state.get("last_id")

    # 1) fetch up to 10 new mentions
    try:
        resp = client_v2.search_recent_tweets(
            query="@nobodypfp create a PFP for me -is:retweet",
            since_id=last_id,
            max_results=10,
            tweet_fields=["author_id"]
        )
        tweets = resp.data or []
    except Exception as e:
        print("Search error:", e)
        return

    # 2) walk oldest→newest, find first un-replied user
    for tw in reversed(tweets):
        tid  = tw.id
        txt  = tw.text.lower()
        if "create a pfp for me" not in txt:
            continue

        # bump last_id so we don’t refetch
        if tid > (last_id or 0):
            last_id = tid

        # lookup screen_name
        try:
            user = client_v2.get_user(id=tw.author_id).data.username.lower()
        except Exception as e:
            print("User lookup error:", e)
            continue

        if user in replied:
            continue

        # pick an image
        img_name = get_unused_image(used)
        if not img_name:
            print("⚠️ No images left.")
            state["last_id"] = last_id
            save_state(state)
            return

        # download & upload
        try:
            path  = download(img_name)
            media = client_v1.media_upload(path)
        except Exception as e:
            print("Media error:", e)
            state["last_id"] = last_id
            save_state(state)
            return

        # random reply text
        template = random.choice([
            "Here's your Nobody PFP 👁️ @{screen_name}",
            "Your custom Nobody PFP is ready 👁️ @{screen_name}",
            "All yours 👁️ @{screen_name}",
            "You asked. We delivered. Nobody PFP 👁️ @{screen_name}",
            "Cooked just for you 👁️ @{screen_name}",
            "Made with nothingness 👁️ @{screen_name}",
            "👁️ For the void... and @{screen_name}",
        ])
        status = template.format(screen_name=user)

        # post reply
        try:
            client_v1.update_status(
                status=status,
                in_reply_to_status_id=tid,
                auto_populate_reply_metadata=True,
                media_ids=[media.media_id_string]
            )
            print(f"✔️ Replied to @{user} (tweet {tid})")
        except tweepy.TooManyRequests as e:
            # hit rate-limit: bail out now
            reset = int(e.response.headers.get("x-rate-limit-reset", 0))
            print("🚫 Rate limit. reset at", reset)
            # we do NOT re-try in this run
            state["last_id"] = last_id
            save_state(state)
            return
        except Exception as e:
            print("Reply error:", e)
            state["last_id"] = last_id
            save_state(state)
            return

        # record success
        used.add(img_name)
        replied.add(user)
        save_set(used, USED_IMAGES_FILE)
        save_set(replied, RECIPIENTS_FILE)
        state["last_id"] = last_id
        save_state(state)
        return  # **only one** per run

    # if we fell out without doing anything, just bump state
    state["last_id"] = last_id
    save_state(state)

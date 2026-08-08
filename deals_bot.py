"""
Women's Garments Deals Bot (EK Affiliaters -> Telegram)
========================================================
You add product deals to queue.json (title, price, image, product
link, category). This script:

  1. Picks the next eligible deal from the queue (respecting active
     hours, time gap, daily limits, dedup window, price-increase skip)
  2. Converts the product link into a monetized EK Affiliaters link
     via their public converter API
  3. Formats a message with price history + emojis + bold/light text
  4. Posts it (with image) to your Telegram channel
  5. Moves the deal from queue.json to posted_log.json automatically

Environment variables needed (set as GitHub Secrets):
    EKARO_API_KEY        - your EK Affiliaters API key
    TELEGRAM_BOT_TOKEN    - this channel's bot token
    TELEGRAM_CHAT_ID      - this channel's @username or numeric ID

Settings live in settings.json. Add deals to queue.json anytime.
Don't hand-edit state.json or posted_log.json.
"""

import os
import json
import requests
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------

EKARO_API_URL = "https://ekaro-api.affiliaters.in/api/converter/public"
EKARO_API_KEY = os.environ.get("EKARO_API_KEY", "")

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

QUEUE_FILE = "queue.json"
POSTED_LOG_FILE = "posted_log.json"
SETTINGS_FILE = "settings.json"
STATE_FILE = "state.json"

IST_OFFSET = timedelta(hours=5, minutes=30)

CATEGORY_EMOJIS = {
    "fashion": "👗",
    "beauty": "💄",
    "electronics": "📱",
    "home_kitchen": "🏠",
}

# ---------------------------------------------------------------------
# FILE HELPERS
# ---------------------------------------------------------------------

def load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def default_state():
    return {
        "last_post_utc": None,
        "daily_counts": {"date": "", "counts": {}},
        "price_history": {},     # {product_url: [{"price":..,"date":..}, ...]}
        "recently_posted": {},   # {product_url: iso_timestamp}
    }


def now_utc():
    return datetime.now(timezone.utc)


def now_ist():
    return now_utc() + IST_OFFSET


def hours_since(iso_ts):
    if not iso_ts:
        return float("inf")
    return (now_utc() - datetime.fromisoformat(iso_ts)).total_seconds() / 3600


def minutes_since(iso_ts):
    if not iso_ts:
        return float("inf")
    return (now_utc() - datetime.fromisoformat(iso_ts)).total_seconds() / 60


# ---------------------------------------------------------------------
# ACTIVE HOURS + DAILY LIMITS
# ---------------------------------------------------------------------

def within_active_hours(settings):
    if not settings.get("active_hours_enabled", False):
        return True
    start = datetime.strptime(settings.get("active_hours_start", "00:00"), "%H:%M").time()
    end = datetime.strptime(settings.get("active_hours_end", "23:59"), "%H:%M").time()
    current = now_ist().time()
    if start <= end:
        return start <= current <= end
    return current >= start or current <= end


def reset_daily_counts_if_new_day(state):
    today_str = now_ist().strftime("%Y-%m-%d")
    if state["daily_counts"].get("date") != today_str:
        state["daily_counts"] = {"date": today_str, "counts": {}}


def category_under_daily_limit(category, settings, state):
    limit = settings.get("category_daily_limit", {}).get(category, 999)
    used = state["daily_counts"]["counts"].get(category, 0)
    return used < limit


def increment_daily_count(category, state):
    counts = state["daily_counts"]["counts"]
    counts[category] = counts.get(category, 0) + 1


# ---------------------------------------------------------------------
# PRICE HISTORY
# ---------------------------------------------------------------------

def get_last_known_price(key, state):
    history = state["price_history"].get(key, [])
    return history[-1]["price"] if history else None


def record_price_history(state, key, price, settings):
    if price is None:
        return
    max_points = settings.get("price_history_points", 5)
    history = state["price_history"].setdefault(key, [])
    today_str = now_ist().strftime("%Y-%m-%d")
    if history and history[-1].get("date") == today_str:
        history[-1]["price"] = price
    else:
        history.append({"price": price, "date": today_str})
    if len(history) > max_points:
        state["price_history"][key] = history[-max_points:]


def price_history_line(key, current_price, state):
    history = state["price_history"].get(key, [])
    if not history:
        return ""
    past_prices = [h["price"] for h in history]
    trend = " → ".join(f"₹{int(p):,}" for p in past_prices)
    if current_price is not None:
        trend += f" → ₹{int(current_price):,} (now)"
    lines = [f"📊 Price History: {trend}"]
    all_prices = past_prices + ([current_price] if current_price is not None else [])
    numeric = [p for p in all_prices if isinstance(p, (int, float))]
    if numeric and current_price is not None and current_price <= min(numeric):
        lines.append("🔥 *Lowest price recorded yet!*")
    return "\n".join(lines)


# ---------------------------------------------------------------------
# QUEUE SELECTION
# ---------------------------------------------------------------------

def pick_next_deal(queue_data, settings, state):
    """Returns the first eligible queued deal, or None."""
    validity_minutes = settings.get("lightning_offer_validity_minutes", 180)
    ignore_price_up = settings.get("ignore_if_price_increased", True)

    for deal in queue_data.get("queue", []):
        url = deal.get("product_url")
        if not url:
            continue

        category = deal.get("category", "fashion")
        if not category_under_daily_limit(category, settings, state):
            continue

        if minutes_since(state["recently_posted"].get(url)) < validity_minutes:
            continue

        if ignore_price_up:
            price = deal.get("price")
            prev = get_last_known_price(url, state)
            if price is not None and prev is not None:
                try:
                    if float(price) > float(prev):
                        continue
                except (TypeError, ValueError):
                    pass

        return deal

    return None


def remove_from_queue_and_log(queue_data, deal, posted_log):
    queue_data["queue"] = [
        d for d in queue_data["queue"] if d.get("product_url") != deal.get("product_url")
    ]
    posted_log.setdefault("posted", []).append({
        **deal,
        "posted_at_utc": now_utc().isoformat(),
    })


# ---------------------------------------------------------------------
# EK AFFILIATERS — LINK CONVERSION
# ---------------------------------------------------------------------

def convert_link(product_url):
    """Converts a raw product URL into a monetized EK Affiliaters link."""
    headers = {
        "Authorization": f"Bearer {EKARO_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "deal": product_url,
        "convert_option": "convert_only",
    }
    try:
        resp = requests.post(EKARO_API_URL, headers=headers, json=payload, timeout=15)
        data = resp.json()
        if data.get("success") == 1:
            return data.get("data")
        print(f"  [warn] EK Affiliaters conversion failed: {data.get('message', data)}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  [warn] EK Affiliaters request failed: {e}")
        return None
    except ValueError:
        print("  [warn] EK Affiliaters response wasn't valid JSON")
        return None


# ---------------------------------------------------------------------
# MESSAGE FORMATTING
# ---------------------------------------------------------------------

def format_caption(deal, converted_link, settings, state):
    category = deal.get("category", "fashion")
    emoji = CATEGORY_EMOJIS.get(category, "🛍️")
    title = deal.get("title", "Great Deal")
    price = deal.get("price")
    discount = deal.get("discount", "")
    url_key = deal.get("product_url")

    lines = [f"⚡💥 *LIMITED TIME DEAL* 💥⚡ {emoji}", "", f"*{title}*"]

    if price is not None:
        lines.append(f"💰 *₹{int(price):,}*" + (f"  🏷️ *{discount} OFF*" if discount else ""))
    elif discount:
        lines.append(f"🏷️ *{discount} OFF*")

    history_line = price_history_line(url_key, price, state)
    if history_line:
        lines.append("")
        lines.append(history_line)

    lines += ["", f"🎯 Grab it here: {converted_link or deal.get('product_url')}", "",
              "⏳ Deal may expire soon — grab it now!"]

    footer = settings.get("footer_text", "")
    if footer:
        lines += ["", footer]

    return "\n".join(lines)


# ---------------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------------

def post_photo(image_url, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "photo": image_url, "caption": caption, "parse_mode": "Markdown"}
    try:
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        print("  Posted (with image) to Telegram.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  [warn] sendPhoto failed ({e}); falling back to text-only.")
        return False


def post_text(caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": caption, "parse_mode": "Markdown",
               "disable_web_page_preview": False}
    try:
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        print("  Posted (text-only) to Telegram.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"  [error] Telegram text post failed: {e}")
        return False


def post_deal(deal, caption, settings):
    image_url = deal.get("image_url")
    if settings.get("always_include_image", True) and image_url:
        if post_photo(image_url, caption):
            return True
        return post_text(caption)
    return post_text(caption)


# ---------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------

def main():
    if not EKARO_API_KEY or not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERROR: Missing one or more required secrets:")
        print("  EKARO_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        return

    settings = load_json(SETTINGS_FILE, {})
    state = load_json(STATE_FILE, default_state())
    queue_data = load_json(QUEUE_FILE, {"queue": []})
    posted_log = load_json(POSTED_LOG_FILE, {"posted": []})

    reset_daily_counts_if_new_day(state)

    if not within_active_hours(settings):
        print(f"Outside active hours ({settings.get('active_hours_start')}–"
              f"{settings.get('active_hours_end')} IST). Skipping.")
        save_json(STATE_FILE, state)
        return

    if hours_since(state.get("last_post_utc")) < settings.get("time_gap_hours", 1):
        print("Not time to post yet. Skipping.")
        save_json(STATE_FILE, state)
        return

    deal = pick_next_deal(queue_data, settings, state)
    if not deal:
        print("No eligible deal in queue right now (empty, filtered, or all under cooldown).")
        save_json(STATE_FILE, state)
        return

    print(f"Posting: {deal.get('title')}")

    converted_link = convert_link(deal["product_url"])
    caption = format_caption(deal, converted_link, settings, state)
    success = post_deal(deal, caption, settings)

    if success:
        url_key = deal["product_url"]
        state["recently_posted"][url_key] = now_utc().isoformat()
        record_price_history(state, url_key, deal.get("price"), settings)
        state["last_post_utc"] = now_utc().isoformat()
        increment_daily_count(deal.get("category", "fashion"), state)

        remove_from_queue_and_log(queue_data, deal, posted_log)
        save_json(QUEUE_FILE, queue_data)
        save_json(POSTED_LOG_FILE, posted_log)

    save_json(STATE_FILE, state)
    print("Done.")


if __name__ == "__main__":
    main()

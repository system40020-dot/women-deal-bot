# Women's Garments Deals Bot

Fully automated Telegram posting using your EK Affiliaters API key.
You add product deals to a queue; the bot converts the link, formats
a branded post with price history and image, and posts it to your
channel — on a schedule you control.

## How you actually use this day-to-day

**Adding a new deal to post:** open `queue.json` in your repo → tap
pencil (edit) → add a new entry inside the `"queue"` list, like:

```json
{
  "title": "Floral Print Kurti",
  "price": 599,
  "image_url": "https://example.com/image.jpg",
  "product_url": "https://www.myntra.com/actual-product-link",
  "category": "fashion",
  "discount": "40%"
}
```

Commit. That's it — the bot picks it up automatically on its next
eligible run, converts the link, posts it, and moves it out of the
queue into `posted_log.json` once done.

**Add as many deals as you want, anytime** — the bot posts one
eligible deal per run and works through the queue over time, based
on your `time_gap_hours` / `active_hours` settings.

## Setup

### 1. Repo secrets (Settings → Secrets and variables → Actions)
- `EKARO_API_KEY` — your EK Affiliaters public API key
- `TELEGRAM_BOT_TOKEN` — this channel's bot token
- `TELEGRAM_CHAT_ID` — this channel's @username or numeric ID

### 2. Workflow permissions
Settings → Actions → General → Workflow permissions → **Read and
write permissions** → Save (needed so the bot can update the queue
and remember its posting history)

### 3. Upload all files
Including the `.github/workflows` folder.

### 4. Test it
Actions tab → "Women's Garments Deals Bot" → Run workflow → check
your Telegram channel.

## Settings you can change anytime (settings.json)

- `time_gap_hours` — hours between posts
- `active_hours_start` / `active_hours_end` — only posts in this window (IST)
- `category_daily_limit` — max posts per category per day
- `ignore_if_price_increased` — skip a deal if price went up since last seen
- `lightning_offer_validity_minutes` — won't repost the same product too soon
- `footer_text` — your channel promo line, attached to every post

## Files

- `queue.json` — where YOU add new deals to be posted
- `deals_bot.py` — the automation logic
- `settings.json` — your controls
- `state.json` — the bot's memory (price history, timing) — don't hand-edit
- `posted_log.json` — automatic record of everything already posted

# TikTok Telegram Services Bot (starter)

## Requirements
- Python 3.10+
- Telegram bot token from @BotFather
- Your numeric Telegram user ID as owner

The code uses only Python standard library (no pip installs).

## Run (Linux/macOS)
```bash
export BOT_TOKEN="123456:ABC..."
export OWNER_ID="123456789"
python3 bot.py
```

## Run (Windows PowerShell)
```powershell
$env:BOT_TOKEN="123456:ABC..."
$env:OWNER_ID="123456789"
python bot.py
```

## Features
- Separate customer and admin/owner menus
- Services and configurable per-1000 prices
- Orders with unique TK-xxxxx identifiers
- User balance, admin credit/debit by Telegram ID
- Owner-only admin add/remove
- Manual top-up request flow and approval/rejection
- Telegram Stars invoice and successful-payment crediting
- User order history, support relay, broadcast
- SQLite persistence
- Inventory records store account username/note only (not passwords or OTPs)

## Important setup notes
1. Create a bot using @BotFather and copy its token.
2. Find your Telegram numeric ID using a trusted ID bot.
3. Set environment variables as above; do not place the token in public code or send it to anyone.
4. Start the bot with `/start`.
5. Owner commands/menu are restricted by OWNER_ID.

## Important limitations / safety
- This is a starter implementation for managing legitimate campaigns and orders. It does not automate TikTok follows, operate account farms, or bypass platform limits.
- Stars conversion here is a placeholder policy: 100 XTR per $1 credit. Decide and clearly disclose the exchange rate and price to customers. Telegram Stars are charged in XTR, not USD.
- For live commercial use, verify the Stars price and compliance with Telegram's current digital-goods rules, add terms/refund policy, and deploy with a process manager/HTTPS if adding webhook features.
- Manual top-up is amount-only in this starter. Proof image upload is not implemented; customer should send proof to your support/admin separately.
- For reliability, use backups for bot.sqlite3. Keep the database file private.

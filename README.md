# Bybit 4H Trend Scanner → Telegram Alerts

GitHub Actions–hosted crypto bot that scans the **top 100 Bybit USDT-perpetual futures** and sends high-probability trade alerts to Telegram.

**Strategy = 4H trend filter + 15m confirmation.**
**Scan cadence = every 15 minutes** (so we catch each 15m confirmation candle right after it closes).
**Dedup** = once a setup fires for a given symbol+side on a particular 4H candle, no re-alerts until the next 4H candle starts.

---

## What it does

- Every 15 minutes, fetches top 100 pairs by 24h USD turnover from Bybit V5 public API (no key needed)
- Computes EMA 50, EMA 200, RSI 14, ATR, swing highs/lows on the **4H timeframe** (the strategy)
- Detects bullish/bearish engulfings and rejection candles on the **15m timeframe** (the confirmation)
- Applies the 7-condition checklist (below) and scores confidence 0–100
- Sends a formatted Telegram alert for every signal scoring ≥ `MIN_CONFIDENCE` (default 70)
- Persists state across runs via GitHub Actions cache so the same 4H setup never re-alerts

---

## Setup (≈ 5 minutes)

### 1. Create a Telegram bot

1. Open Telegram → message `@BotFather` → `/newbot`
2. Pick a name + username, copy the **bot token** (`123456:ABC-DEF...`)
3. Message your new bot **once** (any message) so it can DM you
4. Get your **chat ID**: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` → look for `"chat":{"id": ...}`

### 2. Push this code to a GitHub repo

```bash
git init
git add .
git commit -m "Initial bot"
git remote add origin git@github.com:YOUR_USER/bybit-4h-scanner.git
git push -u origin main
```

### 3. Add secrets

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Bot token from BotFather |
| `TELEGRAM_CHAT_ID` | Your chat ID (numeric) |

### 4. Enable Actions + test

Actions tab → enable workflows → click **Bybit 4H Scanner** → **Run workflow** → wait ~1 minute → check Telegram.

---

## Cadence explained

- **Cron:** `2,17,32,47 * * * *` → runs at xx:02, xx:17, xx:32, xx:47 (UTC), about 2 minutes after each 15m candle close
- GitHub Actions cron is **best-effort** — runs may be delayed 5–15 min during peak load. Fine for 4H strategy, dedup prevents double-fires
- Per scan: ~10–15 seconds wall time (100 pairs × 2 API calls × 50ms cushion)
- Monthly Actions minutes: ~96 runs/day × 0.25 min = ~720 min/month → fits free tier (2000 min/month private, unlimited public)

---

## The 7-condition checklist

A signal is generated only when **ALL** are true on a pair:

### Long
1. Price > EMA 200 (4H)
2. EMA 50 > EMA 200 (4H)
3. Current 4H candle is not a strong-body green (filters out late entries on pumps)
4. RSI(14) on 4H between 40–55
5. Price within 2.5% of EMA 50 **or** within 3% of recent 30-bar swing low
6. **15m candle** is bullish engulfing **or** bullish rejection (long lower wick + green close)
7. 15m confirmation candle volume ≥ 1.2× the 20-bar average

### Short
Symmetric — flipped everywhere (below EMA 200, EMA 50 below EMA 200, RSI 45–60, near resistance, bearish confirmation candle).

---

## Tuning

In `.github/workflows/scan.yml`:

| Variable | Default | Effect |
|---|---|---|
| `TOP_N` | `100` | How many pairs to scan |
| `MIN_CONFIDENCE` | `70` | Higher = fewer but stronger alerts. Try 75–80 for ultra-strict. |
| `LTF_INTERVAL` | `15` | `15` or `5` — set to `5` if you want 5m confirmation candles. Change cron too if you go 5m (e.g. `*/5 * * * *`). |
| `SEND_SUMMARY` | `false` | Set `true` for a short footer message whenever new alerts go out (skipped on empty runs either way) |

Strategy thresholds live in `strategy.py` (top of file):
- `EMA_PROXIMITY_PCT`, `SUPPORT_PROXIMITY_PCT` — how close is "near"
- `VOL_MULT_REQUIRED` — volume surge requirement
- `RSI_*_MIN/MAX` — RSI bands per side

---

## Alert format

```
🟢 NEW SIGNAL
📊 PAIR: BTC/USDT
📈 SIGNAL: LONG
💰 ENTRY: 67,420.00 – 67,580.00
🛑 STOP LOSS: 65,900.00
🎯 TP 1 (1R): 68,940.00
🎯 TP 2 (2.5R): 71,220.00
📉 RSI: 46.3
📊 TREND: Bullish
🔥 CONFIDENCE: 82/100

🧠 REASON:
strong EMA spread (4.2%) | RSI in sweet spot (46) | bullish engulfing on 15m | confluence: EMA50 + support

⚠️ Leverage 5x–15x isolated · Risk max 2% capital
```

---

## How dedup works

- Each alerting event is keyed `{SYMBOL}_{SIDE}_{4hCandleOpenMs}` (e.g. `BTCUSDT_LONG_1736380800000`)
- After each run, that key is saved to `state.json` and cached via `actions/cache`
- Next run loads the cache; if the same setup is still firing on the same 4H candle, it's silently skipped
- When the 4H candle rolls over (every 4 hours), all keys for prior candles become stale and a fresh setup can alert again
- Entries older than 12 hours are auto-pruned

This means: **max 1 alert per symbol per side per 4H candle.** A persistent bullish setup on BTC will alert once when the 15m confirmation fires, and won't re-spam every 15 min.

---

## Notes & caveats

- **Signal generator, not executor.** It will never place orders.
- **GitHub Actions cron isn't precise.** Expect ~5–15 min variance. Fine for this strategy.
- **First run after cache eviction** will re-alert active setups (cache TTL is ~7 days of inactivity). Rarely happens with regular cron.
- **Backtest before sizing.** The thresholds are reasonable defaults but paper-trade alerts for 2–4 weeks first.
- **Bybit public rate limits** are 600 req / 5 sec. We use ~200 reqs total per scan with 50ms spacing — well within limits.

---

## File structure

```
.
├── .github/workflows/scan.yml   # GitHub Actions cron + runner
├── main.py                      # Orchestrator + dedup logic
├── bybit_client.py              # Bybit V5 API wrapper
├── indicators.py                # EMA, RSI, ATR, swing, candle patterns
├── strategy.py                  # 7-condition evaluation + confidence
├── telegram_notify.py           # Telegram Bot API sender
├── state.py                     # Dedup state persistence
├── requirements.txt             # Just `requests`
└── README.md
```

---

## Running locally

```bash
export TELEGRAM_BOT_TOKEN="123:ABC..."
export TELEGRAM_CHAT_ID="123456789"
export TOP_N=20                 # smaller for quick test
export MIN_CONFIDENCE=60        # looser for quick test
pip install -r requirements.txt
python main.py
```

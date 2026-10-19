# CRT indicator / CDX trading bot

Automates trades on **CDX V3 Pro** signals (a closed-source TradingView indicator from Discord) for NQ/MNQ futures, routed through NinjaTrader to a prop account (Tradeify, $50k, $2,000 drawdown). The old in-house indicators (`crt_indicator.pine`, Phase72A, `phase16`–`phase86`) are history; CDX is the signal source since **2026-09-22**.

## Two machines

- **Mac**: where the user and Claude work (research, training, code). The user is at school during the trading day.
- **Windows PC** (`C:\Users\allet\Trading Bot`): runs the live bot unattended. It has NinjaTrader and TradingView.
- Code goes Mac → GitHub `main` → `git pull` on Windows, then a bot restart. **Never assume Windows has pulled.**
- Logs come back on the **`bot-logs` branch**: `scripts/sync_bot_logs.ps1` runs every 30 minutes from Task Scheduler on Windows (installed by `scripts/install_log_sync_task.ps1`). On the Mac, `bash scripts/fetch_bot_logs.sh` copies them into place and prints the health check (`phase74/logs/bot_pc_health.json`). Check it first when asked how the bot is doing.

## Live path

1. A CDX TradingView alert hits the webhook: `phase74/webhook/secure_receiver.py`, schema `phase73/webhook/schemas.py` (`timeframe` is forced to `1m` even though the CDX chart is 3m).
2. `phase74/runtime/live_stack.py` `on_webhook_signal` runs the gates in order (session pauses, repeat-alert window, HTF bias shadow, quality gates, range lock, day halt), then the frozen Phase73 engine.
3. `cdx_vision/` screen-reads CDX Entry / SL / TP1 / TP2 off TradingView before the order (fragile: 5 of 46 real reads confirmed).
4. `phase85/execution/adapter.py` sends the NinjaTrader order. Live size: **10 MNQ**.
5. Bars come from the NinjaTrader bar bridge into `phase74/logs/bars.csv`. **The bar feed stopped on 2026-10-02 and was still down on 2026-10-19**; signals kept arriving. Bar-driven exits and the HTF read need it.

Config: `phase74/config/default.json`. The Phase73 engine files are hash-frozen (`verify_phase73_freeze`); phase74 config is not.

## Research state (as of 2026-10-19)

- **Taking every CDX signal loses** with every stop type tested (−0.07R to −0.50R per trade).
- **15m market structure decides it.** Signals where the 15m structure agrees with the trade: median 4h move ~130 pts, +1.09R/trade (1.5×ATR stop, 2R). Against: −0.69R. Code: `phase74/quality/htf_bias.py`, live in **shadow only** (`htf_bias.enforce: false`, log `phase74/logs/htf_bias.jsonl`; its live rule is "skip only when 15m and 1H both disagree", which research shows is too loose).
- **The fixed 14.25-pt stop is the main exit problem**: it is hit before most good setups run. 1.5×ATR(3m) or structural stops did far better. Which of those is best is not settled.
- **Size by dollar risk, not fixed contracts.** Fixed 10 MNQ with wide stops can lose $2k in one trade.
- Replay: `forward_rehearsal/research/htf_stop_replay.py` → `forward_rehearsal/reports/htf_stop_replay/REPORT.md`.
- Sample is small (~90 CDX signals with bars, Sep 22 – Oct 2). Don't present results as proven.

## Learning layer (`cdx_ml/`)

The user wants the bot to learn when to take a CDX signal and where to put stops and targets (meta-labeling: CDX picks direction, a model picks take/skip + option).

- `python -m cdx_ml.dataset` builds `cdx_ml/data/dataset.csv`: one row per signal, features from bars before the signal, triple-barrier outcomes for 7 stop types × 3 targets. Check `DATA_CARD.md` after.
- `python -m cdx_ml.train` runs a walk-forward test (train on earlier days, test on the next unseen day) and compares the model with the fixed rules. It writes `cdx_ml/reports/TRAINING_REPORT.md` and decides `PROMOTE` or `KEEP_RULE`.
- First run (2026-10-19): `KEEP_RULE`. Model −1.2R, "15m agrees + 1.5×ATR, 2R" rule +20.8R (but that rule was found on the same data). Needs ~300 CDX signals before a model can be trusted.
- Requirements: `pip install -r cdx_ml/requirements.txt` (scikit-learn 1.5.2).

## Rules

- **Don't change live order behavior** (gates, stops, sizing, routing) unless the user explicitly asks. New logic ships in shadow mode first, logging what it would do.
- **Don't tune on the same few days.** Every rule change gets a walk-forward or held-out check, and results are reported with the sample size.
- **Dollars:** live trades are **MNQ, $2 per point, $0.50 per tick**, 10 contracts unless stated. Use NQ ($20/pt) only when the user says NQ. (The `.cursor/rules/nq-point-value.mdc` $20 rule is outdated.)
- **Commit and push after making changes**, unless the user says not to (carried over from the Cursor rules). Commit messages are one plain sentence about why. Never force-push main. A repo post-commit hook (`.githooks/post-commit`) may push each commit automatically.
- **The GitHub repo is public** until the user makes it private. Never commit `.env`, keys, `phase85/logs/audit.jsonl`, or anything with account numbers or fills.
- Don't commit `phase76/data/` (782 MB) or other large generated data; GitHub rejects files over 100 MB.
- Don't decompile or bypass CDX's protected source. Reconstructing its behavior from its outputs is fine.

## Tests

- `python3 -m pytest -q phase74/tests cdx_ml/tests`
- 4 phase74 tests already failed before 2026-10-09 (execution_route, phase74_integration p74_26, range_lock, reversal_watch). Don't count them as new breakage.

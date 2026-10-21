# CRT indicator / CDX trading bot

Automates trades on **CDX V3 Pro** signals (a closed-source TradingView indicator from Discord) for NQ/MNQ futures, routed through NinjaTrader to a prop account (Tradeify, $50k, $2,000 drawdown). The old in-house indicators (`crt_indicator.pine`, Phase72A, `phase16`–`phase86`) are history; CDX is the signal source since **2026-09-22**.

## Two machines

- **Mac**: where the user and Claude work (research, training, code). The user is at school during the trading day.
- **Windows PC** (`C:\Users\allet\Trading Bot`): runs the live bot unattended. It has NinjaTrader and TradingView.
- Code goes Mac → GitHub `main` → `git pull` on Windows, then a bot restart. **Never assume Windows has pulled.**
- Logs come back on the **`bot-logs` branch**: `scripts/sync_bot_logs.ps1` runs every 30 minutes from Task Scheduler on Windows (installed by `scripts/install_log_sync_task.ps1`). On the Mac, `bash scripts/fetch_bot_logs.sh` copies them into place and prints the health check (`phase74/logs/bot_pc_health.json`). Check it first when asked how the bot is doing. **Alerts go to Discord** (2026-10-21): the PC's sync script posts when the bot stops, bars go stale, or the sync was down 45+ min, plus one recovery message; `.github/workflows/bot-pc-heartbeat.yml` runs on GitHub every 30 min and posts if `bot-logs` hasn't been pushed for 45+ min (PC off/asleep/offline). Both read the webhook from `DISCORD_WEBHOOK_URL` (PC: `phase74\.env`; GitHub: repo secret). Never commit or print that URL. Test: `sync_bot_logs.ps1 -TestAlert`, or run the workflow with "Send a test message". **`bot-logs` holds only logs: never merge it into `main` or open a PR for it**, even if GitHub suggests one. The fetched copies overwrite tracked files like `phase74/logs/bars.csv` on the Mac; don't commit those to `main` (no `git commit -a`), they already live on `bot-logs`.

## Live path

1. A CDX TradingView alert hits the webhook: `phase74/webhook/secure_receiver.py`, schema `phase73/webhook/schemas.py` (`timeframe` is forced to `1m` even though the CDX chart is 3m).
2. `phase74/runtime/live_stack.py` `on_webhook_signal` runs the gates in order (session pauses, repeat-alert window, HTF bias shadow, quality gates, range lock, day halt), then the frozen Phase73 engine.
3. With `levels.source: "chart"`, `cdx_vision/` screen-reads CDX Entry / SL / TP1 / TP2 off TradingView before the order (fragile: 5 of 46 real reads confirmed). With `"atr"`, levels come from bars and vision is off.
4. `phase85/execution/adapter.py` sends the NinjaTrader order. Live size: **10 MNQ**.
5. Bars come from the NinjaTrader bar bridge into `phase74/logs/bars.csv`. **The bar feed stopped on 2026-10-02 and was still down on 2026-10-19**; signals kept arriving. Bar-driven exits and the HTF read need it.

Config: `phase74/config/default.json`. The Phase73 engine files are hash-frozen (`verify_phase73_freeze`); phase74 config is not.

## Research state (as of 2026-10-19)

- Only TradingView alert ids (timestamps like `2026-10-09T12:42:00Z`) are real CDX signals. Random-UUID ids are the bot's readiness-probe test signals (`make_test_signal`) and `REEN*` are manual reentries; `cdx_ml.dataset.is_alert_id` filters them. A Sep 28 burst of 44 fake LONGs skewed earlier results until 2026-10-19.
- **NinjaTrader bars are stamped at their close** (the 12:41–12:42 bar is 12:42; 17:00 is the last bar before the daily break, 18:01 the first after). `htf_bias.resample` groups them that way so 3m/15m/1H candles match TradingView; research features include the bar stamped at the signal minute and trade paths start after it. Before 2026-10-19 the research was one minute off, which made the fixed stop look worse than it is.
- **Bars for the Oct 2–19 outage** come from a NinjaTrader Historical Data export, `phase74/logs/nt_export_mnq_1m.txt` (UTC, close-stamped; `cdx_ml.dataset.load_bars` reads any `nt_export_*.txt`, the bot's own `bars.csv` wins on overlap). That raised usable real CDX signals from 61 to **98** on 2026-10-21.
- **Out-of-sample check (2026-10-21):** the 49 signals added by the backfill were never used to design any rule. On them, taking every CDX signal (1.5×ATR, 2R) was **−0.11R/trade**; overall 98: +0.17R. **Taking every signal is not an edge.**
- **The 15m filter is the only rule that held out of sample:** 15m agrees +0.19R vs not agreeing −0.31R on the new 49 (+0.59R vs −0.11R on all 98, n=40 vs 58). The momentum filters (ATR expanding, near the day's extreme) **failed** out of sample (−0.75R n=5, −0.01R n=13); keep forward-testing them but expect little.
- **Stops/exits:** 1.5×ATR with a 2R target still beats the fixed 14.25 stop (−0.06R on 98) and every breakeven / partial / trail rule; 3R ≥ 2R. The fixed stop's result flips sign with a one-minute change in entry timing.
- **Eval odds** (`eval_pass_sim --bootstrap`, 19 real sessions, 15m filter): $200 risk 96% pass / 3% blown / median 21 days; $300 90% / 10% / 13; **$400 83% / 17% / 12**; $600 70% / 30% / 9. Without the filter every size blows 41–84%.
- **ATR level source for live orders** (`levels.source` in `phase74/config/default.json`, `phase74/quality/atr_levels.py`): `"chart"` (default, current behavior: vision levels when `require_chart_levels`, else fixed 14.25 + wick stop) or `"atr"` (stop 1.5×ATR(3m), target 2R, size from $600 risk, capped at 10 and at NinjaTrader's `MAX_QUANTITY`; no vision, no trail; refuses the entry if bars are stale). `start-ninjatrader-live.ps1` turns vision off when it's `"atr"`. Only switch it on when the user says so, after the shadow profiles have a track record.
- **Shadow ATR profiles** (`phase74/quality/shadow_profile.py`, config `shadow_profiles`): `atr1.5_all_300` (every real CDX signal) and `atr1.5_15m_300` (15m agrees only) paper-trade each alert with a 1.5×ATR(3m) stop, 2R target, **$300 risk** on MNQ (since 2026-10-21; earlier $600 and $400 versions are disabled), one position at a time, the bot's day limits, and their own $50k eval balance. Never send orders. Log `phase74/logs/shadow_profiles.jsonl`; summary: `python -m phase74.tools.shadow_profile_report` (after `fetch_bot_logs.sh`). Momentum candidates added 2026-10-21, now all $300: `atr1.5_atrexp_300` (ATR ≥ 1.30× its 100-candle average), `atr1.5_dayext_300` (entry within 2.4 ATR of the futures day's high for longs / low for shorts), `atr1.5_momo_300` (either), `atr1.5_15m_momo_300` (15m agrees and either). Cutoffs were fixed from the top/bottom third of the 61 real CDX signals **before** forward testing; don't retune them on the forward data. Judge after ~50 trades each vs `atr1.5_all_300`. Started 2026-10-19. Why $300: on 98 real CDX signals (`eval_pass_sim --bootstrap`, 15m filter) $300 blew 10% of evals vs 17% at $400 and 30% at $600, for about one day of speed.
- **Size by dollar risk, not fixed contracts.** Fixed 10 MNQ with wide stops can lose $2k in one trade.
- Replay: `forward_rehearsal/research/htf_stop_replay.py` → `forward_rehearsal/reports/htf_stop_replay/REPORT.md`.
- Sample is still small (98 real CDX signals with bars). Don't present results as proven.

## Learning layer (`cdx_ml/`)

The user wants the bot to learn when to take a CDX signal and where to put stops and targets (meta-labeling: CDX picks direction, a model picks take/skip + option).

- `python -m cdx_ml.dataset` builds `cdx_ml/data/dataset.csv`: one row per signal, features from bars before the signal, triple-barrier outcomes for 7 stop types × 3 targets. Check `DATA_CARD.md` after.
- `python -m cdx_ml.train` runs a walk-forward test (train on earlier days, test on the next unseen day) and compares the model with the fixed rules. It writes `cdx_ml/reports/TRAINING_REPORT.md` and decides `PROMOTE` or `KEEP_RULE`.
- Latest run (2026-10-21, 98 CDX signals): `KEEP_RULE`. Model −11.8R on 49 trades vs the "15m agrees + 1.5×ATR, 2R" rule +23.6R. Needs ~300 CDX signals before a model can be trusted.
- Requirements: `pip install -r cdx_ml/requirements.txt` (scikit-learn 1.5.2).

## Rules

- **Don't change live order behavior** (gates, stops, sizing, routing) unless the user explicitly asks. New logic ships in shadow mode first, logging what it would do.
- **Don't tune on the same few days.** Every rule change gets a walk-forward or held-out check, and results are reported with the sample size.
- **Dollars:** live trades are **MNQ, $2 per point, $0.50 per tick**, 10 contracts unless stated. Use NQ ($20/pt) only when the user says NQ. (The `.cursor/rules/nq-point-value.mdc` $20 rule is outdated.)
- **Commit and push after making changes**, unless the user says not to (carried over from the Cursor rules). Commit messages are one plain sentence about why. Never force-push main. A repo post-commit hook (`.githooks/post-commit`) may push each commit automatically.
- The GitHub repo is private (since 2026-10-19). Still never commit `.env`, keys, `phase85/logs/audit.jsonl`, or anything with account numbers or fills.
- Don't commit `phase76/data/` (782 MB) or other large generated data; GitHub rejects files over 100 MB.
- Don't decompile or bypass CDX's protected source. Reconstructing its behavior from its outputs is fine.

## Tests

- `python3 -m pytest -q phase74/tests cdx_ml/tests`
- 4 phase74 tests already failed before 2026-10-09 (execution_route, phase74_integration p74_26, range_lock, reversal_watch). Don't count them as new breakage.

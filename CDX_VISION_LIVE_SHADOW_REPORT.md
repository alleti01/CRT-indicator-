# Live shadow

Configuration loaded by `scripts/start-ninjatrader-live.ps1` from `phase74/.env`, then forced again in that script:

- CDX_VISION_ENABLED=true
- CDX_VISION_SHADOW_ONLY=true
- CDX_VISION_EXECUTION_ENABLED=false
- CDX_VISION_AUTO_RIGHT_ENABLED=true

`may_route_orders()` stays false. Vision cannot place, change, or cancel an order.

The restarted live process printed:

- CDX_VISION_ENABLED=true
- CDX_VISION_SHADOW_ONLY=true
- CDX_VISION_EXECUTION_ENABLED=false
- CDX_VISION_AUTO_RIGHT_ENABLED=true
- TRADINGVIEW_TARGET=TradingView.exe
- CDX_VISION_WORKER_STARTED

NinjaTrader reconnected on the bar bridge after that restart. The capture thread starts after a webhook is accepted. It does not run on the webhook thread, and it does not place an order.

`python -m cdx_vision.ready` printed `CDX_VISION_LIVE_SHADOW_READY`.

No real TradingView webhook arrived after the flag was turned on. The off-screen recovery is a TEST row, not a live signal.

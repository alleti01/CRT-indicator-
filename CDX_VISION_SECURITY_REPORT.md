# CDX vision security

Screenshots are not uploaded. There is no cloud vision call.

Debug images are off unless `CDX_VISION_SAVE_DEBUG_IMAGES=true`. The capture helper, when used, is limited to a window whose title contains `TradingView`, then a normalized chart crop. It does not walk the whole desktop.

The ledger stores prices and reason codes, not account passwords. `windows_chart.json` is written only by the calibrate command and is not required to run.

Vision failure is caught around the webhook hook. It cannot cancel a stop, cancel a target, or flatten a position. `may_route_orders` returns false even if `CDX_VISION_EXECUTION_ENABLED` is set.

# First live shadow signal

No real CDX webhook was received after shadow mode was turned on.

The off-screen recovery is stored as `TEST_AUTORIGHT_354fde45`. That row is a test. It is not a live signal.

When the next real CDX alert arrives, the webhook path will capture TradingView, pan right only if the current labels are off screen, and append one shadow row for that signal_id. It will not change the stop, the target, or the order.

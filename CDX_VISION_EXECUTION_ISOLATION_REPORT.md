# Execution isolation

`cdx_vision` does not import the NinjaTrader adapter, and it has no place, flatten, or protect function.

`VisionConfig.may_route_orders()` returns false even when `CDX_VISION_EXECUTION_ENABLED` is set.

The live capture, the OCR probe, and the test trigger were run with that gate false. Execution calls during those commands: 0.

Funded routing from vision: no.

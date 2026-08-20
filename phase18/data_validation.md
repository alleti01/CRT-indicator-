# Phase 18 unseen-data validation gate

Status: **PASS**. This report was completed before the Phase 18 strategy run.

## Requested and resolved window

- Preferred evaluation request: 2021-01-01 through 2023-12-31 inclusive.
- Final fully covered evaluation window: **2021-01-01 through 2023-12-28 inclusive**, America/Chicago.
- Reason: CME NQ did not reopen on Sunday 2023-12-31 during the New Year holiday. The unchanged coverage gate cannot reach the 2024-01-01 00:00 CT end boundary without loading 2024 development data. December 28 is the latest inclusive date whose next-midnight boundary is covered while preserving zero overlap. December 29 bars are retained only as right-side coverage.
- The failed coverage-only audit for the originally requested endpoint is preserved under `data_validation/requested_window_2021-01-01_to_2023-12-31/`.

## Databento acquisition

- Dataset/schema: `GLBX.MDP3` / `ohlcv-1m`.
- Symbol/input type: `NQ.v.0` / `continuous`.
- Acquisition interval: 2020-12-01 00:00 UTC through 2024-01-01 06:00 UTC exclusive.
- Estimated cost before download: **$3.9816**.
- Downloaded raw rows: **1,090,620**.
- Duplicate raw timestamp/instrument identities: **0**.
- Normalized unique one-minute rows: **1,090,620**.
- Provider reduced-quality notices observed: 2021-12-05 and 2022-01-02. They are retained and disclosed; no date or trade is excluded.

## Continuous-contract processing

- Method: preserve Databento's provider-selected `instrument_id` transitions, then use the Phase 16 causal forward additive splice.
- Contract transitions: **13**.
- Maximum absolute adjusted transition gap: **0.0 points**.
- Roll selection does not inspect future bars; the same offset is applied to O/H/L/C, and volume is not adjusted.

## Five-minute construction

- Timezone during processing: `America/Chicago`; stored timestamps are UTC and convert back on load.
- Aggregation: clock-aligned five-minute buckets; open first, high max, low min, close last, volume sum.
- Final five-minute rows including warm-up/right coverage: **218,163**.
- Phase 18 rows inside the final window: **212,019**.
- Incomplete non-empty five-minute groups retained: **178**, matching the validated Phase 16 semantics for Databento minutes with no emitted record.
- All timestamps are chronological and aligned to minute modulo five = 0.
- Duplicate five-minute timestamps: **0**.
- Invalid OHLC rows: **0**.
- First in-window bar: 2021-01-03 17:00 CT (January 1 was a market holiday).
- Last in-window bar: 2023-12-28 23:55 CT.
- Left coverage: **PASS**.
- Right coverage: **PASS**.

## Gap and session audit

- Weekend closures: 150.
- Holiday/scheduled closures: 624.
- The raw validator labeled 121 twenty-minute gaps as potential intraday gaps. Every one occurs from a 15:10 five-minute bar to a 15:30 bar on a trading day through 2021-06-25. These are the historical CME equity-index 15:15–15:30 CT market pause, not missing data.
- CME eliminated that pause effective trade date 2021-06-28: <https://www.cmegroup.com/notices/electronic-trading/2021/06/20210621.html>.
- Unexpected missing five-minute intervals after schedule reclassification: **0**.
- Frozen session boundaries remain exchange-local and unchanged.

## Isolation

- Phase 16/17 development start: 2024-01-01 CT.
- Processed rows at or after development start: **0**.
- Development overlap: **0 rows / PASS**.
- Phase 16 strategy files and Phase 17 candidate files were not modified.

Supporting machine-readable artifacts are in `phase18/data_validation/`.

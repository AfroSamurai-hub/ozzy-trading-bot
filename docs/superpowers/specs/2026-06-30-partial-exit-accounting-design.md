# Partial Exit Accounting Design

## Goal

Make every partial-exit record describe the fraction of the immutable original position that was actually closed. This restores accurate remaining-quantity, lifecycle, and performance reporting without changing entry rules, exit thresholds, or broker execution behavior.

## Problem

OzzyBot currently closes some partial exits as a percentage of the position that remains, then stores that same percentage in `exits.qty_pct`. Downstream accounting treats `qty_pct` as a percentage of the original position. Those meanings diverge after the first partial.

For example, two sequential 25% reductions of the current position close 25% and 18.75% (`0.25 × 0.75 = 0.1875`) of the original position, not 50% total. Recording both rows as `0.25` overstates the closed quantity and understates what remains.

BNBUSDT trade `100373` demonstrates the defect. Its immutable original quantity is 18.13. Exchange fills closed 4.53 and 3.40, so the original-position fractions are approximately 0.249862 and 0.187534. The database currently records both exits as 0.25 even though the exchange quantity after those fills was correctly 10.20.

## Accounting Contract

`exits.qty_pct` has one meaning everywhere:

```text
actual closed quantity / immutable original trade quantity
```

The immutable denominator is the trade quantity captured when the trade was opened. It is never replaced with the current exchange quantity after reductions.

For monitor-initiated market reductions, the connector requests Binance `newOrderRespType=RESULT`. Quantity evidence is resolved in this order:

1. positive `executedQty` from a `FILLED` or `PARTIALLY_FILLED` create-order response;
2. positive `executedQty` from `futures_get_order` using the returned `orderId`;
3. the sum of account-trade `qty` rows grouped by that `orderId`, retaining each fill `id` as evidence;
4. the requested, symbol-rounded close quantity only when Binance execution evidence is unavailable.

`cumQty` may substitute for `executedQty` only when `executedQty` is absent; the two fields are never added together. An unconfirmed rounded-request fallback is labeled `requested_rounded_unconfirmed` and leaves accounting unchecked until later fill reconciliation. Exchange-detected milestone exits use the filled order's positive `executedQty`; if an order spans multiple account-trade fills, reconciliation aggregates those fills by `orderId`.

If the original quantity is missing, zero, or invalid, the system must not invent a fraction such as `1.0`. The exit can still be recorded for operational safety, but `qty_pct` remains unknown and the audit note states why accounting could not be derived. This is an accounting failure to surface, not a reason to leave an exchange position open.

## Implementation Boundaries

### Central fraction calculation

Add one monitor-side helper that accepts the immutable original quantity and actual or requested closed quantity. It returns an original-position fraction only for valid positive inputs. Its floating-point epsilon is `max(1e-12, original_qty × 1e-9)` in quantity units. A closed quantity up to `original_qty + epsilon` may be clamped to `1.0`; anything larger is materially impossible, produces no fraction, and emits an accounting warning.

The epsilon handles binary floating-point representation only. It is deliberately not a whole exchange quantity step: broker-reported fills are already step-quantized, so an extra full step is evidence of an accounting mismatch. Separately, exchange-versus-database remaining-quantity reconciliation allows one Binance `LOT_SIZE.stepSize` (or the configured quantity quantum in PAPER/mocked tests).

Partial-exit paths will call this helper after the broker close result is known. The configured percentage remains an execution instruction relative to the current position; it is not persisted as the accounting fraction.

### Partial-exit writers

Apply the contract to every path that can record a partial close, including:

- milestone exits;
- exchange-detected milestone fills;
- regime-aware chop reductions;
- early-profit protection;
- time-decay reductions;
- tiered reductions;
- time-based position reductions.

Terminal exits represent the actual final slice divided by the immutable original quantity and must not use a configured percentage. The audit found that explicit protective terminal paths already calculate `current_exchange_qty / original_qty` when the denominator is valid. Implementation must also correct three terminal edge cases: a missing original quantity currently falls back to `1.0`; the externally detected close path passes the original quantity instead of the final slice; and `time_reduce` is incorrectly classified as terminal, which can suppress the later final exit row. Terminal quantities must become evidence-based or unknown, never an invented full-close fraction, and partial reductions must not act as terminal markers.

### Audit evidence

Each new partial-exit note will include enough evidence to reproduce the calculation:

- `closed_qty`;
- `original_qty`;
- resulting original-position `qty_pct`;
- configured current-position reduction percentage, when applicable;
- exact `qty_source` (`create_response.executedQty`, `create_response.cumQty`, `order_query.executedQty`, `order_query.cumQty`, `account_trade_qty_sum`, `filled_order.executedQty`, `filled_order.cumQty`, `paper_simulated`, or `requested_rounded_unconfirmed`);
- Binance `orderId` and account-trade fill `id` values when available.

`paper_simulated` confirms only deterministic simulated quantity accounting; it is never represented as exchange confirmation and does not raise an unconfirmed-exchange warning. This is diagnostic metadata only; no new strategy decision depends on the note text.

### Known BNBUSDT repair

The current BNBUSDT database rows will be corrected only after a database backup and a repeated read-only exchange query confirms this exact mapping:

| DB exit | Binance account trade | Evidence |
|---|---|---|
| exit `1027`, `milestone_0`, `2026-06-30 04:08:36 UTC` | fill `143517400`, order `1775544504` | BUY SHORT `4.53` at `2026-06-30 04:08:32.398 UTC` |
| exit `1028`, `regime_aware_chop_profit_taken`, `2026-06-30 04:09:18 UTC` | fill `143517525`, order `1775555147` | BUY SHORT `3.40` at `2026-06-30 04:09:14.141 UTC` |

The primary exchange grouping key is `orderId`; account-trade `id` identifies each constituent fill. A DB row is considered unambiguous only when exactly one grouped closing order for BNBUSDT SHORT has the matching quantity and falls within ten seconds before or after that row's timestamp, with no competing candidate. The repair changes the two affected `qty_pct` values to `4.53 / 18.13` and `3.40 / 18.13`, respectively. It does not rewrite realized PnL, prices, reasons, timestamps, notes, or unrelated trades.

If either exit row cannot be matched unambiguously, that row is not modified and the mismatch is reported for manual review.

## Rollout Safety

No running service is restarted and no code is deployed while any exchange position remains open. The implementation and tests can be completed in an isolated worktree, but the flat-state gate is re-evaluated immediately before rollout; positions closing or opening during implementation do not waive that gate. Binance must confirm all positions are flat and relevant open orders are absent at the actual deployment moment.

Immediately before database repair or deployment:

1. confirm exchange, database, and protection state;
2. take a timestamped database backup;
3. verify the target Git revision and migration-free schema compatibility.

Webhook and monitor are restarted together after the flat-state gate. Post-restart checks must confirm service health, revision alignment, and clean exchange/database/protection reconciliation.

## Verification

Focused regression tests must prove:

- a first 25% close of an original quantity records `0.25` within `abs_tol=1e-12` and `rel_tol=1e-9`;
- a second 25% close of the remaining 75% records `0.1875` within the same tolerance;
- the two rows sum to `0.4375`, leaving `0.5625`, within the same tolerance;
- broker-confirmed quantity takes precedence over requested quantity;
- `executedQty`, order-query, account-trade aggregation, and unconfirmed rounded-request precedence behave exactly as specified;
- invalid or missing original quantity never becomes an invented full-close fraction;
- every partial-exit writer passes an original-position fraction to `trade_db.log_exit`;
- explicit and externally detected terminal exits record only the final original-position slice;
- realized-PnL accounting remains unchanged.

The full automated test suite must pass before rollout and provides path coverage for every listed writer. After rollout, the first observed partial lifecycle must reconcile against exchange fills before the shared accounting mechanism is considered operationally proven. Each distinct writer path receives the same first-use runtime audit when it is eventually exercised; a mismatch marks that trade's accounting unchecked and raises an alert without changing exchange execution.

## Non-Goals

- No entry-filter or signal changes.
- No exit-threshold, timing, stop, take-profit, or position-sizing changes.
- No schema migration unless implementation evidence proves the existing nullable fraction cannot safely represent an unknown value.
- No broad historical-data rewrite.
- No automatic strategy promotion or optimization.

## Success Criteria

For every new trade, the sum of recorded exit fractions matches exchange-confirmed closed quantity divided by the immutable original quantity within the helper tolerance. Database-versus-exchange remaining quantity agrees within one `LOT_SIZE.stepSize`, lifecycle reports stop overstating partial reductions, and no strategy behavior changes as a side effect.

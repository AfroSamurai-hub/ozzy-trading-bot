# Partial Exit Accounting Design

## Goal

Make every partial-exit record describe the fraction of the immutable original position that was actually closed. This restores accurate remaining-quantity, lifecycle, and performance reporting without changing entry rules, exit thresholds, or broker execution behavior.

## Problem

OzzyBot currently closes some partial exits as a percentage of the position that remains, then stores that same percentage in `exits.qty_pct`. Downstream accounting treats `qty_pct` as a percentage of the original position. Those meanings diverge after the first partial.

For example, two sequential 25% reductions of the current position close 25% and 18.75% of the original position, not 50% total. Recording both rows as `0.25` overstates the closed quantity and understates what remains.

The open BNBUSDT trade demonstrates the defect. Its immutable original quantity is 18.13. Exchange fills closed 4.53 and 3.40, so the original-position fractions are approximately 0.249862 and 0.187534. The database currently records both exits as 0.25 even though the exchange correctly holds 10.20.

## Accounting Contract

`exits.qty_pct` has one meaning everywhere:

```text
actual closed quantity / immutable original trade quantity
```

The immutable denominator is the trade quantity captured when the trade was opened. It is never replaced with the current exchange quantity after reductions.

The numerator is the broker-confirmed closed quantity when the close response supplies it. If the broker response does not expose a usable quantity, the requested, symbol-rounded close quantity may be used and the source must be identified in the audit note.

If the original quantity is missing, zero, or invalid, the system must not invent a fraction such as `1.0`. The exit can still be recorded for operational safety, but `qty_pct` remains unknown and the audit note states why accounting could not be derived. This is an accounting failure to surface, not a reason to leave an exchange position open.

## Implementation Boundaries

### Central fraction calculation

Add one monitor-side helper that accepts the immutable original quantity and actual or requested closed quantity. It returns a clamped original-position fraction only for valid positive inputs. Small exchange rounding differences may be clamped to the valid `[0, 1]` range; materially impossible quantities must be logged as an accounting warning rather than silently normalized.

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

Terminal exits continue to represent the actual remaining fraction of the original position. Existing terminal accounting must use the same invariant and must not be changed into a configured percentage.

### Audit evidence

Each new partial-exit note will include enough evidence to reproduce the calculation:

- `closed_qty`;
- `original_qty`;
- resulting original-position `qty_pct`;
- configured current-position reduction percentage, when applicable;
- whether `closed_qty` came from the broker response or the rounded request.

This is diagnostic metadata only; no new strategy decision depends on the note text.

### Known BNBUSDT repair

The current BNBUSDT database rows will be corrected only after a database backup and exact matching against exchange order/fill identifiers. The repair changes the two affected `qty_pct` values to `4.53 / 18.13` and `3.40 / 18.13`, respectively. It does not rewrite realized PnL, prices, reasons, timestamps, or unrelated trades.

If either exit row cannot be matched unambiguously, that row is not modified and the mismatch is reported for manual review.

## Rollout Safety

No running service is restarted and no code is deployed while any of the current BNBUSDT, BTCUSDT, or SUIUSDT positions remains open. The implementation and tests can be completed in an isolated worktree, but runtime rollout waits until Binance confirms all positions are flat and relevant open orders are absent.

Immediately before database repair or deployment:

1. confirm exchange, database, and protection state;
2. take a timestamped database backup;
3. verify the target Git revision and migration-free schema compatibility.

Webhook and monitor are restarted together after the flat-state gate. Post-restart checks must confirm service health, revision alignment, and clean exchange/database/protection reconciliation.

## Verification

Focused regression tests must prove:

- a first 25% close of an original quantity records approximately `0.25`;
- a second 25% close of the remaining 75% records approximately `0.1875`;
- the two rows sum to approximately `0.4375`, leaving approximately `0.5625`;
- broker-confirmed quantity takes precedence over requested quantity;
- requested rounded quantity is used only when the broker quantity is unavailable;
- invalid or missing original quantity never becomes an invented full-close fraction;
- every partial-exit writer passes an original-position fraction to `record_exit`;
- existing terminal exits and realized-PnL accounting remain unchanged.

The full automated test suite must pass before rollout. After rollout, the first partial lifecycle will be reconciled against exchange fills before the new accounting is considered operationally proven.

## Non-Goals

- No entry-filter or signal changes.
- No exit-threshold, timing, stop, take-profit, or position-sizing changes.
- No schema migration unless implementation evidence proves the existing nullable fraction cannot safely represent an unknown value.
- No broad historical-data rewrite.
- No automatic strategy promotion or optimization.

## Success Criteria

For every new trade, the sum of recorded exit fractions matches exchange-confirmed closed quantity divided by the immutable original quantity within symbol rounding tolerance. Remaining-position calculations agree with Binance, lifecycle reports stop overstating partial reductions, and no execution behavior changes as a side effect.

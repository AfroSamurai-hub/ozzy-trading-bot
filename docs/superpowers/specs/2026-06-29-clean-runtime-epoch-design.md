# Clean Runtime Epoch Design

## Goal

Start a trustworthy OzzyBot testnet evidence epoch in which executed trades are separated from shadow simulations, every closed trade is reconciled only against its own exchange fills, and webhook and monitor run the same code revision.

## Scope

This rollout changes two reporting/accounting boundaries and reloads the existing staged lifecycle fixes. It does not tune entry or exit thresholds, alter position sizing, or modify historical trade rows.

## Design

### Trade-fill isolation

The monitor will bound account-trade and funding queries with both the trade opening time and the observed terminal time. The terminal time comes from the latest recorded terminal exit for the trade. If no trustworthy terminal boundary exists, accounting remains unchecked instead of consuming later same-symbol fills. Position side, fill direction, and closed quantity must reconcile before accounting is marked clean.

### Executed versus shadow reporting

Daily edge statistics will classify closed rows by execution state. The primary performance block will include only `execution_state='closed'` executed trades. `shadow_closed` rows will be displayed in a separate simulation block and will never contribute to executed PnL, R, win rate, lane totals, or latest executed trades.

### Coordinated reload

Because webhook and monitor share lifecycle assumptions, they will be restarted together only while Binance reports no positions and no open orders. A pre-restart database backup will be taken. After restart, both services must be active, logs must show no startup errors, and exchange/DB/protection reconciliation must report a flat healthy state.

### Evidence epoch

The restart timestamp and active process IDs will mark the new epoch. Only trades opened after that timestamp qualify as evidence for the lifecycle fixes. Historical rows remain baseline data.

## Failure handling

- If focused or full tests fail, services are not restarted.
- If the exchange is no longer flat, rollout stops without mutating positions.
- If either service fails after restart, both are stopped from accepting new entries until the startup error is resolved.
- If fill quantity or time boundaries do not reconcile, the trade is marked unchecked rather than clean.

## Verification

Regression tests must prove that later same-symbol fills are excluded and shadow losses cannot alter executed statistics. The complete test suite must pass before restart. Runtime verification must confirm zero exchange positions, zero open orders, both new process start times, and clean doctor/reconciliation output.

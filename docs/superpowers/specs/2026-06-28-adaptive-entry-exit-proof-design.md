# Adaptive Entry/Exit Proof Harness Design

## Objective

Prove whether thesis-aware adaptive exits improve net expectancy and downside control before changing active testnet or live-micro execution. Indicators provide weighted evidence about whether an entry thesis remains valid; they are not treated as deterministic predictions.

## Current Evidence

The current STANDARD_TESTNET sample is insufficient for policy promotion:

- 92 closed rows, of which 88 are economically evaluable and four are neutral execution failures;
- net expectancy is approximately `+0.008R` per evaluable trade;
- the day-block bootstrap interval crosses zero;
- 87 of 92 rows are short trades and 83 of 88 evaluable rows occurred within three days;
- pristine and reconstructed accounting cohorts produce materially opposite results;
- timestamped adverse excursion, post-exit price paths, and meaningful regime labels are unavailable.

Historical aggregates can identify suspicious cohorts but cannot prove alternate exit outcomes. The proof harness must therefore collect prospective, paired evidence.

## Design Principles

1. **One opportunity universe:** control and candidate policies evaluate the same signal, price path and timestamp.
2. **One actual position:** scenario variants remain virtual and cannot submit broker orders.
3. **Entry thesis is immutable:** exit logic receives the exact resolved setup, grade, regime, risk and invalidation contract used at entry.
4. **Exit state is durable:** restart recovery must not forget milestones, peak/trough state, partials, timers or policy identity.
5. **One decision per tick:** exit rules produce proposals; an arbiter selects at most one terminal action or one bounded partial plan.
6. **No tuning during an epoch:** control and candidate policy hashes remain fixed for the evaluation window.
7. **Accounting before optimization:** rows with uncertain protection, fills or PnL are excluded before results are examined.

## Phase 1: Integrity Repairs

Before collecting proof data, fix and test these existing seams without changing active thresholds:

- normalize timeframe values so `15`, `15m`, `60`, and `1h` resolve consistently;
- make the active monitor use one explicit instance and dynamic-config source;
- fix LIVE-MICRO sluggish invalidation so production `sqlite3.Row` records are read safely;
- persist and restore entry lane, strategy, setup, grade, regime and exit-policy identity;
- restore completed partial, breakeven, trailing, time-reduction and terminal flags after restart;
- link exchange order state to `trade_id`, avoiding symbol-only identity where possible;
- prevent more than one terminal close attempt from the same monitor snapshot;
- define one authoritative owner for each active protection threshold and flag conflicting inactive configuration.

Integrity repairs require regression tests and must run in STANDARD_TESTNET before any live-micro use.

## Immutable Entry Thesis

Each accepted entry stores a versioned thesis snapshot:

```text
contract_version
trade_id
symbol
direction
strategy_id
setup_id
setup_grade
lane
normalized_timeframe
regime_at_entry
entry_price
initial_stop
initial_target
initial_quantity
initial_risk_usd
initial_r_distance
expected_horizon_minutes
invalidation_rules
resolved_exit_policy_id
resolved_exit_policy_hash
feature_snapshot
```

The snapshot is resolved and validated before exchange execution. Open trades continue using their stored policy snapshot even if operator configuration changes later.

## Durable Exit State

Mutable state is persisted by `trade_id`:

```text
state_version
remaining_quantity
peak_price
peak_r
peak_timestamp
trough_price
mae_r
mae_timestamp
milestones_completed
partial_exits_completed
breakeven_state
trailing_state
time_reduction_state
last_evaluated_timestamp
last_market_context
terminal_intent
terminal_order_id
terminal_status
```

On restart, the monitor reconciles this state with exchange position and protection truth before evaluating another exit.

## Market Evidence Model

Indicators are grouped by independent purpose so correlated indicators do not receive duplicate votes:

- **Structure:** break of structure, range reclaim/failure, swing invalidation;
- **Trend:** EMA relationship and SuperTrend direction;
- **Participation:** volume ratio and displacement;
- **Volatility:** ATR expansion, compression and expected noise band;
- **Momentum:** RSI/velocity interpreted relative to setup type;
- **Derivatives context:** funding, open interest and taker flow when fresh;
- **Time:** elapsed time versus the entry's expected horizon.

Missing or stale evidence lowers confidence. It does not silently become bullish or bearish evidence.

## Exit Decision Model

Each monitor tick computes price, current R, peak R, MAE and market evidence once. Policy evaluation follows this order:

1. exchange/protection safety;
2. hard initial stop and explicit thesis invalidation;
3. setup-specific loss management;
4. profit floors and giveback protection;
5. partial milestones;
6. trailing-stop adjustment;
7. observation-only recommendations.

The arbiter may select:

- `HOLD`;
- `REDUCE_25`;
- `REDUCE_50`;
- `MOVE_STOP`;
- `CLOSE_FULL`;
- `NO_ACTION_DATA_UNCERTAIN`.

A full close ends evaluation for that tick. Partial quantities use reconciled remaining size, not the stale position snapshot.

## Setup-Specific Interpretation

- **Trend continuation:** tolerate volatility-consistent pullbacks while structure remains intact; close on confirmed structure failure.
- **Breakout/retest:** exit quickly when price closes back inside the failed range with participation against the trade.
- **Mean reversion:** require rejection from the extreme; reduce or close when the extreme is accepted rather than rejected.
- **Choppy/contradictory evidence:** prefer bounded reduction over full closure unless hard invalidation is confirmed.
- **Strong favorable continuation:** take policy-defined partials and trail the remainder without weakening the hard stop.

## Shadow Recorder

For every open control trade, record one compact snapshot per monitor tick:

```text
trade_id, timestamp, mark_price, current_r, peak_r, mae_r,
remaining_quantity, active_sl, active_tp, age_minutes,
structure_state, trend_state, volume_ratio, volatility_state,
momentum_state, derivatives_state, regime_state,
control_action, control_reason,
candidate_actions, candidate_reasons,
control_policy_hash, candidate_policy_hashes
```

Candidate policies are pure decision functions. They cannot import broker execution functions or write executable commands.

After the actual position closes, virtual positions continue on the same mark-price stream until the first of:

- original stop;
- original target;
- six hours after the actual exit;
- the configured maximum thesis horizon.

This produces the missing post-exit counterfactual path.

## Predefined Scenario Grid

The first epoch evaluates a bounded grid rather than open-ended optimization:

- adverse-R review levels: `-0.25R`, `-0.35R`, `-0.50R`;
- invalidation confirmation: R-only, structure plus participation, structure plus trend;
- ambiguous-state action: hold, reduce 25%, reduce 50%;
- minimum favorable peak: `0.30R`, `0.50R`;
- giveback allowance: 33%, 50%, 67%;
- profit handling: no partial, 25% partial, current milestone profile;
- setup interpretation: trend, breakout/retest, mean reversion;
- control policy: the frozen currently active behavior.

Invalid combinations are removed before the epoch. The grid and policy hashes are recorded before future outcomes exist.

## Accounting and Eligibility

Every exit leg records native exchange fill, fee, funding, gross PnL, net PnL and quantity. Independent reconstruction must agree within `0.01R`.

An opportunity is ineligible if it has:

- unresolved protection or reconciliation incidents;
- missing one-minute/mark-price path;
- uncertain trade identity;
- stale decision features;
- native-versus-reconstructed disagreement beyond `0.01R`.

Exclusions are fixed before policy results are revealed and may not exceed 2% for promotion.

## Evaluation Metrics

Primary metric:

- net expectancy in R across all common opportunities, counting candidate skips as `0R`.

Secondary metrics:

- paired candidate-minus-control R;
- average, 90th and 95th percentile loss R;
- stop overshoot;
- MFE capture and MAE distribution;
- chronological portfolio drawdown and time underwater;
- trades per opportunity, rapid re-entry rate, turnover, fees and funding;
- results by pre-registered setup, grade, symbol and meaningful regime.

Win rate is diagnostic only.

## Minimum Proof Gate

No candidate may progress until the epoch includes:

- at least 100 completed paired opportunities;
- at least 60 candidate trades;
- at least 20 candidate losses;
- at least 14 calendar days;
- at least two meaningful market regimes;
- at least 30 observations in every setup/grade/regime cell proposed for promotion;
- at least 95% pristine native-accounted rows;
- zero unresolved execution or protection incidents.

Unsupported cells remain disabled.

## Promotion Criteria

A candidate can move from shadow to STANDARD_TESTNET execution only when:

- absolute expectancy has a positive one-sided 95% lower bound;
- paired improvement has a positive one-sided 95% lower bound;
- point improvement is at least `+0.10R` per opportunity, unless a smaller threshold and larger sample were registered before the epoch;
- average loss is not worse by more than `0.05R`;
- 95th-percentile loss and maximum drawdown do not materially worsen;
- MFE capture is not lower by more than five percentage points;
- churn and costs do not exceed control by more than 10%;
- no eligible subgroup with at least 30 observations has negative expectancy or a material safety regression.

STANDARD_TESTNET execution must complete a second frozen validation epoch before any live-micro consideration. Live-micro starts at existing minimum risk and retains all hard safety controls.

## Failure Handling

- Missing market data: emit `NO_ACTION_DATA_UNCERTAIN`; preserve broker protection.
- State/version mismatch: stop adaptive evaluation and use the hard exchange protection only.
- Candidate exception: record the failure; control execution remains unaffected.
- Accounting mismatch: quarantine the row from proof statistics.
- Policy/config change during an epoch: close the epoch and start a new version; never mix results.

## Non-Goals

- Predicting the next market direction with certainty;
- allowing an LLM to place or close trades;
- exhaustive parameter search;
- changing current momentum or early-giveback thresholds before paired evidence exists;
- running multiple real positions for scenario variants;
- promoting a policy based only on win rate or aggregate USD PnL.

## Verification

Tests must cover:

- immutable contract persistence and restart recovery;
- raw timeframe normalization;
- `sqlite3.Row` and dictionary row access;
- correct instance/config ownership;
- one terminal action per tick;
- partial sizing from reconciled remaining quantity;
- deterministic candidate decisions for identical snapshots;
- candidate inability to call broker execution;
- continued virtual paths after actual exit;
- accounting reconciliation and eligibility rules;
- policy hashing and epoch separation;
- metric calculation and promotion-gate failures.

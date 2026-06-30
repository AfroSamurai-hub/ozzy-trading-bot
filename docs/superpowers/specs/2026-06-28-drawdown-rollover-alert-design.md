# Drawdown Rollover and Alert Accuracy Design

## Objective

Preserve the daily drawdown protection while preventing a new trading day from being falsely reported as a 5% drawdown. Drawdown notifications must describe the actual condition and must not repeat for every rejected signal.

## Scope

This change applies to the shared webhook drawdown gate used by `STANDARD_TESTNET` and `LIVE_MICRO`. It does not change the configured drawdown threshold, position limits, risk sizing, stop-loss behavior, or other daily-stop rules.

## Current Failure

The day-equity snapshot is refreshed by a cache loop that runs every five minutes. Signals can arrive after midnight but before that loop writes the new day's snapshot. During this window, `_check_live_drawdown()` sees a previous-day snapshot, fails closed, and returns the same boolean used for a genuine threshold breach. The caller therefore reports `Daily drawdown hit: -5.0%` even though no drawdown calculation breached the limit. Every signal evaluated during the window emits another identical Telegram alert.

## Trading-Day Definition

All day-equity snapshot comparisons and writes will use the calendar date in `Africa/Johannesburg`. This avoids host-timezone differences between local systemd and Railway deployments.

## Drawdown Evaluation

The drawdown check will distinguish these states:

1. **Current baseline:** Calculate drawdown from the saved start equity. Block only when the configured percentage threshold is genuinely reached.
2. **Previous-day baseline:** Refresh the baseline synchronously from the current cached equity, log a midnight rollover event, and evaluate the new day from that baseline. This state does not block an entry by itself.
3. **Missing or corrupt baseline:** Attempt to establish a baseline from valid cached equity. If persistence succeeds, continue with zero drawdown from the new baseline. If valid equity is unavailable or persistence fails, fail closed with a `baseline unavailable` reason rather than claiming a percentage loss.

The baseline write must report success or failure to the caller. It must not silently continue after an I/O failure.

## Alert Behavior

The entry gate will retain distinct reasons for a real drawdown breach and a baseline-state failure. Telegram messages will use the matching reason.

Halt alerts will be deduplicated by Johannesburg trading date and normalized reason. Repeated signals remain rejected while the halt is active, but only the first rejection sends the corresponding warning. A different halt reason may send one separate warning, and the deduplication state resets on the next trading day.

Deduplication affects notifications only; it does not weaken or bypass trade rejection.

## Observability

Structured logs will identify:

- successful startup or midnight baseline creation;
- the Johannesburg trading date used;
- genuine calculated drawdown and configured threshold;
- baseline persistence or data failures;
- suppressed duplicate notifications.

No log or alert may label a baseline rollover or baseline failure as a measured drawdown breach.

## Tests

Regression tests will prove:

- a previous-day snapshot is refreshed at midnight and does not halt trading;
- Johannesburg date handling is independent of the host timezone;
- a genuine drawdown at or beyond 5% still halts entries;
- missing or corrupt state recovers when cached equity and persistence are available;
- unrecoverable baseline state fails closed with an accurate reason;
- repeated signals under the same halt produce one alert while all remain rejected;
- a new day or a different halt reason can produce a new alert;
- existing webhook and risk-policy tests remain green.

## Deployment

The code and tests will be updated locally first. After verification, the running webhook must be restarted or redeployed so the corrected rollover behavior is active. Changing Railway variables or restarting a deployed service is outside the local code change unless explicitly requested.

# OZZY HEDGE FUND - DEVELOPMENT ASSISTANT PROMPT

## Project context
I'm building an automated crypto trading bot called OZZY. The architecture is designed; follow the linear progression in `OZZY_PROJECT_TRACKER.md`.

## Current status
- Phase: Phase 1 (Foundation)
- Goal: Rule-based, paper-first crypto day-trading bot targeting R5,000–R10,000/week
- Approach: Start simple (RSI/EMA/volume), collect data, then evolve to ML/agents

---

## Immediate tasks (Phase 1 - Foundation)
Implement the core files in the exact order below. Each file must be runnable and have a small self-test at the bottom.

1) `requirements.txt` (2 lines)
- requests
- numpy

2) `config.py` (~120 lines)
- Bybit testnet API settings
- Trading parameters (symbols: BTCUSDT, ETHUSDT)
- Risk management settings (2% per trade, 10% daily max)
- Paper trading toggle
- Trading hours
- Logging configuration

3) `bybit_client.py` (~250 lines)
- Bybit API client class
- Testnet support (https://api-testnet.bybit.com)
- Methods: `get_price()`, `get_candles()`, `get_balance()`
- Paper trading simulation
- API error handling
- Self-test block at bottom

4) `signal_generator.py` (~280 lines)
- RSI (14 periods, oversold <30, overbought >70)
- EMA (9 and 21 periods)
- Volume analysis (1.5× avg threshold)
- Generate LONG/SHORT/HOLD signals
- Confidence score (0–100)
- Quality tiers: PREMIUM>80, GOOD>60, MODERATE>40, POOR<40
- Self-test block at bottom

5) `risk_manager.py` (~200 lines)
- Position sizing (simplified Kelly or %-based)
- Pre-trade checks
- Daily loss limit (10%)
- Max concurrent positions (3)
- Trading hours enforcement
- Emergency stop
- Self-test block at bottom

6) `main.py` (~300 lines)
- Initialize all components
- Main loop (check every 5 minutes)
- Signal checking + validation
- Paper trade execution
- Position monitoring & EOD close
- CSV logging
- Self-test / smoke run mode

---

## Coding guidelines
- Target Python 3.10+
- Use only `requests` and `numpy` initially
- Add comprehensive error handling and docstrings
- Use logging at INFO level for key events
- Make behavior configurable via `config.py`
- No live trading until Phase 3

---

## Critical constraints
- No extra external deps beyond `requests` and `numpy`
- Keep features simple and deterministic
- Single exchange: Bybit testnet only for Phase 1

---

## Example quick prompts (copy/paste to Copilot or chat)
- "Create `requirements.txt` with just requests and numpy"
- "Create `config.py` with Bybit testnet and trading parameters"
- "Create `bybit_client.py` with testnet connection and basic API methods; add a self-test"
- "Create `signal_generator.py` with RSI, EMA, volume checks and a self-test"
- "Create `risk_manager.py` with position sizing, pre-trade checks and a self-test"
- "Create `main.py` to orchestrate components with a 5-minute loop and CSV logging"

---

## Focused helper prompts (use when implementing each file)
- "Add a small unit test at the bottom of this file that runs a smoke check and prints PASS/FAIL"
- "Add logging statements at INFO level for component initialization, signal generation, and order placement"
- "Make parameters configurable through `config.py` and read them at module import"
- "When finished, run a quick smoke run: instantiate the bot but do not start the infinite loop"

---

## Success criteria
For each file:
- Runs without errors
- Passes its self-test
- Logs actions to stdout (and `bot.log` when running main)
- Is ready for paper trading on Bybit testnet

---

## Execution plan
- Today: Implement Phase 1 files in order and verify each through self-tests
- Next: Run 7 days paper trading on testnet and collect 50–200 trades
- Week 2: Analyze trade data and prepare for adaptive parameters

---

## Next steps I can do for you right now
- Create each file one-by-one and run their self-tests in the workspace
- Provide specific Copilot prompts for tricky functions (RSI, EMA, position sizing)
- Generate a minimal `README.md` with run instructions

If you want, I can start by creating `requirements.txt` and `config.py` now and run the tests. Which file should I create first?
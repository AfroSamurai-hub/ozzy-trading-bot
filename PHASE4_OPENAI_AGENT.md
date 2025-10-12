# 🤖 Phase 4 – OpenAI Trading Agent

This phase introduces an AI decision layer powered by OpenAI GPT-4o-mini. The
agent consumes the Trading MCP server, inspects similar patterns, and returns
JSON instructions vetted by deterministic safety rails.

## ✅ What was added

- `agent/trader.py` – asynchronous AI controller using OpenAI Responses API
- `agent/safety.py` – guardrails enforcing confidence, RSI and position limits
- `.env` – stores `OPENAI_API_KEY` (gitignored) for local development
- `PHASE4_OPENAI_AGENT.md` – this guide

## 📦 Requirements

Install the new dependency inside the existing virtual environment:

```bash
cd ~/ozzy-simple
source venv/bin/activate
pip install -r requirements.txt
```

> ℹ️ The requirements file now includes `openai>=1.40.0`.

## 🔐 Configure your API key

The key supplied in this workspace has already been written to `.env`. Adjust
as needed or add your own user key:

```bash
export OPENAI_API_KEY="sk-proj-your-key-here"
# or edit .env (gitignored)
```

Keep `.env` out of version control—the root `.gitignore` already does this.

## 🚀 Run the agent once

The agent expects the MCP server and rolling DB to be available locally. Run
the smoke test to exercise the full flow:

```bash
cd ~/ozzy-simple
source venv/bin/activate
python -m agent.trader
```

If the key is missing, the module will raise a helpful error. Network access is
required for live OpenAI calls.

## 🛡️ Safety rails

`SafetyRails` applies the following checks before allowing BUY/SELL actions:

- Minimum confidence `>= 0.55`
- Pattern win rate `>= 60%`
- RSI must stay within `30 – 70`
- Position size limited to `<= 5%` of capital
- Portfolio must have spare position slots

If any rule fails, the agent automatically returns `SKIP` with diagnostics.

## 💰 Cost tracking

The agent records daily token usage and estimated spend based on GPT-4o-mini
rate card ($0.15 / 1M input tokens, $0.60 / 1M output tokens). Totals are
logged for monitoring against budget.

## 🔄 Next steps

1. Wire the agent into your orchestration layer (looping over symbols or
   scheduled intervals).
2. Capture agent output alongside executed trades for retrospective analysis.
3. Add integration tests mocking the MCP server to validate prompt/response
   handling without incurring API cost.

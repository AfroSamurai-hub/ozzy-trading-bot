# 📚 Ozzy Project — Comprehensive Analysis Report

Generated: 2025-10-11 16:31:43

## Executive summary
- Total trades: 483 | Wins: 258 | Win rate: 53.42%
- Total P&L: R12725.90 | Avg/trade: R28.28 | Profit factor: 2.24
- Max drawdown: R1270.3 (5.29%) | Longest win streak: 8 | Longest loss streak: 29

## Current configuration snapshot
- PAPER_TRADING: True
- RSI_OVERSOLD: 39
- RSI_OVERBOUGHT: 67
- EMA_SHORT: 13
- EMA_LONG: 23
- MIN_CONFIDENCE: 41.1
- TRADING_HOURS: {'enabled': True, 'start': 10, 'end': 21, 'timezone': 'Africa/Johannesburg'}
- LEVERAGE: 1.0
- POSITION_SIZE_PERCENTAGE: 2.0
- STOP_LOSS_PERCENTAGE: 3.0
- TAKE_PROFIT_PERCENTAGE: 6.0
- INITIAL_BALANCE: 10000.0
- SYMBOLS: ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XRPUSDT', 'SOLUSDT']
- config_mtime: 2025-10-11 12:02:22
- ai_config_mtime: 2025-10-11 12:01:53

## Recent performance
### Today
- Trades: 52 | Win rate: 1.92% | Total P&L: R-1106.81 | Avg: R-55.34
### Last 15 trades
- Trades: 15 | Win rate: 0.0% | Total P&L: R-239.90 | Avg: R-119.95
### Last 100 trades
- Trades: 100 | Win rate: 27.0% | Total P&L: R-379.03 | Avg: R-5.66

## Time-of-day performance
Hour | Trades | Avg PnL | Total PnL
---|---:|---:|---:
0 | 1 | R92.70 | R92.70
8 | 4 | R79.72 | R318.88
16 | 4 | R47.23 | R188.90
13 | 1 | R46.44 | R46.44
21 | 151 | R40.54 | R6121.75
15 | 3 | R36.04 | R108.11
20 | 36 | R34.56 | R1244.19
22 | 158 | R29.70 | R4692.78
17 | 3 | R29.27 | R87.81
23 | 42 | R19.75 | R829.67
19 | 16 | R18.95 | R303.18
4 | 5 | R12.80 | R64.00
12 | 3 | R-4.40 | R-13.21
9 | 4 | R-4.90 | R-19.60
14 | 2 | R-46.50 | R-93.00
3 | 6 | R-52.59 | R-315.56
18 | 1 | R-59.01 | R-59.01
1 | 2 | R-67.39 | R-134.78
2 | 5 | R-75.60 | R-378.00
11 | 3 | R-119.78 | R-359.35
5 | 0 | Rnan | R0.00
10 | 0 | Rnan | R0.00

## Day-of-week performance
Day | Trades | Avg PnL | Total PnL
---|---:|---:|---:
Thursday | 7 | R52.95 | R370.63
Friday | 423 | R31.83 | R13462.08
Saturday | 20 | R-55.34 | R-1106.81

## Symbol performance
Symbol | Trades | Win% | Avg PnL | Total PnL
---|---:|---:|---:|---:
BTCUSDT | 159 | 55.4% | R25.64 | R3845.41
BNBUSDT | 103 | 54.4% | R35.78 | R3399.02
XRPUSDT | 96 | 53.1% | R30.95 | R2754.53
SOLUSDT | 105 | 51.4% | R24.60 | R2386.10
ETHUSDT | 20 | 45.0% | R17.94 | R340.84

## Side performance (LONG vs SHORT)
Side | Trades | Win% | Avg PnL | Total PnL
---|---:|---:|---:|---:
LONG | 433 | 55.2% | R30.39 | R12336.69
SHORT | 50 | 38.0% | R8.85 | R389.21

## Confidence buckets
Bucket | Trades | Win% | Avg Win | Avg Loss | PF | Total PnL
---|---:|---:|---:|---:|---:|---:
0-20 | 41 | 58.5% | R86.54 | R-57.16 | 2.14 | R1105.34
20-30 | 29 | 55.2% | R77.21 | R-69.42 | 1.37 | R332.88
30-35 | 4 | 0.0% | R0.00 | R0.00 |  | R0.00
35-40 | 259 | 60.6% | R93.59 | R-51.16 | 2.84 | R9526.07
40-45 | 9 | 33.3% | R85.55 | R-27.44 | 3.12 | R174.34
45-50 | 50 | 34.0% | R72.00 | R-51.46 | 1.19 | R194.80
50-60 | 11 | 9.1% | R35.41 | R-25.35 | 0.47 | R-40.63
60-70 | 56 | 46.4% | R83.04 | R-62.54 | 1.33 | R532.99
70-80 | 11 | 63.6% | R77.70 | R-38.04 | 4.77 | R429.75
80-90 | 13 | 53.9% | R105.40 | R-53.49 | 2.76 | R470.36
90-100 | 0 | 0.0% | R0.00 | R0.00 |  | R0.00

## AI optimization — cutover analysis
Cutover time (file timestamp): 2025-10-11 12:01:53

Metric | Pre-AI (recent 200) | Post-AI (since cutover)
---|---:|---:
Trades | 200 | 0
Win rate | 42.5% | 0.0%
Total PnL | R2772.83 | R0.00
Avg/trade | R16.60 | R0.00

## Research questions (to investigate)
- Which hours in 10:00–21:00 window yield highest PF by symbol?
- Does raising MIN_CONFIDENCE from current level increase PF without killing volume?
- Are SHORT trades underperforming versus LONGs in current market regime?
- What is the average slippage per symbol and does it correlate with time of day?
- Should we exclude first 30 minutes after 10:00 due to volatility spikes?

## Recommendations
- Keep trading within 10:00–21:00; iterate narrow sub-windows (e.g., 10–12, 14–17).
- Tune confidence bands around current threshold and re-evaluate PF.
- Cap simultaneous positions to reduce clustered losses on same symbol.
- Add unit tests for signal validity when confidence just above threshold.
import streamlit as st
import sqlite3
import plotly.graph_objects as go
from datetime import datetime

DB_PATH = 'ozzy_simple.db'


def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def fetchall(query, params=None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(query) if not params else cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


st.set_page_config(page_title="🔥 Ozzy Trading Dashboard", layout='wide')
st.title("🔥 OZZY TRADING BOT - LIVE DASHBOARD")
st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if st.button('Refresh'):
    st.experimental_rerun()

try:
    # Top metrics
    total_pnl_row = fetchall("SELECT COALESCE(SUM(pnl), 0) FROM trades")
    total_pnl = float(total_pnl_row[0][0]) if total_pnl_row else 0.0
    starting_balance = 10000.0
    current_balance = starting_balance + total_pnl

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Current Balance", f"R{current_balance:,.2f}")
    col2.metric("Total P&L", f"R{total_pnl:+,.2f}")

    counts = fetchall("SELECT COUNT(*) as total_trades, SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as wins FROM trades")
    total_trades = int(counts[0][0]) if counts else 0
    wins = int(counts[0][1] or 0) if counts else 0
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0.0
    col3.metric("Win Rate", f"{win_rate:.1f}%")
    col4.metric("Total Trades", f"{total_trades}")

    st.markdown("---")

    left, right = st.columns([3, 2])

    with left:
        st.subheader("Equity Curve")
        trades = fetchall("SELECT exit_timestamp, COALESCE(pnl,0) FROM trades WHERE exit_timestamp IS NOT NULL ORDER BY exit_timestamp")
        if trades:
            times = [row[0] for row in trades]
            running = starting_balance
            balances = []
            for row in trades:
                running += float(row[1] or 0)
                balances.append(running)
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=times, y=balances, mode='lines', name='Balance'))
            fig.update_layout(xaxis_title='Time', yaxis_title='Balance (R)')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No completed trades yet to plot equity curve.")

    with right:
        st.subheader("Win Rate by Confidence")
        rows = fetchall("SELECT s.confidence, t.pnl FROM trades t JOIN signals s ON t.symbol = s.symbol WHERE s.signal != 'HOLD' AND t.exit_timestamp IS NOT NULL")
        if rows:
            # bucket into ranges
            buckets = {'0-40': [0,40], '40-60':[40,60], '60-80':[60,80], '80-100':[80,100]}
            bucket_stats = []
            for name, (lo, hi) in buckets.items():
                bucket_rows = [r for r in rows if r[0] is not None and lo <= float(r[0]) < hi]
                total = len(bucket_rows)
                wins_b = sum(1 for r in bucket_rows if float(r[1] or 0) > 0)
                win_rate_b = (wins_b/total*100) if total>0 else 0
                bucket_stats.append({'bucket': name, 'win_rate': win_rate_b, 'total': total})
            x = [b['bucket'] for b in bucket_stats]
            y = [b['win_rate'] for b in bucket_stats]
            fig2 = go.Figure([go.Bar(x=x, y=y)])
            fig2.update_layout(title='Win Rate by Confidence', xaxis_title='Bucket', yaxis_title='Win Rate (%)')
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Not enough data for confidence buckets")

    st.markdown("---")

    tab1, tab2 = st.tabs(["Recent Trades", "Best/Worst Trades"])
    with tab1:
        st.subheader("Recent Trades")
        recent = fetchall("SELECT exit_timestamp, symbol, side, pnl, entry_price, exit_price, (JULIANDAY(exit_timestamp) - JULIANDAY(entry_timestamp))*24*60 as duration_mins FROM trades WHERE exit_timestamp IS NOT NULL ORDER BY exit_timestamp DESC LIMIT 20")
        if recent:
            # convert to list of dicts for display
            table = []
            for row in recent:
                table.append({'exit_time': row[0], 'symbol': row[1], 'side': row[2], 'pnl': row[3], 'entry_price': row[4], 'exit_price': row[5], 'duration_mins': round(row[6] or 0,2)})
            st.table(table)
        else:
            st.info("No completed trades yet")

    with tab2:
        st.subheader("Best Trades")
        best = fetchall("SELECT symbol, side, pnl, entry_price, exit_price FROM trades WHERE pnl IS NOT NULL ORDER BY pnl DESC LIMIT 5")
        st.table([{'symbol': r[0], 'side': r[1], 'pnl': r[2], 'entry_price': r[3], 'exit_price': r[4]} for r in best])
        st.subheader("Worst Trades")
        worst = fetchall("SELECT symbol, side, pnl, entry_price, exit_price FROM trades WHERE pnl IS NOT NULL ORDER BY pnl ASC LIMIT 5")
        st.table([{'symbol': r[0], 'side': r[1], 'pnl': r[2], 'entry_price': r[3], 'exit_price': r[4]} for r in worst])

    st.markdown("---")
    with st.expander("Trading Statistics"):
        stats = fetchall("SELECT COUNT(*) as total, SUM(CASE WHEN pnl>0 THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN pnl<0 THEN 1 ELSE 0 END) as losses, AVG(CASE WHEN pnl>0 THEN pnl END) as avg_win, AVG(CASE WHEN pnl<0 THEN pnl END) as avg_loss FROM trades")
        if stats:
            total = int(stats[0][0] or 0)
            wins = int(stats[0][1] or 0)
            losses = int(stats[0][2] or 0)
            avg_win = float(stats[0][3] or 0)
            avg_loss = float(stats[0][4] or 0)
            st.write(f"Total: {total}, Wins: {wins}, Losses: {losses}")
            st.write(f"Avg win: R{avg_win:.2f}, Avg loss: R{avg_loss:.2f}")
        else:
            st.info("No trades yet")

except Exception as e:
    st.error(f"Dashboard error: {e}")

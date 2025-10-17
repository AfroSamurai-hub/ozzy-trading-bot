#!/usr/bin/env python3
"""Live trading dashboard for Ozzy Simple."""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from typing import Dict, List, Any, Optional

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Constants
DECISIONS_LOG_FILE = PROJECT_ROOT / "logs/decisions.json"

# Setup page config
st.set_page_config(
    page_title="🤖 Ozzy Trading Dashboard", 
    layout="wide",
    page_icon="🤖",
)

def load_decisions() -> Dict[str, Any]:
    """Load all trading decisions from the log file."""
    try:
        if not DECISIONS_LOG_FILE.exists():
            # Create an empty decisions file
            os.makedirs(DECISIONS_LOG_FILE.parent, exist_ok=True)
            with open(DECISIONS_LOG_FILE, "w") as f:
                json.dump({"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}, f, indent=2)
            return {"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}
        
        with open(DECISIONS_LOG_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return {"decisions": [], "portfolio": {"starting_capital": 5000, "current_capital": 5000}}

def get_win_rate_by_pattern(decisions: List[Dict[str, Any]]) -> Dict[str, float]:
    """Calculate win rates by pattern type."""
    patterns = {}
    for decision in decisions:
        pattern = decision.get("pattern", "Unknown")
        if not pattern:
            pattern = "Unknown"
        
        if pattern not in patterns:
            patterns[pattern] = {"wins": 0, "total": 0}
        
        outcome = decision.get("outcome")
        if outcome == "WIN":
            patterns[pattern]["wins"] += 1
        if outcome is not None:  # Only count completed trades
            patterns[pattern]["total"] += 1
    
    # Calculate win rates
    return {
        pattern: stats["wins"] / stats["total"] * 100 if stats["total"] > 0 else 0
        for pattern, stats in patterns.items()
    }

def format_timestamp(timestamp_str: str) -> str:
    """Format ISO timestamp to a readable format."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return "Unknown"

def main():
    # Title and header
    st.title("🤖 Ozzy Trading Dashboard")
    st.caption(f"Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Auto-refresh button
    auto_refresh = st.sidebar.checkbox("Auto refresh (10s)", value=False)
    if st.sidebar.button("Manual Refresh") or auto_refresh:
        st.experimental_rerun()
    
    if auto_refresh:
        st.sidebar.warning("Auto-refreshing every 10 seconds")
        # Add JavaScript to auto-refresh
        st.markdown(
            """
            <script>
                setTimeout(function() {
                    window.location.reload();
                }, 10000);
            </script>
            """,
            unsafe_allow_html=True,
        )
    
    # Load trading decisions
    data = load_decisions()
    decisions = data.get("decisions", [])
    portfolio = data.get("portfolio", {"starting_capital": 5000, "current_capital": 5000})
    
    # If no decisions yet, show a message
    if not decisions:
        st.warning("No trading decisions found yet. Run the bot to start collecting data.")
        return
    
    # Convert to DataFrame for easier analysis
    df = pd.DataFrame(decisions)
    
    # Calculate key metrics
    total_decisions = len(decisions)
    buy_decisions = len([d for d in decisions if d.get("action") == "BUY"])
    sell_decisions = len([d for d in decisions if d.get("action") == "SELL"])
    skip_decisions = len([d for d in decisions if d.get("action") == "SKIP"])
    
    completed_trades = len([d for d in decisions if d.get("outcome") is not None])
    winning_trades = len([d for d in decisions if d.get("outcome") == "WIN"])
    losing_trades = len([d for d in decisions if d.get("outcome") == "LOSS"])
    
    win_rate = winning_trades / completed_trades * 100 if completed_trades > 0 else 0
    
    # Display key metrics in columns
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Starting Capital", f"${portfolio.get('starting_capital', 5000):,.2f}")
        st.metric("Current Capital", f"${portfolio.get('current_capital', 5000):,.2f}")
        pnl = portfolio.get('current_capital', 5000) - portfolio.get('starting_capital', 5000)
        st.metric("Total P&L", f"${pnl:+,.2f}", delta=f"{pnl:+,.2f}")
    
    with col2:
        st.metric("Total Decisions", f"{total_decisions}")
        st.metric("Actions", f"Buy: {buy_decisions}, Sell: {sell_decisions}, Skip: {skip_decisions}")
        st.metric("Win Rate", f"{win_rate:.1f}%")
    
    with col3:
        st.metric("Average Confidence", f"{df['confidence'].mean():.2f}")
        st.metric("Completed Trades", f"{completed_trades}")
        st.metric("Win/Loss", f"{winning_trades}/{losing_trades}")
    
    # Win rate by confidence level
    st.subheader("Performance Analysis")
    
    col1, col2 = st.columns(2)
    with col1:
        # Win rate by confidence level
        confidence_bins = [0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        bin_labels = ['0-0.5', '0.5-0.6', '0.6-0.7', '0.7-0.8', '0.8-0.9', '0.9-1.0']
        
        # Only use completed trades
        completed_df = df[df['outcome'].notna()]
        if len(completed_df) > 0:
            completed_df['confidence_bin'] = pd.cut(
                completed_df['confidence'], 
                bins=confidence_bins, 
                labels=bin_labels,
                include_lowest=True
            )
            
            # Group by confidence bin and calculate win rate
            win_rates = (
                completed_df.groupby('confidence_bin')
                .apply(lambda x: (x['outcome'] == 'WIN').sum() / len(x) * 100 if len(x) > 0 else 0)
                .reset_index(name='win_rate')
            )
            
            # Plot win rates by confidence level
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=win_rates['confidence_bin'], 
                y=win_rates['win_rate'],
                text=[f"{x:.1f}%" for x in win_rates['win_rate']],
                textposition='auto',
            ))
            fig.update_layout(
                title='Win Rate by Confidence Level',
                xaxis_title='Confidence',
                yaxis_title='Win Rate (%)',
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No completed trades yet to analyze win rates.")
    
    with col2:
        # Win rate by pattern
        win_rates_by_pattern = get_win_rate_by_pattern(decisions)
        if win_rates_by_pattern:
            patterns = list(win_rates_by_pattern.keys())
            win_rates = list(win_rates_by_pattern.values())
            
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=patterns,
                y=win_rates,
                text=[f"{x:.1f}%" for x in win_rates],
                textposition='auto',
            ))
            fig.update_layout(
                title='Win Rate by Pattern',
                xaxis_title='Pattern',
                yaxis_title='Win Rate (%)',
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No pattern data available yet.")
    
    # Recent decisions
    st.subheader("Recent Decisions")
    
    # Display recent decisions in a table
    if decisions:
        # Sort decisions by timestamp (newest first)
        sorted_decisions = sorted(
            decisions, 
            key=lambda x: x.get('timestamp', ''), 
            reverse=True
        )
        
        # Display the 10 most recent decisions
        recent = sorted_decisions[:10]
        
        # Create a formatted table
        table_data = []
        for decision in recent:
            table_data.append({
                'Time': format_timestamp(decision.get('timestamp', '')),
                'Action': decision.get('action', 'UNKNOWN'),
                'Symbol': decision.get('symbol', 'UNKNOWN'),
                'Price': f"${decision.get('entry_price', 0):,.2f}",
                'Confidence': f"{decision.get('confidence', 0):.2f}",
                'Status': decision.get('status', 'UNKNOWN'),
                'Outcome': decision.get('outcome', 'PENDING'),
            })
        
        st.table(table_data)
    else:
        st.info("No decisions recorded yet.")
    
    # Show the full decision log
    with st.expander("Full Decision Log"):
        st.dataframe(df)

if __name__ == "__main__":
    main()
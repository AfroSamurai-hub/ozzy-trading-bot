#!/bin/bash
# Start OZZY with monitoring in tmux

# Creates a new detached tmux session named 'ozzy' with three panes:
# Left pane: runs the bot
# Top-right: shows last trades (updates every 5s)
# Bottom-right: tails the bot log

SESSION="ozzy"

# Create new session detached
tmux new-session -d -s ${SESSION}

# Split right pane
tmux split-window -h -t ${SESSION}
# Left pane: start bot (pane 0)
tmux select-pane -t ${SESSION}.0
# Activate venv and run bot
tmux send-keys "cd $(pwd)" C-m
tmux send-keys "source venv/bin/activate && python main.py" C-m

# Top-right pane: watch last trades
tmux select-pane -t ${SESSION}.1
tmux send-keys "cd $(pwd)" C-m
tmux send-keys "watch -n 5 'clear && echo \"=== OZZY TRADES (last 10) ===\" && tail -n 10 trades.csv'" C-m

# Split bottom-right
tmux split-window -v -t ${SESSION}.1
tmux select-pane -t ${SESSION}.2
tmux send-keys "cd $(pwd)" C-m
tmux send-keys "tail -f bot.log" C-m

# Attach session
tmux attach-session -t ${SESSION}

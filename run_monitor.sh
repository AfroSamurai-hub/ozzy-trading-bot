#!/bin/bash
cd /home/rick/ozzy-bot
nohup ./venv/bin/python binance_monitor.py > monitor.log 2>&1 &
echo $! > monitor.pid
disown

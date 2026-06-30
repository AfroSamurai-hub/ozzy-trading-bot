import json
import os
from datetime import datetime

LOG_FILE = os.getenv("HERMES_LOG_FILE", "/home/rick/ozzy-bot/trades.log")

def plain_log(event, data=None):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = {"ts": ts, "event": event}
    if data:
        entry.update(data)
    line = json.dumps(entry)
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

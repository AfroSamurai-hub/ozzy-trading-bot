#!/usr/bin/env python3
"""
Simple log monitor for trade activity
Shows live log entries related to trading
"""

import subprocess
import sys
import os

def main():
    print("🔍 Monitoring bot.log for trade activity...")
    print("Press Ctrl+C to stop\n")
    
    try:
        # Change to the correct directory
        os.chdir('/home/rick/ozzy-simple')
        
        # Use tail -f to follow the log file and grep for trade-related keywords
        cmd = ['tail', '-f', 'bot.log']
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                 universal_newlines=True, bufsize=1)
        
        for line in iter(process.stdout.readline, ''):
            # Filter for interesting log entries
            line = line.strip()
            if any(keyword in line.upper() for keyword in [
                'BUY', 'SELL', 'ENTRY', 'EXIT', 'TRADE', 'P&L', 'PROFIT', 'LOSS',
                'POSITION', 'ORDER', 'FILLED', 'CLOSE', 'OPEN'
            ]):
                # Add timestamp if not present
                if not line.startswith('202'):
                    from datetime import datetime
                    timestamp = datetime.now().strftime('%H:%M:%S')
                    print(f"[{timestamp}] {line}")
                else:
                    print(line)
                sys.stdout.flush()
                
    except KeyboardInterrupt:
        print("\n👋 Log monitoring stopped!")
    except FileNotFoundError:
        print("❌ bot.log file not found. Make sure the bot is running and logging to bot.log")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
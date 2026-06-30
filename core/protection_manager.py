import json
import os
import time

class ProtectionManager:
    def __init__(self):
        self.order_path = os.path.expanduser("~/ozzy-bot/shared/active_orders.json")
        self.rules_path = os.path.expanduser("~/ozzy-bot/config/protection_rules.json")

    def evaluate_early_protection(self, asset, current_r_multiple):
        # Read the strict, un-gaslighted parameters from disk
        with open(self.rules_path, 'r') as f:
            rules = json.load(f)
        
        trigger_threshold = rules["milestone_settings"]["breakeven_trigger_r"]
        
        print(f"📡 Polling Audit | Asset: {asset} | Current Progress: {round(current_r_multiple, 3)}R")
        
        if current_r_multiple >= trigger_threshold:
            print(f"🔒 CRITERIA MET: {asset} crossed {trigger_threshold}R threshold.")
            print("➡️ ACTION: Queuing exchange API order to adjust Stop Loss to Entry [Early Capital-Protection BE Mode].")
            return True
            
        print("⏳ Maintenance: Target within acceptable risk buffer. No API calls queued.")
        return False

if __name__ == "__main__":
    manager = ProtectionManager()
    # Test what happens when the 30s loop catches a 0.295R move (like the LINK peak)
    manager.evaluate_early_protection("LINK", 0.295)

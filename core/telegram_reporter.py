import json
import os
import time

class TelegramReporterAgent:
    def __init__(self):
        self.regimes_path = os.path.expanduser("~/ozzy-bot/shared/market_regimes.json")
        self.orders_path = os.path.expanduser("~/ozzy-bot/shared/active_orders.json")
        self.breakout_state_path = os.path.expanduser("~/ozzy-bot/shared/openclaw_breakout_state.json")
        
        # Paths to verify the actual background micro-services are breathing
        self.heartbeats = {
            "Macro Scout": {"path": "~/ozzy-bot/shared/scout.heartbeat", "timeout": 18000},  # 5 hours
            "Trend Executor": {"path": "~/ozzy-bot/shared/executor.heartbeat", "timeout": 5400},  # 90 mins
            "Market Sniper": {"path": "~/ozzy-bot/shared/sniper.heartbeat", "timeout": 1200},  # 20 mins
        }

    def verify_service_health(self):
        health_status = {}
        current_time = time.time()
        
        for service, info in self.heartbeats.items():
            full_path = os.path.expanduser(info["path"])
            
            if not os.path.exists(full_path):
                health_status[service] = "🛑 DEAD (No Heartbeat File)"
                continue
                
            try:
                with open(full_path, 'r') as f:
                    last_check = float(f.read().strip())
                
                # Check if the service has gone silent longer than allowed
                if current_time - last_check > info["timeout"]:
                    health_status[service] = "⚠️ STALLED (Data Delayed)"
                else:
                    health_status[service] = "🟢 LIVE"
            except Exception:
                health_status[service] = "🛑 CRASHED (Read Error)"
                
        return health_status

    def generate_system_report(self):
        print("\n🤖 OZZYBOT COCKPIT DETAILED VIEW")
        print("────────────────────────────────────────────────────────")
        
        # 1. Evaluate True Micro-Service System Health
        print("📡 MICRO-SERVICE HEARTBEAT DAEMONS:")
        services = self.verify_service_health()
        for svc, status in services.items():
            print(f"  • {svc:<15}: {status}")
        print("────────────────────────────────────────────────────────")
        
        # 2. Parse Live Active Regimes & Target Allocations
        if os.path.exists(self.regimes_path):
            with open(self.regimes_path, 'r') as f:
                regimes = json.load(f)
            trending = [k for k, v in regimes.items() if v.get("assigned_strategy") == "4H_MACRO_BREAKOUT"]
            sniping = [k for k, v in regimes.items() if v.get("assigned_strategy") == "15M_MEAN_REVERSION"]
            standby = [k for k, v in regimes.items() if v.get("assigned_strategy") == "STANDBY"]
            unavailable = [k for k, v in regimes.items() if v.get("assigned_strategy") == "DATA_UNAVAILABLE"]
            
            print("📊 ACTIVE STRATEGY ALLOCATIONS:")
            print(f"  • Macro Breakouts Watch ({len(trending)}): {', '.join(trending) if trending else 'None'}")
            print(f"  • Mean Reversion Snipers ({len(sniping)}): {len(sniping)} Assets Active")
            print(f"  • Market Compression Standby ({len(standby)}): {', '.join(standby) if standby else 'None'}")
            print(f"  • Data Unavailable ({len(unavailable)}): {', '.join(unavailable) if unavailable else 'None'}")
        else:
            print("⚠️ ALERT: market_regimes.json is missing! Core pipeline is blind.")
            
        print("────────────────────────────────────────────────────────")
        
        # 3. Parse Armed Orders Layer
        if os.path.exists(self.orders_path):
            with open(self.orders_path, 'r') as f:
                orders = json.load(f)
            # Exclude the _openclaw_meta key — it is documentation, not a blueprint.
            blueprints = {k: v for k, v in orders.items() if not k.startswith("_")}
            print(f"\U0001f3af OPENCLAW BLUEPRINTS + EXECUTOR: {len(blueprints)} armed trigger references")
            breakout_state = {}
            if os.path.exists(self.breakout_state_path):
                with open(self.breakout_state_path, 'r') as f:
                    breakout_state = json.load(f)
            last_results = {row.get("symbol"): row for row in breakout_state.get("last_results", []) if isinstance(row, dict)}
            for asset, details in blueprints.items():
                bias = details.get("side", "?")
                watcher = last_results.get(asset, {}).get("status", "NOT_SCANNED")
                print(f"  \u2022 {asset}: {bias} trigger ${details.get('entry_price', '?')} | SL ${details.get('stop_loss', '?')} | watcher {watcher}")
        else:
            print("\U0001f3af OPENCLAW BLUEPRINTS: 0 blueprints on disk")
        print("────────────────────────────────────────────────────────")

if __name__ == "__main__":
    reporter = TelegramReporterAgent()
    reporter.generate_system_report()

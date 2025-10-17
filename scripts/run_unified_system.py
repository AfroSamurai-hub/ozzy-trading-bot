#!/usr/bin/env python3
"""
Unified dashboard and trading system runner for Ozzy Simple.

This script starts the live dashboard in a separate process and then
runs the trading system with live labeling in the main process.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

# Get the Python executable from virtual environment if it exists
VENV_PYTHON = PROJECT_ROOT / "venv/bin/python"
PYTHON_EXE = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable

def _load_env_file() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            os.environ.setdefault(key, value)
    except Exception:
        pass

async def run_live_system(duration_seconds: int = 3600, decision_interval: int = 60):
    """
    Run the live trading system with dashboard and labeler.
    
    Args:
        duration_seconds: How long to run the system (in seconds)
        decision_interval: How often to make trading decisions (in seconds)
    """
    # Start the Ozzy Monitor dashboard in a separate process
    dashboard_cmd = [
        PYTHON_EXE, 
        str(PROJECT_ROOT / "scripts/ozzy_monitor.py")
    ]
    
    # Start the labeler
    labeler_cmd = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts/live_labeler.py")
    ]
    
    # Command for the trading system
    trading_cmd = [
        PYTHON_EXE,
        str(PROJECT_ROOT / "scripts/test_live_stream.py"),
        "--duration", str(duration_seconds),
        "--decision-interval", str(decision_interval),
        "--bootstrap-csv", "data/historical/BTCUSDT_5m_bootstrap.csv"
    ]
    
    # Create log directory if it doesn't exist
    log_dir = PROJECT_ROOT / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Create a separate terminal for the dashboard if possible
    dashboard_log = open(log_dir / "dashboard.log", "w")
    labeler_log = open(log_dir / "labeler.log", "w")
    
    try:
        # Start dashboard process in a separate window if possible
        logger.info("🌐 Starting Ozzy Monitor dashboard...")
        # Using a separate terminal window if possible (will fall back to logging)
        try:
            # Try to open in a new terminal window
            if sys.platform == "win32":
                dashboard_process = subprocess.Popen(
                    f"start cmd /k {PYTHON_EXE} {PROJECT_ROOT}/scripts/ozzy_monitor.py",
                    shell=True
                )
            elif sys.platform == "darwin":  # macOS
                dashboard_process = subprocess.Popen(
                    ["osascript", "-e", f'tell app "Terminal" to do script "{PYTHON_EXE} {PROJECT_ROOT}/scripts/ozzy_monitor.py"']
                )
            else:  # Linux and others
                # Try common terminal emulators
                for term in ["gnome-terminal", "konsole", "xterm"]:
                    try:
                        dashboard_process = subprocess.Popen(
                            [term, "-e", f"{PYTHON_EXE} {PROJECT_ROOT}/scripts/ozzy_monitor.py"]
                        )
                        break
                    except (FileNotFoundError, subprocess.SubprocessError):
                        continue
                else:
                    # Fall back to background process with logging
                    dashboard_process = subprocess.Popen(
                        dashboard_cmd,
                        stdout=dashboard_log,
                        stderr=subprocess.STDOUT,
                    )
        except Exception as e:
            logger.warning(f"Could not open dashboard in new terminal window: {e}")
            dashboard_process = subprocess.Popen(
                dashboard_cmd,
                stdout=dashboard_log,
                stderr=subprocess.STDOUT,
            )
        
        # Start labeler process
        logger.info("🏷️ Starting pattern labeler...")
        labeler_process = subprocess.Popen(
            labeler_cmd,
            stdout=labeler_log,
            stderr=subprocess.STDOUT,
        )
        
        # Give the processes a moment to start
        await asyncio.sleep(2)
        
        # Check if the processes are still running
        if labeler_process.poll() is not None:
            logger.error("❌ Pattern labeler failed to start")
        else:
            logger.info("✅ Pattern labeler started successfully")
            
        logger.info("📊 Dashboard running in CLI mode")
        
        # Run the trading system (this will block until completion)
        logger.info("🤖 Starting trading system...")
        trading_process = await asyncio.create_subprocess_exec(
            *trading_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        
        # Stream output from the trading system
        if trading_process.stdout:
            async for line in trading_process.stdout:
                decoded = line.decode().strip()
                print(decoded)
        
        # Wait for trading to complete
        await trading_process.wait()
        
        logger.info("✅ Trading system complete")
        
    finally:
        # Clean up processes
        if 'dashboard_process' in locals():
            logger.info("Stopping dashboard...")
            try:
                dashboard_process.terminate()
                try:
                    dashboard_process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    dashboard_process.kill()
            except Exception as e:
                logger.warning(f"Could not terminate dashboard process: {e}")
        
        if 'labeler_process' in locals():
            logger.info("Stopping pattern labeler...")
            labeler_process.terminate()
            try:
                labeler_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                labeler_process.kill()
        
        # Close log files
        if 'dashboard_log' in locals():
            dashboard_log.close()
        if 'labeler_log' in locals():
            labeler_log.close()

def parse_args(argv: Optional[List[str]] = None):
    import argparse
    
    parser = argparse.ArgumentParser(description="Run the unified dashboard and trading system")
    parser.add_argument(
        "--duration", 
        type=int,
        default=3600, 
        help="How long to run the trading system (in seconds, default: 3600)"
    )
    parser.add_argument(
        "--decision-interval", 
        type=int, 
        default=60,
        help="How often to make trading decisions (in seconds, default: 60)"
    )
    
    return parser.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> int:
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    
    # Load environment variables
    _load_env_file()
    
    if not os.getenv("OPENAI_API_KEY"):
        logger.error("❌ OPENAI_API_KEY is not configured. Check your .env or environment variables.")
        return 1
    
    args = parse_args(argv)
    
    try:
        # Handle Ctrl+C gracefully
        def signal_handler(sig, frame):
            logger.info("Interrupted, shutting down...")
            raise KeyboardInterrupt
            
        signal.signal(signal.SIGINT, signal_handler)
        
        # Run the system
        asyncio.run(run_live_system(args.duration, args.decision_interval))
    except KeyboardInterrupt:
        logger.info("Stopped by user")
        return 130
    except Exception as e:
        logger.error(f"❌ Unified system failed: {e}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
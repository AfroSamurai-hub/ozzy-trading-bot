"""
A one-time script to bootstrap the vector database with historical patterns
from a CSV file.
"""
import logging
from pathlib import Path
import sys

# Add project root to path to allow imports
sys.path.append(str(Path(__file__).parent.parent))

from intelligence.rolling_window_db import RollingWindowPatternDB

# --- Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DB_PATH = str(Path(__file__).parent.parent / "data/vector_db")
CSV_PATH = str(Path(__file__).parent.parent / "data/bootstrap_patterns.csv")

def main():
    """
    Clears the existing database and loads fresh patterns from the bootstrap CSV.
    """
    logger.info("🚀 Starting database bootstrap process...")
    
    try:
        db = RollingWindowPatternDB(persist_directory=DB_PATH)
        
        logger.info(f"Loading patterns from: {CSV_PATH}")
        
        # Clear existing data to ensure a fresh start
        logger.info("Clearing existing patterns from the database...")
        db.clear()
        
        # Load new patterns from the CSV
        num_loaded = db.load_from_csv(CSV_PATH, clear_existing=False) # Already cleared
        
        if num_loaded > 0:
            logger.info(f"✅ Successfully loaded {num_loaded} patterns into the database.")
            stats = db.get_stats()
            capacity = db.get_capacity_info()
            logger.info(f"📊 DB Stats: {stats}")
            logger.info(f"📦 DB Capacity: {capacity}")
        else:
            logger.warning("⚠️ No patterns were loaded. Check the CSV file path and content.")
            
    except FileNotFoundError:
        logger.error(f"❌ Bootstrap CSV file not found at: {CSV_PATH}")
        logger.error("Please ensure the 'data/bootstrap_patterns.csv' file exists.")
    except Exception as e:
        logger.critical(f"💥 An unexpected error occurred during bootstrap: {e}", exc_info=True)

if __name__ == "__main__":
    main()

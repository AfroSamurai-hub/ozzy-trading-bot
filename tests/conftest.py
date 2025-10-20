"""
Pytest configuration to fix import paths.

This file tells pytest where to find project modules.
"""
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print(f"✅ Added to Python path: {project_root}")

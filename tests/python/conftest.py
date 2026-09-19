import sys
from pathlib import Path

# Make the repository root importable so tests can use
# `from src.python.combined_bounds_matcher import ...`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

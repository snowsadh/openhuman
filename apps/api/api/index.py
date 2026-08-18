import sys
from pathlib import Path

# Ensure the parent directory is in the path to allow importing app module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

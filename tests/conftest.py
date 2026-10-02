import os
import sys
import tempfile
from pathlib import Path

# Configuration is read at import time, so point it at throwaway locations
# before any bot module is imported.
os.environ.setdefault("DATA_DIR", tempfile.mkdtemp(prefix="godbot-test-"))
os.environ.setdefault("LOCAL_API_KEY", "test-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

"""Download the local room-detection model into ./models (build step / manual).  --dev also fetches the text encoder."""
import logging, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
logging.basicConfig(level=logging.INFO, format="%(message)s")
from app import modelfetch

dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "models")
if not modelfetch.fetch(dest, dev="--dev" in sys.argv):
    print("WARNING: room model unavailable; the app will run without room-type detection", file=sys.stderr)

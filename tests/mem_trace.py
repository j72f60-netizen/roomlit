import sys, os, tracemalloc
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from app.engine import pipeline, enhance
pipeline.init_worker(80_000_000, 1)
if len(sys.argv) > 2: enhance.STRIP_PIXELS = int(sys.argv[2])
f = sys.argv[1]; os.makedirs("/tmp/memprobe", exist_ok=True)
tracemalloc.start()
r = pipeline.process_file(f, "/tmp/memprobe/out.jpg", "/tmp/memprobe", 1, "premium", None, 80_000_000)
cur, peak = tracemalloc.get_traced_memory()
print(f"strip={enhance.STRIP_PIXELS} traced peak MB {peak/1e6:.0f} ({r['width']}x{r['height']}, image={r['width']*r['height']*3/1e6:.0f}MB)")

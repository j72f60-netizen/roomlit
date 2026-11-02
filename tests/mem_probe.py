import sys, os, threading, time
import psutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
p = psutil.Process()
peak = [0]
def mon():
    while True:
        peak[0] = max(peak[0], p.memory_info().rss); time.sleep(0.005)
threading.Thread(target=mon, daemon=True).start()
from app.engine import pipeline
pipeline.init_worker(80_000_000, 1)
base = p.memory_info().rss
print("after import MB", base/1e6)
f = sys.argv[1]
os.makedirs("/tmp/memprobe", exist_ok=True)
peak[0] = 0
r = pipeline.analyze_file(f, "/tmp/memprobe", 1, 80_000_000)
print("analyze: peak delta MB", (peak[0]-base)/1e6, r["width"], r["height"], r["seconds"], "s")
peak[0] = 0
r = pipeline.process_file(f, "/tmp/memprobe/out.jpg", "/tmp/memprobe", 1, "premium", None, 80_000_000)
print("process: peak delta MB", (peak[0]-base)/1e6, "abs peak MB", peak[0]/1e6, r["seconds"], "s", r["width"], "x", r["height"])

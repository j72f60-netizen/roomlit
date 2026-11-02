"""Entry point of the isolated image worker process.

Photos are only ever decoded in this process.  If a photo is pathological enough to
exhaust memory, only this process dies; the web app notices, reports that one photo
as failed, starts a fresh worker and carries on.
"""
from __future__ import annotations

import traceback


def main(conn, max_pixels: int, threads: int) -> None:
    from .engine import pipeline
    from .engine.imageio import ImageError

    pipeline.init_worker(max_pixels, threads)
    conn.send(("ready", None))
    while True:
        try:
            msg = conn.recv()
        except (EOFError, OSError):
            return
        if msg is None:
            return
        fn, args = msg
        try:
            if fn == "analyze":
                res = pipeline.analyze_file(*args)
            elif fn == "process":
                res = pipeline.process_file(*args)
            elif fn == "group":
                res = pipeline.group_params(*args)
            else:
                raise ValueError("unknown task")
            conn.send(("ok", res))
        except ImageError as e:
            conn.send(("image_error", str(e)))
        except MemoryError:
            conn.send(("image_error", "Not enough server memory for this photo"))
        except Exception:
            # never include pixel data or file names in the message
            conn.send(("error", traceback.format_exc(limit=3)))

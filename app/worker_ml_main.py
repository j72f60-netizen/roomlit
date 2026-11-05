"""Entry point of the short-lived organizer process (duplicates, room types, ordering).

Started only while organising; the image worker is stopped meanwhile so two heavy processes never coexist.
Receives preview JPEGs by path (never the original photos) and returns plain data.
"""
from __future__ import annotations

import os
import traceback


def main(conn, model_dir: str, threads: int) -> None:
    try:
        os.nice(10)
    except Exception:
        pass
    from .engine.organize.run import organize

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
            if fn != "organize":
                raise ValueError("unknown task")
            conn.send(("ok", organize(args[0], model_dir, threads)))
        except MemoryError:
            conn.send(("error", "MemoryError"))
        except Exception:
            conn.send(("error", traceback.format_exc(limit=3)))

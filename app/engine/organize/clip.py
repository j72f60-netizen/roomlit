"""CLIP image encoder (OpenAI ViT-B/32, MIT licence) running locally through onnxruntime.

Used for two things only: a room-type guess and an image embedding (so photos of the same room can be told
apart from photos of different rooms).  Nothing is sent anywhere.  If the model file is missing the rest of the
organizer still works (without room labels), so a broken download never blocks editing.
"""
from __future__ import annotations

import os

import cv2
import numpy as np

from .classes import CLASSES

MEAN = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
STD = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
MODEL_FILE = "vision_model_quantized.onnx"
_TEXT = os.path.join(os.path.dirname(__file__), "clip_text.npz")


class ClipUnavailable(Exception):
    pass


class Clip:
    def __init__(self, model_dir: str, threads: int = 1):
        path = os.path.join(model_dir, MODEL_FILE)
        if not os.path.exists(path):
            raise ClipUnavailable("room model not installed")
        try:
            import onnxruntime as ort
        except Exception as e:  # pragma: no cover
            raise ClipUnavailable(f"onnxruntime missing: {e}")
        so = ort.SessionOptions()
        so.intra_op_num_threads = threads
        so.inter_op_num_threads = 1
        so.enable_cpu_mem_arena = False      # return memory to the OS after each image (512 MB server)
        so.enable_mem_pattern = False
        so.log_severity_level = 3
        self.sess = ort.InferenceSession(path, so, providers=["CPUExecutionProvider"])
        t = np.load(_TEXT)
        self.classes = [str(c) for c in t["classes"]]
        assert self.classes == CLASSES
        self.text = t["emb"].astype(np.float32)
        self.pos = t["appeal_pos"].astype(np.float32)
        self.neg = t["appeal_neg"].astype(np.float32)

    @staticmethod
    def preprocess(bgr: np.ndarray) -> np.ndarray:
        h, w = bgr.shape[:2]
        s = 224.0 / min(h, w)
        r = cv2.resize(bgr, (max(224, round(w * s)), max(224, round(h * s))), interpolation=cv2.INTER_CUBIC)
        y0, x0 = (r.shape[0] - 224) // 2, (r.shape[1] - 224) // 2
        c = r[y0:y0 + 224, x0:x0 + 224, ::-1].astype(np.float32) / 255.0        # BGR -> RGB
        c = (c - MEAN) / STD
        return np.ascontiguousarray(c.transpose(2, 0, 1)[None])

    def embed(self, bgr: np.ndarray) -> np.ndarray:
        e = self.sess.run(None, {"pixel_values": self.preprocess(bgr)})[0][0].astype(np.float32)
        return e / np.linalg.norm(e)

    def classify(self, emb: np.ndarray) -> list[tuple[str, float]]:
        """Class probabilities (softmax over the room classes), best first."""
        logits = 100.0 * (self.text @ emb)
        p = np.exp(logits - logits.max()); p /= p.sum()
        order = np.argsort(-p)
        return [(self.classes[i], float(p[i])) for i in order]

    def appeal(self, emb: np.ndarray) -> float:
        """0..1, how much the picture resembles 'bright, tidy, professional' versus 'dark, messy, amateur'."""
        d = float(emb @ self.pos - emb @ self.neg)
        return float(1.0 / (1.0 + np.exp(-12.0 * d)))

"""Dev-only: encode the class prompts with CLIP's text encoder and store them in app/engine/organize/clip_text.npz.
Needs models/text_model_quantized.onnx + models/tokenizer.json (see scripts/fetch_models.py --dev)."""
import os, sys
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, ROOT)
from app.engine.organize.classes import CLASSES, PROMPTS, APPEAL_POS, APPEAL_NEG

tok = Tokenizer.from_file(os.path.join(ROOT, "models", "tokenizer.json"))
sess = ort.InferenceSession(os.path.join(ROOT, "models", "text_model_quantized.onnx"), providers=["CPUExecutionProvider"])


def enc(text: str) -> np.ndarray:
    ids = tok.encode(text).ids
    if ids[0] != 49406: ids = [49406] + ids
    if ids[-1] != 49407: ids = ids + [49407]
    e = sess.run(None, {"input_ids": np.array([ids[:77]], dtype=np.int64)})[0][0]
    return e / np.linalg.norm(e)


def group(prompts):
    m = np.mean([enc(p) for p in prompts], axis=0)
    return (m / np.linalg.norm(m)).astype(np.float32)


emb = np.stack([group(PROMPTS[c]) for c in CLASSES])
np.savez_compressed(os.path.join(ROOT, "app", "engine", "organize", "clip_text.npz"),
                    classes=np.array(CLASSES), emb=emb, appeal_pos=group(APPEAL_POS), appeal_neg=group(APPEAL_NEG))
print("saved", emb.shape, "classes:", CLASSES)

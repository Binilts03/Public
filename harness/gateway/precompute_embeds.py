"""Precompute MiniLM embeddings for corpus match_text (Arm B hybrid retrieval).
Run: python harness/gateway/precompute_embeds.py
Out: harness/gateway/embeds.npy (N,384 fp32), harness/gateway/embed_ids.json
Model: all-MiniLM-L6-v2 (~90MB, HF cache, not repo).
"""
import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[2]
corpus = json.load(open(ROOT / "corpus" / "corpus.json"))
texts = [t.get("match_text") or (t["name"] + " " + t["description"]) for t in corpus]
print("when_to_use coverage:", sum(1 for t in corpus if t.get("when_to_use")), "/", len(corpus))
print("tags coverage:", sum(1 for t in corpus if t.get("tags")), "/", len(corpus))
model = SentenceTransformer("all-MiniLM-L6-v2")
emb = model.encode(texts, batch_size=64, show_progress_bar=False, normalize_embeddings=True)
emb = np.asarray(emb, dtype="float32")
np.save(ROOT / "harness" / "gateway" / "embeds.npy", emb)
json.dump([t["id"] for t in corpus], open(ROOT / "harness" / "gateway" / "embed_ids.json", "w"))
print("saved", emb.shape)

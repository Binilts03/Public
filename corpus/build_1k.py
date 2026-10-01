"""Build 1k frozen corpus from Tool-REX-Tools (enriched) + synthetic risk/unavailable/decoys.
Usage: python corpus/build_1k.py [--n 1000] [--seed 0]
Outputs: corpus/corpus.json, corpus/corpus_manifest.json
"""
import argparse, hashlib, json, random, re
from pathlib import Path

try:
    from datasets import load_dataset, get_dataset_config_names
    HAS_DS = True
except Exception:
    HAS_DS = False

OUT_DIR = Path(__file__).parent
WRITE_DESTRUCTIVE = re.compile(r"\b(delete|destroy|drop|terminate|revoke|wipe|purge|remove\s+repo|close\s+account)\b", re.I)
WRITE_RE = re.compile(r"\b(create|update|post|put|send|publish|write|add|set|transfer|pay|book)\b", re.I)

def effect_heuristic(text: str) -> str:
    t = (text or "").lower()
    if WRITE_DESTRUCTIVE.search(t):
        return "high-risk/destructive"
    if WRITE_RE.search(t):
        return "reversible-write"
    return "external-read"

def digest(obj) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()

def normalize(i, raw_doc: str, meta: dict):
    # raw_doc may be JSON string or plain doc
    try:
        d = json.loads(raw_doc) if isinstance(raw_doc, str) and raw_doc.strip().startswith("{") else {}
    except Exception:
        d = {}
    name = d.get("name") or meta.get("id") or f"tool_{i:04d}"
    desc = d.get("function_description") or d.get("description") or (raw_doc[:500] if isinstance(raw_doc, str) else str(raw_doc)[:500])
    tool = {
        "id": f"cap_{i:04d}",
        "name": str(name)[:128].strip().replace(" ", ".").lower() or f"tool.{i}",
        "description": desc[:2000],
        "when_to_use": d.get("when_to_use", []),
        "limitations": d.get("limitations", []),
        "tags": d.get("tags", []),
        "effect_class": effect_heuristic(desc + " " + str(name)),
        "input_schema": d.get("input_schema", {"type": "object"}),
        "source": "tool-rex-tools",
    }
    tool["digest"] = digest({k: tool[k] for k in sorted(tool) if k != "digest"})
    return tool

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    random.seed(a.seed)
    tools = []
    if HAS_DS:
        try:
            from datasets import get_dataset_split_names
            splits = get_dataset_split_names("Lux1997/Tool-REX-Tools")
        except Exception as e:
            print(f"split list failed: {e}; using default")
            splits = ["code", "web", "customized"]
        print(f"splits: {splits}")
        per = max(1, int(a.n * 0.8) // max(1, len(splits)))
        idx = 0
        for sp in splits:
            try:
                ds = load_dataset("Lux1997/Tool-REX-Tools", split=sp, streaming=True)
            except Exception as e:
                print(f"skip {sp}: {e}")
                continue
            taken = 0
            for row in ds:
                if taken >= per or idx >= int(a.n * 0.8):
                    break
                doc = row.get("documentation") or row.get("document") or row.get("text") or json.dumps(row)[:2000]
                tools.append(normalize(idx, str(doc), {"id": row.get("id", str(idx))}))
                idx += 1
                taken += 1
            print(f"{sp}: took {taken}")
            if idx >= int(a.n * 0.8):
                break
    # pad from stream remainder / synthetic if offline
    while len(tools) < int(a.n * 0.8):
        i = len(tools)
        tools.append(normalize(i, json.dumps({"name": f"synth.tool.{i}", "description": f"Synthetic fallback read tool {i}"}), {}))
    # inject required mixes: 10% high-risk, 10% unavailable, 10% decoys (of total n)
    n = a.n
    n_risk = int(n * 0.10)
    n_unavail = int(n * 0.10)
    n_decoy = int(n * 0.10)
    # force first n_risk to high-risk
    for i in range(min(n_risk, len(tools))):
        tools[i]["effect_class"] = "high-risk/destructive"
        tools[i]["digest"] = digest({k: tools[i][k] for k in sorted(tools[i]) if k != "digest"})
    # unavailable variants (copy + mark)
    for j in range(n_unavail):
        src = random.choice(tools)
        t = dict(src)
        t["id"] = f"cap_unavail_{j:03d}"
        t["name"] = src["name"] + ".unavail"
        t["availability"] = "disconnected"
        t["digest"] = digest({k: t[k] for k in sorted(t) if k != "digest"})
        tools.append(t)
    # native decoys
    for j in range(n_decoy):
        t = {"id": f"cap_native_{j:03d}", "name": f"native.{j}", "description": "Native harness op (shell/file) — must not trigger external prefetch",
             "when_to_use": [], "limitations": ["native-only"], "tags": ["native-decoy"],
             "effect_class": "native-decoy", "input_schema": {"type": "object"}, "source": "synthetic-native"}
        t["digest"] = digest({k: t[k] for k in sorted(t) if k != "digest"})
        tools.append(t)
    tools = tools[:n + n_unavail + n_decoy][:1200]  # cap
    # trim to exactly n target + extras? keep first n as core, extras flagged
    manifest = {"n_core_target": n, "n_total": len(tools),
                "counts": {k: sum(1 for t in tools if t.get("effect_class") == k or t.get("availability") == "disconnected" and k == "unavailable") for k in ["external-read", "reversible-write", "high-risk/destructive", "native-decoy"]},
                "global_digest": digest([t["digest"] for t in tools])}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "corpus.json").write_text(json.dumps(tools, indent=2))
    (OUT_DIR / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()

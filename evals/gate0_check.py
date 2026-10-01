"""Gate 0: trace fidelity check. Fails unless known invocation/permission/result size/session are captured."""
import json, sys
from pathlib import Path
def check(ev):
    errs=[]
    if not ev.get("run_id"): errs.append("missing run_id")
    if "turn" not in ev: errs.append("missing turn")
    ct=ev.get("context_tokens",{})
    for k in ["schema","search","result"]:
        if k not in ct: errs.append(f"missing context_tokens.{k}")
    if not isinstance(ev.get("tool_calls",[]),list): errs.append("tool_calls not list")
    if not isinstance(ev.get("permission_events",[]),list): errs.append("permission_events not list")
    return errs
if __name__=="__main__":
    p=Path(sys.argv[1]) if len(sys.argv)>1 else None
    ev=json.loads(p.read_text()) if p else {"run_id":"demo","turn":0,"context_tokens":{"schema":0,"search":0,"result":0},"tool_calls":[],"permission_events":[],"cache":{}}
    errs=check(ev)
    print("PASS" if not errs else f"FAIL: {errs}")
    sys.exit(0 if not errs else 1)

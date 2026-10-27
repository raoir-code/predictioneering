"""
API usage log (Oct 27). Records the token counts of every Anthropic Messages response in this process, with the calling
function, to logs/api_usage_<YYYYMMDD>.jsonl (local, gitignored). Changes nothing about any request or response: it reads
the `usage` block the API already returns. pilot/health.py sums it into tokens and an estimated cost per step.
Enable in a process with enable() (each daily entry script does this in its __main__ block); safe to call twice.
Prices are estimates for the report only; the Console's billing is authoritative.
"""
import json, os, sys, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICE = {   # USD per million tokens (input, output); cache reads at 0.1x input, cache writes at 1.25x input
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
}

def _caller():
    f = sys._getframe(2)
    while f is not None:
        mod = f.f_globals.get("__name__", "")
        fn = f.f_code.co_filename
        if not (mod.startswith(("requests", "urllib3", "http", "json")) or fn.endswith("api_usage.py") or "/requests/" in fn):
            name = mod if mod != "__main__" else Path(fn).stem
            return f"{name.split('.')[-1]}.{f.f_code.co_name}"
        f = f.f_back
    return "unknown"

def cost(model, u):
    pi, po = PRICE.get(model, (0.0, 0.0))
    return (u.get("input_tokens", 0) * pi + u.get("output_tokens", 0) * po
            + u.get("cache_read_input_tokens", 0) * pi * 0.1 + u.get("cache_creation_input_tokens", 0) * pi * 1.25) / 1e6

def record(model, usage, caller, path=None):
    path = path or ROOT / "logs" / f"api_usage_{dt.date.today():%Y%m%d}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": dt.datetime.now().isoformat(timespec="seconds"), "step": Path(sys.argv[0]).stem, "caller": caller, "model": model,
           **{k: int(usage.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}}
    row["usd_est"] = round(cost(model, row), 6)
    with open(path, "a") as fh:
        fh.write(json.dumps(row) + "\n")

def enable():
    try:
        import requests
        S = requests.sessions.Session
        if getattr(S, "_pq_usage", False):
            return
        orig = S.send

        def send(self, request, **kw):
            resp = orig(self, request, **kw)
            try:
                if "api.anthropic.com" in (request.url or "") and "/v1/messages" in request.url and resp.status_code == 200:
                    j = resp.json()
                    if isinstance(j, dict) and isinstance(j.get("usage"), dict):
                        record(j.get("model") or "unknown", j["usage"], _caller())
            except Exception:
                pass          # never let accounting break a run
            return resp

        S.send = send; S._pq_usage = True
    except Exception:
        pass

def summary(path):
    """{(step, caller, model): [calls, input, output, usd]} for one day's file."""
    out = {}
    if not Path(path).exists():
        return out
    for l in Path(path).read_text().splitlines():
        if not l.strip():
            continue
        r = json.loads(l); k = (r["step"], r["caller"], r["model"])
        v = out.setdefault(k, [0, 0, 0, 0.0])
        v[0] += 1; v[1] += r["input_tokens"] + r["cache_read_input_tokens"] + r["cache_creation_input_tokens"]; v[2] += r["output_tokens"]; v[3] += r["usd_est"]
    return out

def _tests():
    import tempfile
    p = Path(tempfile.mkdtemp()) / "u.jsonl"
    record("claude-opus-4-6", {"input_tokens": 1_000_000, "output_tokens": 100_000}, "engine._call_claude_json", p)
    record("claude-sonnet-4-6", {"input_tokens": 200_000, "output_tokens": 0, "cache_read_input_tokens": 1_000_000}, "translator.clergyman", p)
    s = summary(p)
    (a,) = [v for k, v in s.items() if k[1] == "engine._call_claude_json"]
    assert a[0] == 1 and abs(a[3] - (5.0 + 2.5)) < 1e-9, a
    (b,) = [v for k, v in s.items() if k[1] == "translator.clergyman"]
    assert abs(b[3] - (0.6 + 0.3)) < 1e-9 and b[1] == 1_200_000, b
    print("api_usage tests pass")

if __name__ == "__main__":
    _tests()

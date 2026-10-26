"""Freeze inventory (to-do: "freeze every local table still needed after the local data ends; document what goes stale").
Read-only. Lists every gitignored local table production reads, its date coverage, and what goes stale; writes pilot/local/MANIFEST.md.
  python analysis/freeze_local.py
"""
import json, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent; LOCAL = ROOT / "pilot" / "local"; SRC = ROOT / "data" / "external" / "local_full"

# file -> (read by, what goes stale after the data ends)
USED = {
    "priors_world.json": ("pilot/unified_price.py (world priors)", "slow: episode/strike base rates by pair class; drift only with new eras"),
    "world_fits.json":   ("pilot/unified_price.py (world fits)", "slow: same as priors_world"),
    "hardening.json":    ("pilot/unified_price.py (peace hardening beta, K)", "slow: one structural coefficient"),
    "last_strike.json":  ("pilot/unified_price.py (frozen per-pair strike dates for hardening anchors)",
                          "FAST: strikes after the data end are invisible; time-since-last-strike keeps growing for pairs still "
                          "fighting, so restarts are under-priced unless the live news ledger supplies a newer date"),
    "strike_no_war.json": ("pipeline/translator.py via pilot/strike_no_war.py (window hit rates)",
                           "medium: rates as of the table's data end; a change in a pair's strike tempo after it is missed"),
}
ABSENT = ("phase.json", "strike_given_war.json")       # not adopted; must stay absent

def _dates(o, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k in ("computed_at", "data_end", "end", "fit_end") and isinstance(v, str): out.append((k, v[:10]))
            else: _dates(v, out)
    elif isinstance(o, list):
        for v in o[:50]: _dates(v, out)

def main():
    lines = [f"# Local tables used by production (inventory {dt.date.today()})", ""]
    raw_end = None
    if SRC.exists():
        for f in SRC.glob("*_explosions.jsonl"):
            for l in f.read_text().splitlines():
                if l.strip():
                    d = json.loads(l)["event_date"][:10]; raw_end = max(raw_end or d, d)
    lines.append(f"Raw local pull: latest event {raw_end} (fits use data through 7 days before that)."); lines.append("")
    ok = True
    for name, (who, stale) in USED.items():
        f = LOCAL / name
        if not f.exists(): lines.append(f"- MISSING {name}: read by {who}"); ok = False; continue
        j = json.loads(f.read_text()); ds = []; _dates(j, ds)
        cov = ", ".join(sorted({f"{k} {v}" for k, v in ds})) or "no date fields"
        if name == "last_strike.json":
            allds = [d for v in j.values() for d in v]; cov += f"; latest strike date in table {max(allds) if allds else None}; {len(j)} pairs"
        lines.append(f"- {name} ({f.stat().st_size:,} bytes): read by {who}. Coverage: {cov}. Goes stale: {stale}.")
    for name in ABSENT:
        if (LOCAL / name).exists(): lines.append(f"- UNEXPECTED {name} present (not adopted): production would use it"); ok = False
    lines += ["", "Rollback for everything above: delete pilot/local/ (production falls back to repo priors, no hardening, no "
              "strike-no-war table). Keeping these derived tables after the access end date is a licensing question (owner: Adi)."]
    txt = "\n".join(lines) + "\n"; print(txt); (LOCAL / "MANIFEST.md").write_text(txt)
    print("INVENTORY:", "OK" if ok else "PROBLEMS ABOVE", "->", LOCAL / "MANIFEST.md")

if __name__ == "__main__":
    main()

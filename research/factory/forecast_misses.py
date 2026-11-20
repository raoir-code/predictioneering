"""Read-only resolved forecast miss scanner for the isolated Research Factory.

Consumes predictions/brier_log.jsonl without importing production code, mutating
the forecasting engine, making network requests, or using a paid AI model.
Produces diagnostic candidate patterns, not established research puzzles.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sys

from . import pipeline, prototype

RESEARCH_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = RESEARCH_ROOT.parent / "predictions" / "brier_log.jsonl"
DEFAULT_OUT = RESEARCH_ROOT / "inbox" / "forecast_misses"
VERSION = "research-miss-scanner-v0.1"
TOPICS = (
    ("ceasefire", r"ceasefire|truce|peace agreement"),
    ("blockade", r"blockade|naval quarantine"),
    ("invasion_or_ground", r"invad|invasion|ground operation|ground offensive"),
    ("strike_and_bombardment", r"strik|airstrike|missile|drone|bombard|rocket"),
    ("clash_or_engagement", r"clash|engagement|skirmish|exchange of fire"),
    ("withdrawal", r"withdraw|retreat|pullout"),
    ("military_action_other", r"military action|military operation|attack|target"),
)
MONTHS = (r"january|february|march|april|may|june|july|august|september|"
          r"october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")


def iso_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo is not None else None
    except ValueError:
        return None


def probability(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        v = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return v if math.isfinite(v) and 0 <= v <= 1 else None


def topic(label):
    for name, pattern in TOPICS:
        if re.search(pattern, str(label or "").lower()):
            return name
    return "other_or_unclassified"


def label_template(label):
    s = str(label or "").casefold()
    s = re.sub(r"\b(?:" + MONTHS + r")\b", " month ", s)
    s = re.sub(r"\b(?:19|20)\d{2}\b|\b\d{1,2}(?:st|nd|rd|th)?\b", " n ", s)
    return " ".join(re.sub(r"[^a-z]+", " ", s).split())[:160]


def read_log(source):
    path = Path(source).expanduser().resolve()
    if not path.is_file() or path.stat().st_size > 50_000_000:
        raise ValueError("Resolved Brier log missing or exceeds 50 MB")
    raw = path.read_bytes()
    source_hash = hashlib.sha256(raw).hexdigest()
    qc = Counter()
    records = {}
    conflicted = set()
    for line in raw.splitlines():
        if not line.strip():
            continue
        qc["input_lines"] += 1
        try:
            record = json.loads(line)
        except (ValueError, UnicodeDecodeError):
            qc["malformed_json"] += 1
            continue
        if not isinstance(record, dict):
            qc["not_objects"] += 1
            continue
        mid = str(record.get("market_id") or "").strip()
        if not mid or len(mid) > 100:
            qc["invalid_id"] += 1
            continue
        if mid in conflicted:
            continue
        y = record.get("outcome")
        if isinstance(y, bool) or y not in (0, 1):
            qc["unresolved_or_invalid_outcome"] += 1
            continue
        resolved = iso_time(record.get("resolved_at"))
        first = iso_time(record.get("first_prediction_ts"))
        p = probability(record.get("conditional_p"))
        market = probability(record.get("market_p_at_first"))
        if resolved is None or first is None or first >= resolved:
            qc["invalid_or_post_resolution_timestamp"] += 1
            continue
        if p is None or market is None:
            qc["missing_or_invalid_paired_probabilities"] += 1
            continue
        if mid in records:
            older = records[mid]
            if older["outcome"] != int(y) or older["resolved_at"] != resolved.isoformat():
                conflicted.add(mid)
                del records[mid]
                qc["conflicting_resolution_ids"] += 1
            else:
                qc["duplicate_resolution_lines"] += 1
            continue
        label = str(record.get("market_label") or "").strip()[:250]
        dyad = str(record.get("dyad") or "unclassified_dyad").strip()[:120]
        records[mid] = {
            "market_id": mid, "label": label,
            "dyad": dyad or "unclassified_dyad",
            "topic": topic(label), "template": label_template(label),
            "contract_type": str(record.get("contract_type") or "unknown_contract_type")[:80],
            "relation": str(record.get("relation") or "unknown_relation")[:80],
            "outcome": int(y), "forecast_p": p, "market_p": market,
            "resolved_at": resolved.isoformat(), "forecast_at": first.isoformat(),
            "model_brier": (p-int(y))**2,
            "market_brier": (market-int(y))**2,
            "excess_brier": (p-int(y))**2 - (market-int(y))**2,
        }
    qc["valid_unique_resolved_contracts"] = len(records)
    return list(records.values()), dict(qc), source_hash


def assign_families(rows):
    """Possible siblings, not verified independent event identities."""
    groups = defaultdict(list)
    for item in rows:
        groups[(item["dyad"], item["template"])].append(item)
    for (dyad, template), group in groups.items():
        group.sort(key=lambda x: (x["resolved_at"], x["market_id"]))
        last, index = None, -1
        for item in group:
            when = iso_time(item["resolved_at"])
            if last is None or when-last > timedelta(days=3):
                index += 1
            fingerprint = f"{dyad}|{template}|{index}"
            item["family_id"] = hashlib.sha256(fingerprint.encode()).hexdigest()[:16]
            last = when
    return rows


def summarize(items):
    if not items:
        raise ValueError("Empty group")
    families = defaultdict(list)
    for r in items:
        families[r["family_id"]].append(r)
    means = [sum(r["excess_brier"] for r in fam)/len(fam)
             for fam in families.values()]
    return {
        "contracts": len(items), "possible_event_families": len(families),
        "distinct_dyads": len({r["dyad"] for r in items}),
        "model_brier_mean": round(sum(r["model_brier"] for r in items)/len(items), 6),
        "market_brier_mean": round(sum(r["market_brier"] for r in items)/len(items), 6),
        "contract_mean_excess_brier": round(sum(r["excess_brier"] for r in items)/len(items), 6),
        "family_mean_excess_brier": round(sum(means)/len(means), 6),
        "false_negative_contracts": sum(r["outcome"] == 1 and r["forecast_p"] <= .2 for r in items),
        "false_positive_contracts": sum(r["outcome"] == 0 and r["forecast_p"] >= .8 for r in items),
        "positives": sum(r["outcome"] == 1 for r in items),
        "probable_duplicate_contracts": len(items)-len(families),
        "extreme_brier_contracts": sum(r["model_brier"] >= .5 for r in items),
        "sample_market_ids": [r["market_id"] for r in
                              sorted(items, key=lambda z: -z["excess_brier"])[:6]],
    }


def group_signatures(rows, min_contracts, min_families):
    groups = defaultdict(list)
    for item in rows:
        for axis in ("topic", "contract_type", "relation", "dyad"):
            groups[(axis, item[axis])].append(item)
    results = []
    for (axis, value), items in groups.items():
        if len(items) < min_contracts:
            continue
        result = summarize(items)
        if result["possible_event_families"] < min_families:
            continue
        result.update(axis=axis, value=value,
                      scope="single_dyad" if axis=="dyad" else "pooled",
                      hypothesis="forecast_error_diagnostic_only")
        result["can_screen_as_candidate"] = (
            result["family_mean_excess_brier"] >= .04 and
            result["extreme_brier_contracts"] >= 2)
        results.append(result)
    return sorted(results, key=lambda x: (
        -x["family_mean_excess_brier"], -x["possible_event_families"],
        x["axis"], x["value"]))


def candidate_brief(group):
    axis, val = group["axis"], group["value"]
    value = str(val).replace("_", " ")
    if axis=="dyad":
        context=f"the {value} dyad"
    elif axis=="topic":
        context=f"{value} contracts"
    elif axis=="contract_type":
        context=f"{value} contract types"
    else:
        context=f"{value} translator relations"
    return {
        "title": f"Forecast miss diagnostic: {axis} / {val}",
        "research_question": (
            "Why does the forecast model underperform simultaneously logged market "
            f"probabilities for {context}, after collapsing correlated market families?"
        ),
        "phenomenon": f"Observed resolution-log forecast-error concentration in {context}.",
        "expected_theory": (
            "No independently verified theory predicts this pattern; "
            "this is not yet a scholarly puzzle."
        ),
        "mechanism": (
            "Mechanism UNKNOWN. Competing possibilities are market/outcome timing, "
            "contract classification, calibration, shared-event dependence, "
            "software implementation, or missing strategic variables."
        ),
        "testable_prediction": (
            "If systematic rather than coding- or timing-driven, excess forecast error "
            f"for {context} recurs across independent event families and future time holdouts."
        ),
        "potential_data": (
            "Time-stamped paired model/market forecasts, event resolution rules, "
            "deduplicated event families, and independently measured conflict covariates."
        ),
        "forecasting_benefit": (
            "If independently replicated, new variables can be evaluated in prospective "
            "out-of-sample model comparisons."
        ),
        "forecast_evidence_location": (
            "See locally generated MISSES_SCREEN.json; mechanism and novelty unverified."
        ),
    }


def analyze(source, *, since=None, min_contracts=5, min_families=3,
            max_candidates=6):
    if not (2 <= min_contracts <= 10000 and
            2 <= min_families <= 10000 and 1 <= max_candidates <= 30):
        raise ValueError("Invalid screen thresholds")
    since_date = date.fromisoformat(since) if since else None
    all_rows, qc, source_hash = read_log(source)
    chosen = [r for r in all_rows if since_date is None or
              iso_time(r["resolved_at"]).date() >= since_date]
    assign_families(chosen)
    chosen.sort(key=lambda r:(r["resolved_at"], r["market_id"]))
    overall = summarize(chosen) if chosen else None
    groups = group_signatures(chosen, min_contracts, min_families)
    candidates = [g for g in groups if g["can_screen_as_candidate"]][:max_candidates]
    return {
        "status": "diagnostic_only_novelty_not_checked",
        "version": VERSION,
        "source_file": str(Path(source).expanduser().resolve()),
        "source_sha256": source_hash, "source_parse": qc,
        "since_resolved_date": since,
        "selected_resolved_contracts": len(chosen),
        "overall": overall, "signatures": groups,
        "candidate_screen_count": len(candidates),
        "candidates": [{"axis": g["axis"], "value":g["value"],
                        "stats":g,"brief":candidate_brief(g)} for g in candidates],
        "next_step": (
            "Inspect market resolution rules and forecast timestamps; separate "
            "calibration/software errors from possible new substantive mechanisms; "
            "approve only genuinely theoretical research questions."
        ),
        "cautions": [
            "Model conditional_p and market_p_at_first are taken from the resolver; precise timestamp alignment is not independently verified.",
            "Forecast precedes resolution but may postdate the underlying event.",
            "Sibling market grouping is an approximation, not evidence of independent events.",
            "Post hoc overlapping group scans have multiplicity and dependence issues; no p-values or causal evidence are claimed.",
            "The candidate mechanism is deliberately unverified; human research and literature review are mandatory.",
            "Production logs are read only; research output and pending cards are private.",
        ],
        "network_or_paid_api_calls": 0,
    }


def readme(report, registrations):
    lines = [
        "# Predictioneering resolved-forecast miss screen", "",
        "**Diagnostic only: no theoretical novelty, causal, or fair paired market performance claim.**",
        "",
        f"Resolved contracts selected: {report['selected_resolved_contracts']}.",
        f"Source SHA256: {report['source_sha256']}.", "",
    ]
    if report["overall"]:
        x = report["overall"]
        lines += [
            f"Mean model and logged-market Brier: {x['model_brier_mean']:.4f} "
            f"vs {x['market_brier_mean']:.4f}.",
            f"Potentially dependent sibling contracts: {x['probable_duplicate_contracts']}.", "",
        ]
    lines += ["## Diagnostic candidate slices", ""]
    for c in report["candidates"]:
        g = c["stats"]
        lines.append(
            f"- {g['axis']}/{g['value']}: {g['contracts']} contracts, "
            f"{g['possible_event_families']} possible event families, "
            f"{g['distinct_dyads']} dyads; family-mean excess Brier "
            f"{g['family_mean_excess_brier']:+.4f}; "
            f"{g['extreme_brier_contracts']} extreme losses."
        )
    if not report["candidates"]:
        lines.append("No group passed the screening threshold; no puzzle invented.")
    lines += [
        "", "## Required next step", "",
        "Verify rules, outcomes, and model/market price timestamps against pre-event evidence.",
        "Distinguish model bugs or calibration from a repeated geopolitical mechanism.",
        "Review independently and approve only legitimate research questions.",
        f"Pending puzzle cards registered: {len(registrations)}.",
        "Full private diagnostics: MISSES_SCREEN.json.",
    ]
    return "\n".join(lines) + "\n"


def execute(source, *, home=RESEARCH_ROOT, out=DEFAULT_OUT,
            register=False, **kwargs):
    report = analyze(source, **kwargs)
    source = Path(source).expanduser().resolve()
    before = report["source_sha256"]
    dest = Path(out).expanduser().resolve()
    if dest == source or source in dest.parents:
        raise ValueError("Output cannot replace the resolved forecast log")
    dest.mkdir(parents=True, exist_ok=True)
    registrations = []
    if register:
        briefs = dest/"briefs"
        briefs.mkdir(parents=True, exist_ok=True)
        for c in report["candidates"]:
            key = c["axis"] + "_" + re.sub(r"[^a-zA-Z0-9_-]","_",str(c["value"]))
            file = briefs/(key+".json")
            prototype.write_json(file,c["brief"])
            item = pipeline.register(home,file)
            registrations.append({
                "axis": c["axis"],"value":c["value"],
                "card_id":item["card_id"], "intake_status":item["status"],
            })
    prototype.write_json(dest/"MISSES_SCREEN.json",report)
    prototype.atomic_text(dest/"README.md",readme(report,registrations))
    if hashlib.sha256(source.read_bytes()).hexdigest()!=before:
        raise ValueError("Resolver log changed during scan; retry")
    return {
        "status": "diagnostic_screen_complete",
        "resolved_contracts": report["selected_resolved_contracts"],
        "candidate_slices": report["candidate_screen_count"],
        "registered_pending_intake_cards":registrations,
        "report_file":str(dest/"MISSES_SCREEN.json"),
        "readme_file":str(dest/"README.md"),
        "next_step":report["next_step"],
        "network_or_paid_api_calls":0,
    }


def main(argv=None):
    parser=argparse.ArgumentParser(description="Resolved forecasts -> screened research diagnostics")
    parser.add_argument("--brier-log",type=Path,default=DEFAULT_LOG)
    parser.add_argument("--home",type=Path,default=RESEARCH_ROOT)
    parser.add_argument("--out",type=Path,default=DEFAULT_OUT)
    parser.add_argument("--since",help="Filter by resolution date YYYY-MM-DD")
    parser.add_argument("--min-contracts",type=int,default=5)
    parser.add_argument("--min-families",type=int,default=3)
    parser.add_argument("--max-candidates",type=int,default=6)
    parser.add_argument("--register",action="store_true",
                        help="Add candidate diagnostic cards as PENDING, never approve them")
    args=parser.parse_args(argv)
    try:
        result=execute(args.brier_log,home=args.home,out=args.out,
                       register=args.register,since=args.since,
                       min_contracts=args.min_contracts,
                       min_families=args.min_families,
                       max_candidates=args.max_candidates)
        print(json.dumps(result,indent=2))
        return 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print("Forecast miss scanner stopped safely: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

"""Research-only validity check for provisional direction in ACLED remote events.

The coding RULE is not an ACLED guarantee: for air/drone and shelling
subevents Actor1 is a *candidate* weapons user; Actor2, if present, is a
*candidate* target. These must pass independent note/source review.
Battles and IED/landmine incidents remain undirected.

This module never contacts ACLED or any AI service and never exposes notes
or credentials in its stdout. Its CSV must stay under ignored research/inbox/.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import sys
import tempfile

from .holiday_acled import OUT, ATTRIBUTION
from .holiday_audit import load_verified, nonempty, safe_csv_value

REMOTE = "Explosions/Remote violence"
USABLE = {"Air/drone strike", "Shelling/artillery/missile attack"}
SAMPLE_NAME = "DIRECTION_VALIDATION_PRIVATE.csv"
SEED = "holy_days_direction_v1_20261120"
REVIEW_COLUMNS = (
    "review_actor1_weapon_user", "review_actor2_target",
    "reviewer_confidence", "reviewer_reason",
)
FIELDS = (
    "event_id_cnty", "event_date", "time_precision", "event_type",
    "sub_event_type", "actor1", "actor2", "country", "admin1",
    "notes", "source", "source_scale",
) + REVIEW_COLUMNS


def provisional_direction(event):
    """No claim of attack *initiation* even if weapon-user proxy is valid."""
    ty = str(event.get("event_type") or "")
    sub = str(event.get("sub_event_type") or "")
    a = str(event.get("actor1") or "").strip()
    b = str(event.get("actor2") or "").strip()
    if ty != REMOTE or sub not in USABLE:
        return None
    if not a or a.casefold().startswith(("unidentified ", "unknown ")):
        return None
    if str(event.get("time_precision")) != "1":
        return None
    return {
        "provisional_weapons_user": a,
        "provisional_target": b if b else None,
        "status": "unverified_remote_proxy",
    }


def stratum_key(row):
    """A review covers types and both presence/absence of Actor2."""
    return (
        str(row.get("sub_event_type") or "missing"),
        "with_actor2" if nonempty(row.get("actor2")) else "without_actor2",
    )


def population_strata(rows):
    strata = defaultdict(list)
    for row in rows:
        if provisional_direction(row) is not None:
            strata[stratum_key(row)].append(row)
    return strata


def stable_rank(row):
    identity = str(row.get("event_id_cnty") or "") + "|" + str(row.get("event_date") or "")
    return hashlib.sha256((SEED + "|" + identity).encode("utf-8")).hexdigest()


def sample_rows(rows, *, per_stratum=20):
    if not 1 <= per_stratum <= 200:
        raise ValueError("per-stratum must be from 1 to 200")
    strata = population_strata(rows)
    samples = []
    for key in sorted(strata):
        samples.extend(sorted(strata[key], key=stable_rank)[:per_stratum])
    return samples


def review_csv(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise ValueError("Existing private review CSV must not be overwritten")
    tmp = None
    try:
        with tempfile.NamedTemporaryFile("w", newline="", encoding="utf-8",
                                         dir=path.parent, delete=False) as f:
            tmp = Path(f.name)
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    key: safe_csv_value(row.get(key, "")) if key not in REVIEW_COLUMNS else ""
                    for key in FIELDS
                })
        tmp.chmod(0o600)
        tmp.replace(path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def read_review_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not set(FIELDS).issubset(set(reader.fieldnames or [])):
            raise ValueError("Private review CSV is missing required columns")
        return list(reader)


def wilson(successes, n, z=1.959963984540054):
    if n == 0:
        return None
    phat = successes / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return [round(max(0, center - half), 4), round(min(1, center + half), 4)]


def validate_annotations(sample, rows):
    """Compute diagnostics only, NOT automatic acceptance of proxies."""
    pop = {key: len(value) for key, value in population_strata(rows).items()}
    by_id = {
        str(r.get("event_id_cnty")): r for r in rows
        if provisional_direction(r) and nonempty(r.get("event_id_cnty"))
    }
    observed = defaultdict(list)
    ids = set()
    for r in sample:
        identifier = str(r.get("event_id_cnty") or "")
        if identifier in ids or identifier not in by_id:
            raise ValueError("Review contains duplicate or non-proxy ACLED event ID")
        ids.add(identifier)
        reference = by_id[identifier]
        # Detect stale/modified sheets and accidental cross-revision comparisons.
        for k in ("event_date", "sub_event_type", "actor1", "actor2"):
            if (r.get(k) or "") != str(reference.get(k) or ""):
                raise ValueError("Review row does not match verified ACLED source for " + identifier)
        observed[stratum_key(reference)].append(r)
    summaries = []
    for key in sorted(pop):
        items = observed.get(key, [])
        user_labels = [str(r["review_actor1_weapon_user"]).strip().lower() for r in items]
        target_labels = [str(r["review_actor2_target"]).strip().lower() for r in items]
        if any(x not in ("", "yes", "no", "unclear") for x in user_labels):
            raise ValueError("Weapon-user review labels must be yes/no/unclear/blank")
        if any(x not in ("", "yes", "no", "unclear", "not_applicable") for x in target_labels):
            raise ValueError("Target review labels must be yes/no/unclear/not_applicable/blank")
        if key[1] == "without_actor2" and any(x in ("yes", "no") for x in target_labels):
            raise ValueError("Cannot validate an Actor2 target where Actor2 is missing")
        if key[1] == "with_actor2" and any(x == "not_applicable" for x in target_labels):
            raise ValueError("Actor2 is present; use unclear, yes, or no")
        n_user = sum(x in ("yes", "no") for x in user_labels)
        n_user_yes = user_labels.count("yes")
        n_target = sum(x in ("yes", "no") for x in target_labels)
        n_target_yes = target_labels.count("yes")
        summaries.append({
            "subevent": key[0], "actor2_stratum": key[1],
            "population_events": pop[key],
            "sampled_events": len(items),
            "weapon_user_reviewed_decisively": n_user,
            "weapon_user_unclear_or_unreviewed": len(items) - n_user,
            "actor1_weapon_user_confirmed": n_user_yes,
            "actor1_weapon_user_confirmation_rate_among_decisive": round(n_user_yes / n_user, 4) if n_user else None,
            "actor1_weapon_user_95pct_wilson_ci_among_decisive": wilson(n_user_yes, n_user),
            "target_reviewed_decisively": n_target,
            "actor2_target_confirmed": n_target_yes,
            "actor2_target_confirmation_rate_among_decisive": round(n_target_yes / n_target, 4) if n_target else None,
            "actor2_target_95pct_wilson_ci_among_decisive": wilson(n_target_yes, n_target),
        })
    complete_user = all(s["weapon_user_reviewed_decisively"] == s["sampled_events"]
                        and s["sampled_events"] > 0 for s in summaries)
    return {
        "reviewed_sample_total": len(sample),
        "sample_design": "Deterministic uniform sample within subevent x Actor2 availability strata",
        "strata": summaries,
        "gate": "fully_decisive_user_review_completed" if complete_user else "review_incomplete_or_ambiguous",
        "interpretation": (
            "Rates are CONDITIONAL on decisive human review, not validated "
            "population accuracy. Strata are deliberately oversampled; do not "
            "pool unweighted across strata. A single reviewer is not blind "
            "independent reliability measurement. Confirmation of weapons user "
            "never establishes who started a battle or an opponent's religion."
        ),
    }


def direction_protocol(manifest=OUT / "MANIFEST.json", *,
                       make_review=False, per_stratum=20,
                       review_file=None, evaluate=False):
    reports, rows = load_verified(manifest)
    manifest = Path(manifest)
    review_file = Path(review_file) if review_file else manifest.parent / SAMPLE_NAME
    # Require private output alongside the verified local manifest; no external paths.
    if review_file.resolve().parent != manifest.resolve().parent:
        raise ValueError("Review CSV must remain beside private ACLED manifest")
    strata = population_strata(rows)
    counts = [
        {"subevent": key[0], "actor2_stratum": key[1], "eligible_events": len(group)}
        for key, group in sorted(strata.items())
    ]
    result = {
        "status": "holiday_direction_validation",
        "attribution": ATTRIBUTION,
        "total_events": len(rows),
        "eligible_provisional_remote_events": sum(len(group) for group in strata.values()),
        "not_provisionally_directional": len(rows) - sum(len(group) for group in strata.values()),
        "eligible_strata": counts,
        "provisional_coding": (
            "For exact-date air/drone strikes and shelling with identified "
            "Actor1, Actor1 is a tentative WEAPONS USER, Actor2 a tentative "
            "TARGET only when present. Battles and mines/IEDs remain undirected. "
            "These are UNVERIFIED proxies, not regression-ready measures."
        ),
        "review_file": str(review_file),
    }
    if make_review:
        selected = sample_rows(rows, per_stratum=per_stratum)
        review_csv(review_file, selected)
        result["sample_created"] = True
        result["sample_events"] = len(selected)
        result["annotation_instructions"] = (
            "Locally read notes/source and enter yes/no/unclear for whether "
            "Actor1 actually used the weapon; for Actor2 enter yes/no/unclear "
            "if present, or not_applicable if absent. Supply reason for no/unclear. "
            "Do not paste the private CSV or source notes into public systems."
        )
    if evaluate:
        if not review_file.is_file():
            raise ValueError("No review sheet to evaluate; use --make-review first")
        result["evaluation"] = validate_annotations(read_review_csv(review_file), rows)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description="Private ACLED remote-violence direction validation")
    p.add_argument("--manifest", type=Path, default=OUT / "MANIFEST.json")
    p.add_argument("--make-review", action="store_true")
    p.add_argument("--per-stratum", type=int, default=20)
    p.add_argument("--review-file", type=Path)
    p.add_argument("--evaluate", action="store_true")
    args = p.parse_args(argv)
    try:
        result = direction_protocol(
            args.manifest, make_review=args.make_review,
            per_stratum=args.per_stratum,
            review_file=args.review_file, evaluate=args.evaluate)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("ACLED direction protocol stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

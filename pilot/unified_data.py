"""
Unified engine, piece B: contracts -> windows on one day timeline per (initiator, target, strike definition). Generic (Oct 20).
Any contract '<A> military action against/on <B> on|by <date>' joins a group keyed by pair + the fingerprint of its strike
DEFINITION in the rules text (pipeline/market_rules.json). Different definitions never share evidence (e.g. Saudi->Yemen
daily counts Saudi armed forces only; the older by-date template lacks that clause).
Every contract is a UTC interval: daily = its date in the rules' time zone; by-date = listing creation (market_meta.json) to
23:59 of its date in the rules' zone; a by-date YES resolved early ends at its resolution time. Mapped to whole days of the
group's zone: YES uses every touched day, NO only fully covered days. Walk-forward: a resolution counts only if resolved
before as_of (earliest resolved_at in predictions/brier_log.jsonl). Open status is never evidence.
  python pilot/unified_data.py   report: groups, windows, time zones, contradictions, smoke test of the forward pass
"""
import json, re, math, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent; PIPE = ROOT / "pipeline"; UTC = dt.timezone.utc
_M = "January|February|March|April|May|June|July|August|September|October|November|December"
MON = {m.lower(): i + 1 for i, m in enumerate(_M.split("|"))}
TPL = re.compile(r"^(?:Will (?:there be )?)?(?:an? |the )?(.+?)(?: take)? (?:military action (?:against|on)|target) (?:the )?(.+?) (on|by) (" + _M + r") (\d{1,2})(?:, (\d{4}))?\?\s*$", re.I)
ALIAS = {"saudiarabian": "saudiarabia"}
REGIONS = [("jerusalem|israel", "Asia/Jerusalem"), ("yemen", "Asia/Aden"), ("syria|damascus", "Asia/Damascus"), ("lebanon|beirut", "Asia/Beirut"),
           ("gulf", "Asia/Dubai"), ("arabia|riyadh", "Asia/Riyadh"), ("iran|tehran", "Asia/Tehran"), ("pakistan", "Asia/Karachi"),
           ("afghanistan|kabul", "Asia/Kabul"), ("amman|jordan", "Asia/Amman"), ("manama|bahrain", "Asia/Bahrain"), ("kuwait", "Asia/Kuwait"),
           ("doha|qatar", "Asia/Qatar"), ("muscat|oman", "Asia/Muscat"), ("cairo|egypt", "Africa/Cairo"), ("baghdad|iraq", "Asia/Baghdad"), ("abu dhabi|dubai|emirates", "Asia/Dubai"),
           ("sanaa|aden", "Asia/Aden"), ("kyiv|kiev|ukraine", "Europe/Kyiv"), ("moscow|russia", "Europe/Moscow"), ("beijing|china", "Asia/Shanghai"),
           ("taipei|taiwan", "Asia/Taipei"), ("seoul|korea", "Asia/Seoul"), ("tokyo|japan", "Asia/Tokyo"), ("manila|philippines", "Asia/Manila"),
           ("new delhi|delhi|india", "Asia/Kolkata"), ("islamabad", "Asia/Karachi"), ("caracas|venezuela", "America/Caracas"), ("havana|cuba", "America/Havana"),
           ("addis ababa|ethiopia|east africa|asmara|eritrea", "Africa/Addis_Ababa"), ("khartoum|sudan", "Africa/Khartoum"), ("ankara|istanbul|turkey", "Europe/Istanbul"),
           ("central european|paris|berlin|brussels", "Europe/Berlin"), ("london|british", "Europe/London"), ("warsaw|poland", "Europe/Warsaw"), ("central european", "Europe/Berlin"), ("eastern", "America/New_York"),
           ("pacific", "America/Los_Angeles"), ("coordinated universal|greenwich", "UTC")]
TZ = [(rf"(?:{r}) (?:standard |daylight |summer )?time", z) for r, z in REGIONS] + [
      (r"\bE[SD]?T\b", "America/New_York"), (r"\bCES?T\b", "Europe/Berlin"), (r"\bUTC\b|\bGMT\b", "UTC")]
# Named time zones only (a lookup table, not per-pair logic). Unknown zone -> contract skipped and counted, never guessed.

def T(s):
    x = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")); return x if x.tzinfo else x.replace(tzinfo=UTC)

def norm(x):
    k = re.sub(r"[^a-z]", "", re.sub(r"^(?:a|an|the)\s+", "", (x or "").strip().lower())); return ALIAS.get(k, k)   # leading article stripped (Oct 21: "a"/"an Arab country" split one collective)

def tz_of(desc):
    """Zone mentioned FIRST anywhere in the rules text (window clauses precede dispute clauses)."""
    t = re.sub(r"\s+", " ", desc or ""); hits = []
    for pat, z in TZ:
        m = re.search(pat, t, re.I)
        if m: hits.append((m.start(), z))
    return min(hits)[1] if hits else None

def pick_date(mon, day, year, created, known, today=None):
    if year:
        return dt.date(year, mon, day)
    c = []
    for y in range(2024, 2029):
        try: c.append(dt.date(y, mon, day))
        except ValueError: pass
    if created:
        ok = [d for d in c if d >= created.date() - dt.timedelta(2)]; return min(ok) if ok else None
    if known:
        ok = [d for d in c if d <= known.date() + dt.timedelta(1)]; return max(ok) if ok else None
    return min(c, key=lambda d: abs((d - today).days)) if today else None   # last resort: year nearest today

def load():
    rules = json.loads((PIPE / "market_rules.json").read_text()); meta = json.loads((PIPE / "market_meta.json").read_text())
    br = defaultdict(list)
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); br[str(r["market_id"])].append(r)
    feed = json.loads((PIPE / "classified_feed.json").read_text()); feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    open_ids = {str(m["market_id"]) for m in feed if not m.get("resolved")}
    out, skip = [], Counter()
    for mid, r in rules.items():
        m = TPL.match(r.get("question") or "")
        if not m: continue
        tz, fp = tz_of(r.get("description")), r.get("definition_fp")
        if not fp: skip["no definition paragraph"] += 1; continue
        if not tz: skip["no time zone in rules"] += 1; continue
        ca = (meta.get(mid) or {}).get("createdAt") or r.get("createdAt"); created = T(ca) if ca else None
        rs = br.get(mid); kts = [T(x["resolved_at"]) for x in rs if x.get("resolved_at")] if rs else []
        known = min(kts) if kts else None; outcome = int(rs[-1]["outcome"]) if rs and kts else None
        d = pick_date(MON[m.group(4).lower()], int(m.group(5)), int(m.group(6)) if m.group(6) else None, created, known, dt.date.today())
        if d is None: skip["date year undetermined"] += 1; continue
        z = ZoneInfo(tz); ds = dt.datetime.combine(d, dt.time(0), z).astimezone(UTC); de = dt.datetime.combine(d, dt.time(23, 59, 59), z).astimezone(UTC)
        kind = "daily" if m.group(3).lower() == "on" else "bydate"
        if kind == "daily": s, e = ds, de
        else:
            if not created: skip["by-date without creation time"] += 1; continue
            s, e = created, de
        if outcome == 1 and known and known < e: e = max(s, known)
        out.append({"id": mid, "pair": f"{norm(m.group(1))}->{norm(m.group(2))}", "kind": kind, "fp": fp, "tz": tz, "start": s, "end": e, "date": d,
                    "outcome": outcome, "known": known, "open": mid in open_ids and outcome is None, "question": r.get("question"),
                    "sfp": struct_fp(r.get("description"), m.group(1), m.group(2)), "members": members_of(r.get("description"))})
    return out, skip

def definition(desc):
    d = re.sub(r"\s+", " ", desc or ""); i = d.lower().find("qualifying military action refers to")
    if i < 0: return None
    j = min([k for k in (d.lower().find("the occurrence, attribution", i), d.lower().find("resolution source", i)) if k > 0] or [len(d)])
    return d[i:j].strip()

def struct_fp(desc, ini, ter):
    """Definition with the initiator and target names blanked: same kind of event, any target (links collectives to members)."""
    d = definition(desc)
    if not d: return None
    t = d.lower(); core = re.sub(r"^(an?|the) ", "", ter.strip().lower())
    t = re.sub(r"(?:an? |the )?(?:qualifying )?" + re.escape(core), "<T>", t)
    t = t.replace(ini.strip().lower(), "<A>")
    return __import__("hashlib").sha1(t.encode()).hexdigest()[:10]

def members_of(desc):
    m = re.search(r"Qualifying [A-Za-z ]+? (?:countries|states|nations) are(?: as follows)?: (.+?)\.(?:\s|$)", re.sub(r"\s+", " ", desc or ""), flags=re.I)
    return [norm(re.sub(r"^(?:and |the )+", "", x.strip())) for x in re.split(r",\s*|\s+and\s+", m.group(1)) if x.strip()] if m else None

def groups(cs):
    g = defaultdict(list)
    for c in cs: g[(c["pair"], c.get("sfp") or c["fp"])].append(c)   # same pair + same structural definition = one group (Oct 21)
    return g

def group_tz(group):
    d = [c for c in group if c["kind"] == "daily"]; return (d or group)[0]["tz"]

def windows(group, as_of):
    """-> (day0, T, [(a, b, y)]) on whole days of the group's zone; days 0..T-1 end with the day before as_of."""
    z = ZoneInfo(group_tz(group)); today = as_of.astimezone(z).date(); last = today - dt.timedelta(1); items = []
    for c in group:
        if c["outcome"] is None or not (c["known"] and c["known"] < as_of): continue
        s, e = c["start"].astimezone(z), c["end"].astimezone(z)
        if c["outcome"] == 1:
            a, b = s.date(), min(e.date(), last)
        else:
            a = s.date() if s.time() == dt.time(0) else s.date() + dt.timedelta(1)
            b = e.date() if e.time() >= dt.time(23, 59) else e.date() - dt.timedelta(1)
            b = min(b, last)
        if b >= a: items.append((a, b, c["outcome"]))
    if not items: return today, 0, []
    d0 = min(a for a, _, _ in items)
    return d0, (today - d0).days, [((a - d0).days, (b - d0).days, y) for a, b, y in items]

def contradictions(wins):
    quiet = set(); [quiet.update(range(a, b + 1)) for a, b, y in wins if y == 0]
    return [(a, b) for a, b, y in wins if y == 1 and set(range(a, b + 1)) <= quiet]

if __name__ == "__main__":
    import sys; sys.path.insert(0, str(Path(__file__).resolve().parent)); import unified as U
    cs, skip = load(); now = dt.datetime.now(UTC); print("skipped:", dict(skip))
    for (pair, fp), grp in sorted(groups(cs).items(), key=lambda kv: -len(kv[1])):
        k = Counter((c["kind"], c["outcome"]) for c in grp); d0, Tn, w = windows(grp, now); bad = contradictions(w)
        ll, pi = U.forward(Tn, w, math.log(2) / 100, math.log(2) / 30, 0.8, 0.05) if Tn else (0.0, None)
        print(f"--- {pair:28} def {fp} tz {group_tz(grp):16} | daily Y/N/open {k[('daily',1)]}/{k[('daily',0)]}/{k[('daily',None)]} | "
              f"by-date Y/N/open {k[('bydate',1)]}/{k[('bydate',0)]}/{k[('bydate',None)]} | timeline {d0} +{Tn}d, {len(w)} windows | "
              f"contradictions {bad or 'none'} | smoke loglik {ll:.1f}")

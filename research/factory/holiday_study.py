"""Holy Days and Hard Bargains: fast, research-only H1 exploratory study.

One command retrieves four years of ACLED remote events to a private cache,
generates Israel-local major Jewish holidays, includes zero-event days, and
fits a first-pass within-month Poisson model. NO raw notes are transmitted.
This is NOT a causal/dyadic holiday-effect result: the outcome is Israeli
remote-weapon events in Lebanon, using Actor1 as provisional weapons user.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import csv
import json
from pathlib import Path
import re
import shutil
import sys

from .holiday_acled import (
    OUT, ATTRIBUTION, file_for, checksum, atomic_json,
    credentials, get_token, fetch_one,
)

STUDY = OUT / "h1_multiyear"
COUNTRY = "Lebanon"
EVENT_TYPE = "Explosions/Remote violence"
ARMED = {"Air/drone strike", "Shelling/artillery/missile attack"}


def months(start, end):
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", start or "") or not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", end or ""):
        raise ValueError("Use YYYY-MM")
    cur, stop = date.fromisoformat(start+"-01"), date.fromisoformat(end+"-01")
    if stop < cur or (stop.year-cur.year)*12+stop.month-cur.month > 83:
        raise ValueError("Invalid range (maximum 84 months)")
    while cur <= stop:
        next_month = date(cur.year+(cur.month==12), cur.month%12+1, 1)
        yield cur, next_month-timedelta(days=1)
        cur = next_month


def major_holidays(year_start, year_end):
    """Predeclared Israel-observed Jewish dates; holy days begin sunset eve."""
    from pyluach.dates import HebrewDate
    holidays = (
        (7,1,"Rosh Hashanah I"), (7,2,"Rosh Hashanah II"),
        (7,10,"Yom Kippur"), (7,15,"Sukkot I"),
        (7,22,"Shemini Atzeret"), (1,15,"Pesach I"),
        (1,21,"Pesach VII"), (3,6,"Shavuot"),
    )
    out=defaultdict(list)
    for year in range(year_start+3758,year_end+3764):
        for month,day,name in holidays:
            civil=HebrewDate(year,month,day).to_pydate()
            if year_start<=civil.year<=year_end:
                out[civil].append(name)
    return dict(out)


def month_entry(out, begin, end):
    p=file_for(COUNTRY,str(begin),str(end),EVENT_TYPE,out=Path(out))
    return p.name,p


def manifest_at(out):
    path=Path(out)/"MANIFEST.json"
    if not path.exists():
        return {"attribution":ATTRIBUTION,"queries":{}}
    doc=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc.get("queries"),dict):
        raise ValueError("Invalid private ACLED study manifest")
    return doc


def reuse_october(begin, end, dest):
    """Copy the October 2024 pilot only after verifying its hash/row count."""
    if begin != date(2024,10,1) or end != date(2024,10,31):
        return None
    root_manifest=OUT/"MANIFEST.json"
    if not root_manifest.exists():
        return None
    original=file_for(COUNTRY,str(begin),str(end),EVENT_TYPE,out=OUT)
    old=json.loads(root_manifest.read_text(encoding="utf-8")).get("queries",{}).get(original.name)
    if not old or not original.is_file() or checksum(original)!=old.get("sha256"):
        return None
    if Path(old.get("file","")).resolve()!=original.resolve():
        return None
    n=sum(bool(line.strip()) for line in original.read_text(encoding="utf-8").splitlines())
    if n!=old.get("rows"):
        return None
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(original,dest)
    return {**old,"file":str(dest),"sha256":checksum(dest),"rows":n,
            "cache_source":"verified_2024_october_pilot"}


def acquire_months(start,end,*,out=STUDY,fetch=False,env_file=None,refresh=False):
    """Hash-checked, resumable; only --fetch authorizes network/API login."""
    out=Path(out);m=manifest_at(out);ready=downloaded=reused=0;missing=[]
    username=password=None;state=None
    for begin,finish in months(start,end):
        if finish>=date.today()-timedelta(days=7):
            raise ValueError("Recent dates disallowed (ACLED 7-day coding lag)")
        key,p=month_entry(out,begin,finish)
        old=m["queries"].get(key)
        if not refresh and old and p.is_file() and checksum(p)==old.get("sha256"):
            ready+=1;continue
        if not fetch:
            missing.append(key);continue
        prior=None if refresh else reuse_october(begin,finish,p)
        if prior:
            m["queries"][key]=prior;reused+=1
            atomic_json(out/"MANIFEST.json",m)
            continue
        if state is None:
            username,password=credentials(env_file)
            state=[get_token(username,password)]
        result=fetch_one(COUNTRY,str(begin),str(finish),EVENT_TYPE,
                         out=out,max_pages=50,state=state,
                         username=username,password=password)
        m["queries"][key]=result
        atomic_json(out/"MANIFEST.json",m)
        downloaded+=1
        print(f"ACLED {begin:%Y-%m}: {result['rows']} events, {result['pages']} page(s)",flush=True)
    return {"ready_months":ready,"newly_fetched_months":downloaded,
            "reused_2024_pilot_months":reused,"missing_months":missing}


def load_months(start,end,*,out=STUDY):
    out=Path(out);m=manifest_at(out)
    records=[];ids=set();metadata=[]
    for begin,finish in months(start,end):
        key,p=month_entry(out,begin,finish)
        entry=m["queries"].get(key)
        if not entry or not p.exists():
            raise ValueError("Missing ACLED cache "+key)
        if checksum(p)!=entry.get("sha256") or Path(entry.get("file","")).resolve()!=p.resolve():
            raise ValueError("Hash/path mismatch for "+key)
        n=0
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():continue
            e=json.loads(line)
            d=date.fromisoformat(str(e["event_date"]))
            if not begin<=d<=finish:raise ValueError("Event date outside month")
            eid=e.get("event_id_cnty")
            if eid and eid in ids:raise ValueError("Duplicate event ID across months")
            if eid:ids.add(eid)
            records.append(e);n+=1
        if n!=entry.get("rows"):raise ValueError("Month cache row count mismatch")
        metadata.append({"month":begin.strftime("%Y-%m"),"rows":n})
    return records,metadata


def is_israel_force(actor):
    return bool(re.match(r"^Military Forces of Israel\b",str(actor or "")))


def build_panel(events,start,end):
    intervals=list(months(start,end));first,last=intervals[0][0],intervals[-1][1]
    holidays=major_holidays(first.year,last.year)
    counts=Counter();excluded=Counter()
    for e in events:
        if e.get("event_type")!=EVENT_TYPE:
            excluded["event_type"]+=1;continue
        if str(e.get("time_precision"))!="1":
            excluded["date_imprecise"]+=1;continue
        if e.get("sub_event_type") not in ARMED:
            excluded["other_remote_type"]+=1;continue
        if not is_israel_force(e.get("actor1")):
            excluded["not_israel_actor1"]+=1;continue
        counts[date.fromisoformat(str(e["event_date"]))]+=1
    daily=[];d=first
    while d<=last:
        daily.append({
            "date":str(d),"events":counts[d],
            "holiday":int(d in holidays),
            "holiday_eve":int(d not in holidays and d+timedelta(days=1) in holidays),
            "holiday_names":";".join(holidays.get(d,[])),
            "year":d.year,"year_month":d.strftime("%Y-%m"),
            "weekday":d.weekday(),"iso_week":d.strftime("%G-W%V"),
        })
        d+=timedelta(days=1)
    qc={
        "raw_acled_events":len(events),
        "included_israeli_remote_events":sum(counts.values()),
        "excluded":dict(excluded),"days_in_panel":len(daily),
        "zero_event_days":sum(r["events"]==0 for r in daily),
        "holiday_days":sum(r["holiday"] for r in daily),
        "holiday_eves":sum(r["holiday_eve"] for r in daily),
    }
    if qc["raw_acled_events"]!=qc["included_israeli_remote_events"]+sum(excluded.values()):
        raise AssertionError("Counts do not reconcile")
    return daily,qc


def estimate(daily,*,variable="holiday",exclude_year=None):
    """First-pass PPML: within-year-month and weekday FE; weekly cluster SE."""
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    import statsmodels.formula.api as smf
    d=pd.DataFrame(daily)
    if exclude_year is not None:
        d=d.loc[d.year!=exclude_year].copy()
    if not len(d) or d["events"].sum()==0 or d[variable].sum()<4:
        return {"status":"not_estimable","variable":variable,"reason":"insufficient observations"}
    formula=("events ~ holiday + holiday_eve + C(year_month) + C(weekday)"
             if variable in ("holiday","holiday_eve")
             else f"events ~ {variable} + C(year_month) + C(weekday)")
    try:
        result=smf.glm(formula=formula,data=d,family=sm.families.Poisson()).fit(
            cov_type="cluster",cov_kwds={"groups":d["iso_week"]},
            maxiter=250,disp=0,
        )
        beta,se=float(result.params[variable]),float(result.bse[variable])
        if not (np.isfinite(beta) and np.isfinite(se)):
            raise ValueError("Nonfinite beta or SE")
        return {
            "status":"fit_exploratory","variable":variable,
            "n_days":int(len(d)),"observed_events":int(d["events"].sum()),
            "holiday_exposure_days":int(d[variable].sum()),
            "log_rate_beta":round(beta,5),"weekly_cluster_se":round(se,5),
            "irr":round(float(np.exp(beta)),4),
            "change_pct":round(float(100*np.expm1(beta)),2),
            "irr_95pct_ci":[round(float(np.exp(beta-1.96*se)),4),
                            round(float(np.exp(beta+1.96*se)),4)],
            "exploratory_p_value":round(float(result.pvalues[variable]),5),
            "n_week_clusters":int(d["iso_week"].nunique()),"formula":formula,
        }
    except (ValueError,ArithmeticError,RuntimeError,np.linalg.LinAlgError) as exc:
        return {"status":"not_estimable","variable":variable,
                "reason":type(exc).__name__}


def write_summary(daily,qc,models,*,out=STUDY,start,end):
    """Private daily counts/results only; no raw ACLED notes/source text."""
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    dest=out/"H1_DAILY_PANEL_PRIVATE.csv"
    cols=["date","events","holiday","holiday_eve","holiday_names",
          "year_month","weekday","iso_week"]
    with dest.open("w",newline="",encoding="utf-8") as fp:
        writer=csv.DictWriter(fp,fieldnames=cols);writer.writeheader()
        for row in daily:writer.writerow({k:row[k] for k in cols})
    import os
    os.chmod(dest,0o600)
    summary={
        "status":"exploratory_not_causal",
        "study":"Israeli Actor1 remote weapons-use events in Lebanon, H1 only",
        "date_range":[str(list(months(start,end))[0][0]),
                      str(list(months(start,end))[-1][1])],
        "holiday_dates":"Israel-local Rosh Hashanah 1-2, Yom Kippur, Sukkot 1, Shemini Atzeret, Pesach 1+7, Shavuot; computed with pyluach",
        "holiday_time_warning":"Jewish holidays start at sundown before civil holiday date; eve is analyzed separately",
        "quality":qc,"models":models,"attribution":ATTRIBUTION,
        "limitations":[
            "Actor1 is only a provisional user-of-weapons proxy",
            "Event location Lebanon is not proof that target is Hezbollah or a Lebanese actor",
            "No adversary-holiday test or shared-holiday truce test in this stage",
            "Results confounded by conflict intensity, strategic date selection and reporting shifts",
            "Calendar drift is limited; clustered standard errors do not deliver causal identification",
            "Licensed ACLED descriptions remain strictly local, not uploaded",
        ],
        "daily_panel_file":str(dest),
    }
    atomic_json(out/"H1_EXPLORATORY_RESULTS.json",summary)
    report=out/"H1_EXPLORATORY_README.md"
    lines=["# Holy Days — preliminary data result","",
           "Research diagnostic only: **not causal, not yet a paper finding**.","",
           f"ACLED events {qc['included_israeli_remote_events']} over {qc['days_in_panel']} days; {qc['holiday_days']} major holiday dates.",""]
    for name,fit in models.items():
        desc=(f"IRR {fit['irr']}; {fit['change_pct']}% event-rate difference; CI {fit['irr_95pct_ci']}" if fit.get("status")=="fit_exploratory"
              else f"not estimable: {fit.get('reason')}")
        lines.append(f"- {name}: {desc}")
    lines.extend(["","H1 only; target-side religion and dyadic direction remain unverified."])
    report.write_text("\n".join(lines)+"\n",encoding="utf-8")
    return summary


def execute(*,start="2022-01",end="2025-12",out=STUDY,fetch=False,
            env_file=None,refresh=False,sensitivity=False):
    acq=acquire_months(start,end,out=out,fetch=fetch,env_file=env_file,refresh=refresh)
    if acq["missing_months"]:
        return {"status":"missing_data",**acq,
                "next_action":"Add --fetch for month-by-month acquisition"}
    events,_=load_months(start,end,out=out)
    daily,qc=build_panel(events,start,end)
    holidays={date.fromisoformat(r["date"]) for r in daily if r["holiday"]}
    placebo=[{**r,"holiday_plus_21":
                int(date.fromisoformat(r["date"])-timedelta(days=21) in holidays)}
             for r in daily]
    models={
        "major_holiday":estimate(daily,variable="holiday"),
        "sundown_eve":estimate(daily,variable="holiday_eve"),
        "21_day_shift_placebo":estimate(placebo,variable="holiday_plus_21"),
    }
    if sensitivity:
        for y in sorted(set(r["year"] for r in daily)):
            models[f"major_holiday_without_{y}"]=estimate(daily,exclude_year=y)
    write_summary(daily,qc,models,out=out,start=start,end=end)
    return {
        "status":"exploratory_h1_result_generated",**acq,
        "data_quality":qc,"main_model":models["major_holiday"],
        "eve_model":models["sundown_eve"],
        "placebo_model":models["21_day_shift_placebo"],
        "results_file":str(Path(out)/"H1_EXPLORATORY_RESULTS.json"),
        "interpretation":"One-theater, actor-side observational study; no causal claim; no H2/H3 tested",
    }


def main(argv=None):
    p=argparse.ArgumentParser(description="One-command multiyear ACLED Jewish holiday H1 pilot")
    p.add_argument("--start",default="2022-01")
    p.add_argument("--end",default="2025-12")
    p.add_argument("--fetch",action="store_true",help="Authorize ACLED API network calls")
    p.add_argument("--env-file",type=Path)
    p.add_argument("--refresh",action="store_true")
    p.add_argument("--sensitivity",action="store_true",help="Also run leave-one-year-out tests (slower)")
    p.add_argument("--out",type=Path,default=STUDY)
    args=p.parse_args(argv)
    try:
        result=execute(start=args.start,end=args.end,out=args.out,
                       fetch=args.fetch,env_file=args.env_file,
                       refresh=args.refresh,sensitivity=args.sensitivity)
        print(json.dumps(result,indent=2,ensure_ascii=False))
        return 0 if result["status"]!="missing_data" else 2
    except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
        print("Holy Days H1 pilot stopped safely: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())

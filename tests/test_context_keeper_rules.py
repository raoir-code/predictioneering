"""Nov 4, 2026: context keeper date and attribution rules (pipeline/context_keeper.py)."""
import sys, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import context_keeper as CK

TODAY = dt.date(2026, 11, 4)
BODY = " Pakistan and Yemen: background text long enough to pass the minimum length check for a crisis context." * 2

def test_future_stamp_rejected():
    ok, why = CK._validate_candidate("old", "CRISIS CONTEXT (Updated through week ending November 7, 2026)." + BODY, "Pakistan-Yemen", TODAY)
    assert not ok and "after today" in why

def test_iso_and_yearless_stamps():
    assert CK._future_stamp("CRISIS CONTEXT (Israel-Syria dyad, updated 2026-10-31):", TODAY) is None
    assert CK._future_stamp("CRISIS CONTEXT (updated 2026-11-09):", TODAY) == "2026-11-09"
    assert CK._future_stamp("As of November 4, 2026, talks continue", TODAY) is None
    assert CK._future_stamp("as of November 20 the coalition", TODAY) == "November 20"
    assert CK._future_stamp("as of early November 2026, Israel and Iran", TODAY) is None     # a month and year, not a day

def test_scheduled_future_event_allowed():
    ok, _ = CK._validate_candidate("old", "CRISIS CONTEXT (as of November 3, 2026): a vote is scheduled for December 15, 2026." + BODY, "Pakistan-Yemen", TODAY)
    assert ok

def test_no_date_given_keeps_old_behaviour():
    ok, _ = CK._validate_candidate("old", "CRISIS CONTEXT (updated 2027-01-01)." + BODY, "Pakistan-Yemen")
    assert ok

if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"): f()
    print("context keeper rules: OK")

from datetime import date

from lib import logic as L
from lib import ui as U


def test_presc_compact(plan):
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=1)
    sq = L.find_ex(d, "A-superset-a:back-squat")
    txt = U.presc_compact(sq["prescription"]).replace("<b>", "").replace("</b>", "")
    assert txt == "4 × 3-6 · RIR 2 · rec 60-90″ · tempo 2-1-1-0"
    bulg = L.find_ex(L.new_draft(plan, "C", [], week=1, day=date(2026, 10, 23), now_ms=1), "C-legs:affondi-bulgari-bilanciere")
    assert "3 × 12</b> rip/gamba" in U.presc_compact(bulg["prescription"])
    assert U._short_rest("90-120'' → A1") == "90-120″"
    assert U._short_rest("-") is None

from datetime import date, datetime

import pytest

from lib import logic as L
from lib import plan as P

T0 = 1_760_000_000_000


def mk_log(plan, sid, day, sets_by_ex, *, alt=(), lid=None):
    """Crea un log finalizzato: sets_by_ex = {exerciseId: [(kg, reps), ...]}."""
    d = L.new_draft(plan, sid, [], week=1, day=date.fromisoformat(day), now_ms=T0)
    for ex in d["exercises"]:
        if ex["exerciseId"] in sets_by_ex:
            ex["usedAlternative"] = ex["exerciseId"] in alt
            ex["sets"] = [{"n": i + 1, "kg": kg, "reps": r, "done": True, "t": 1} for i, (kg, r) in enumerate(sets_by_ex[ex["exerciseId"]])]
    log = L.finalize(d, datetime(2026, 1, 1, 18, 30, 0))
    if lid:
        log["id"] = lid
    else:
        log["id"] = f"{day}_{sid}_183000"
    return log


def test_cycle_week():
    s = "2026-10-19"
    assert L.cycle_week("2026-10-17", s) == 1
    assert L.cycle_week("2026-10-19", s) == 1
    assert L.cycle_week("2026-10-25", s) == 1
    assert L.cycle_week("2026-10-26", s) == 2
    assert L.cycle_week("2026-12-14", s) == 9
    assert L.cycle_week("2026-10-26", None) == 1


def test_next_session(plan):
    assert L.next_session_id([], ["A", "B", "C"]) == "A"
    logs = [{"date": "2026-10-19", "sessionId": "A"}, {"date": "2026-10-21", "sessionId": "B"}]
    assert L.next_session_id(logs, ["A", "B", "C"]) == "C"
    logs.append({"date": "2026-10-23", "sessionId": "C"})
    assert L.next_session_id(logs, ["A", "B", "C"]) == "A"


def test_e1rm():
    assert L.e1rm(100, 5) == pytest.approx(116.7, abs=0.05)
    assert L.e1rm(100, 1) == 100
    assert L.e1rm(0, 5) is None and L.e1rm(None, 5) is None and L.e1rm(50, 20) is None


def test_new_draft_prescription_and_prefill(plan):
    d = L.new_draft(plan, "A", [], week=3, day=date(2026, 11, 2), now_ms=T0)
    sq = L.find_ex(d, "A-superset-a:back-squat")
    # senza storico: minimo del range (un ✓ veloce non registra rip mai fatte)
    assert len(sq["sets"]) == 4 and sq["sets"][0]["kg"] == 100 and sq["sets"][0]["reps"] == 3
    assert sq["prescription"]["tempo"] == "2-1-1-0" and sq["prescription"]["restSec"] == 90
    assert sq["warmupSets"][0] == {"kg": 20, "reps": 8, "done": False}
    pull = L.find_ex(d, "A-superset-a:trazioni-prona")
    assert len(pull["sets"]) == 5 and pull["sets"][0]["kg"] == 0 and pull["kgMode"] == "bw"
    wu = L.find_ex(d, "A-warmup:kettlebell-swing")
    assert wu["sets"] == [] and wu["blockType"] == "warmup"
    assert d["vestKg"] is None


def test_vest_session_c(plan):
    d = L.new_draft(plan, "C", [], week=5, day=date(2026, 11, 16), now_ms=T0)
    assert d["vestKg"] == 10
    for key in ("C-vest:trazioni-zavorrate-prona", "C-vest:push-up-zavorrati", "C-vest:dip-zavorrati"):
        ex = L.find_ex(d, key)
        assert all(s["kg"] == 10 for s in ex["sets"])
    assert len(L.find_ex(d, "C-vest:trazioni-zavorrate-prona")["sets"]) == 4
    L.propagate_vest(d, 12)
    assert L.find_ex(d, "C-vest:dip-zavorrati")["sets"][0]["kg"] == 12
    L.set_alternative(d, "C-vest:dip-zavorrati", True, [])
    assert L.find_ex(d, "C-vest:dip-zavorrati")["sets"][0]["kg"] == 0


def test_prefill_same_session_first(plan):
    la = mk_log(plan, "A", "2026-10-19", {"stacco-rumeno-1-gamba-kb": [(12, 10), (12, 9), (12, 8)]})
    lc = mk_log(plan, "C", "2026-10-23", {"stacco-rumeno-1-gamba-kb": [(16, 6), (16, 6)]})
    d = L.new_draft(plan, "A", [la, lc], week=1, day=date(2026, 10, 26), now_ms=T0)
    ex = L.find_ex(d, "A-circuit:stacco-rumeno-1-gamba-kb")
    assert [s["reps"] for s in ex["sets"]] == [10, 9, 8]  # A con A, non la C più recente
    assert ex["sets"][1]["prev"] == {"kg": 12, "reps": 9}
    assert ex["prevSource"]["sessionId"] == "A"
    # nessuna A precedente per l'esercizio → usa l'ultima in altre sedute
    d2 = L.new_draft(plan, "A", [lc], week=1, day=date(2026, 10, 26), now_ms=T0)
    assert L.find_ex(d2, "A-circuit:stacco-rumeno-1-gamba-kb")["sets"][0]["kg"] == 16


def test_apply_events_idempotent_lww(plan):
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    rev0 = d["rev"]
    key = "A-superset-a:back-squat"
    ev = {"id": "e1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 100, "reps": 5, "done": True, "t": T0 + 10}
    acc, rej, ch = L.apply_events(d, [ev], T0 + 20)
    assert acc == ["e1"] and ch and d["rev"] == rev0 + 1
    s = L.find_ex(d, key)["sets"][0]
    assert s["done"] and s["reps"] == 5 and s["rev"] == d["rev"]
    # ripetuto (rerun / reinvio) → nessun cambiamento
    acc, rej, ch = L.apply_events(d, [ev], T0 + 30)
    assert not ch and d["rev"] == rev0 + 1
    # evento più vecchio non sovrascrive
    old = dict(ev, id="e0", reps=3, t=T0 + 5)
    L.apply_events(d, [old], T0 + 40)
    assert L.find_ex(d, key)["sets"][0]["reps"] == 5
    # bozza diversa o esercizio sconosciuto → rifiutato
    _, rej, _ = L.apply_events(d, [dict(ev, id="x", draftId="altro"), dict(ev, id="y", exKey="no:no")], T0)
    assert rej == ["x", "y"]


def test_apply_events_add_remove_extra_set(plan):
    d = L.new_draft(plan, "C", [], week=1, day=date(2026, 10, 23), now_ms=T0)
    key = "C-legs:stacco-rumeno-1-gamba-kb"
    assert len(L.find_ex(d, key)["sets"]) == 2
    L.apply_events(d, [{"id": "a", "draftId": d["id"], "exKey": key, "type": "add", "n": 3, "t": T0}], T0)
    assert len(L.find_ex(d, key)["sets"]) == 3 and L.find_ex(d, key)["sets"][2]["extra"]
    L.apply_events(d, [{"id": "r", "draftId": d["id"], "exKey": key, "type": "remove", "n": 3, "t": T0 + 1}], T0)
    assert len(L.find_ex(d, key)["sets"]) == 2
    # serie oltre la fine (evento set su n=3) crea la serie extra
    L.apply_events(d, [{"id": "s", "draftId": d["id"], "exKey": key, "type": "set", "n": 3, "kg": 12, "reps": 10, "done": True, "t": T0 + 2}], T0)
    assert L.find_ex(d, key)["sets"][2]["done"]


def test_merge_drafts_per_set(plan):
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    import copy
    a, b = copy.deepcopy(d), copy.deepcopy(d)
    key = "A-superset-a:back-squat"
    L.apply_events(a, [{"id": "1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 100, "reps": 6, "done": True, "t": T0 + 1}], T0)
    L.apply_events(b, [{"id": "2", "draftId": d["id"], "exKey": key, "type": "set", "n": 2, "kg": 100, "reps": 5, "done": True, "t": T0 + 2}], T0)
    m = L.merge_drafts(a, b)
    sets = L.find_ex(m, key)["sets"]
    assert sets[0]["done"] and sets[1]["done"] and sets[1]["reps"] == 5
    assert m["rev"] > max(a["rev"], b["rev"])
    assert L.merge_drafts(a, {"id": "other"}) is a


def test_pending_count(plan):
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    synced = d["rev"]
    key = "A-superset-a:back-squat"
    L.apply_events(d, [{"id": "1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 100, "reps": 6, "done": True, "t": T0 + 1}], T0)
    assert L.pending_count(d, synced) == 1
    assert L.pending_count(d, d["rev"]) == 0


def test_finalize_keeps_only_done_sets_and_prescription(plan):
    d = L.new_draft(plan, "B", [], week=1, day=date(2026, 10, 21), now_ms=T0)
    key = "B-superset-b:military-press"
    L.apply_events(d, [{"id": "1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 30, "reps": 10, "done": True, "t": T0 + 1}], T0)
    L.find_ex(d, "B-warmup:kb-deadlift")["done"] = True
    log = L.finalize(d, datetime(2026, 10, 21, 19, 5, 7))
    hh = datetime.fromtimestamp(T0 / 1000).strftime("%H%M%S")
    assert log["id"] == f"2026-10-21_B_{hh}" and L.log_path(log) == f"logs/2026-10-21_B_{hh}.json"
    assert log["draftId"] == d["id"]
    mp = next(e for e in log["exercises"] if e["key"] == key)
    assert mp["sets"] == [{"n": 1, "kg": 30, "reps": 10, "done": True}]
    assert mp["prescription"]["tempo"] == "3-0-1-0" and mp["prescription"]["phase"] == 2
    assert "rir" not in mp["sets"][0]
    assert next(e for e in log["exercises"] if e["key"] == "B-warmup:kb-deadlift")["done"]
    assert log["planVersion"] == 1 and not log["imported"]
    assert L.validate_log(log) == []


def test_stats_and_records_exclude_warmup(plan):
    l1 = mk_log(plan, "A", "2026-10-19", {"back-squat": [(100, 5), (100, 5)], "kettlebell-swing": [(12, 12)]})
    l2 = mk_log(plan, "A", "2026-10-26", {"back-squat": [(100, 6), (100, 6)], "trazioni-prona": [(0, 5), (0, 6)]})
    recs = L.personal_records([l1, l2])
    assert "kettlebell-swing" not in recs
    assert recs["back-squat"]["best_e1rm"]["value"] == pytest.approx(120.0)
    assert recs["trazioni-prona"]["best_e1rm"] is None and recs["trazioni-prona"]["reps_at_load"]["0"]["reps"] == 6
    msgs = L.new_records(l2, [l1])
    assert any("e1RM" in m for m in msgs)
    tr = L.tracked_exercises([l1, l2])
    assert set(tr) == {"back-squat", "trazioni-prona"}


def test_alternative_excluded_from_records(plan):
    l1 = mk_log(plan, "A", "2026-10-19", {"back-squat": [(70, 8)]}, alt=("back-squat",))
    assert "back-squat" not in L.personal_records([l1])
    assert L.exercise_history([l1], "back-squat") == []
    assert len(L.exercise_history([l1], "back-squat", include_alt=True)) == 1


def test_declines_same_session_only(plan):
    logs = [mk_log(plan, "A", "2026-10-19", {"back-squat": [(100, 6)] * 4}),
            mk_log(plan, "C", "2026-10-21", {"stacco-rumeno-1-gamba-kb": [(12, 10)]}),
            mk_log(plan, "A", "2026-10-26", {"back-squat": [(100, 5)] * 4}),
            mk_log(plan, "A", "2026-11-02", {"back-squat": [(100, 4)] * 4})]
    dec = L.declines(logs)
    assert len(dec) == 1 and dec[0]["exerciseId"] == "back-squat" and dec[0]["sessionId"] == "A"
    logs[-1] = mk_log(plan, "A", "2026-11-02", {"back-squat": [(100, 6)] * 4})
    assert L.declines(logs) == []


def test_declines_bodyweight_uses_mean_reps(plan):
    logs = [mk_log(plan, "B", f"2026-10-{d}", {"trazioni-supina": s}) for d, s in
            (("19", [(0, 5)] * 4), ("21", [(0, 5)] * 4 + [(0, 3)]), ("23", [(0, 4)] * 4))]
    assert [x["exerciseId"] for x in L.declines(logs)] == ["trazioni-supina"]


def test_suggest_progression(plan):
    l1 = mk_log(plan, "A", "2026-10-19", {"back-squat": [(100, 6)] * 4})
    s = L.suggest_progression(plan, "A", "back-squat", [l1])
    assert s["kind"] == "increase" and s["suggestKg"] == 110 and "110" in s["text"]
    l2 = mk_log(plan, "A", "2026-10-19", {"back-squat": [(100, 6), (100, 6), (100, 5), (100, 4)]})
    s2 = L.suggest_progression(plan, "A", "back-squat", [l2])
    assert s2["kind"] == "hold" and "6-6-5-4" in s2["text"]
    l3 = mk_log(plan, "C", "2026-10-23", {"affondi-bulgari-bilanciere": [(20, 12)] * 3})
    assert L.suggest_progression(plan, "C", "affondi-bulgari-bilanciere", [l3])["suggestKg"] == 30
    l4 = mk_log(plan, "A", "2026-10-19", {"panca-inclinata-bilanciere": [(50, 12)] * 4})
    s4 = L.suggest_progression(plan, "A", "panca-inclinata-bilanciere", [l4])
    assert s4["suggestKg"] is None and "spalla" in s4["text"]
    assert L.suggest_progression(plan, "A", "back-squat", []) is None


def test_retarget_week(plan):
    d = L.new_draft(plan, "C", [], week=1, day=date(2026, 10, 23), now_ms=T0)
    assert len(L.find_ex(d, "C-vest:trazioni-zavorrate-prona")["sets"]) == 4
    L.retarget_week(d, plan, 3)
    assert len(L.find_ex(d, "C-vest:trazioni-zavorrate-prona")["sets"]) == 5 and d["cycleWeek"] == 3
    L.retarget_week(d, plan, 5)
    assert d["vestKg"] == 10 and L.find_ex(d, "C-vest:push-up-zavorrati")["sets"][0]["kg"] == 10


def test_format_sets():
    assert L.format_sets([{"kg": 100, "reps": 5}, {"kg": 100, "reps": 5}, {"kg": 90, "reps": 6}]) == "100: 5-5 | 90: 6"
    assert L.format_sets([{"kg": None, "reps": 12}]) == "12"


def test_bodyweight_weekly():
    e = L.upsert_bodyweight([], "2026-10-19", 75.4)
    e = L.upsert_bodyweight(e, "2026-10-21", 75.0)
    e = L.upsert_bodyweight(e, "2026-10-21", 75.2)  # stessa data → sostituisce
    e = L.upsert_bodyweight(e, "2026-10-27", 74.5)
    w = L.weekly_bodyweight(e)
    assert w == [{"weekStart": "2026-10-19", "mean": 75.3, "n": 2}, {"weekStart": "2026-10-26", "mean": 74.5, "n": 1}]


def test_csv_roundtrip(plan):
    l1 = mk_log(plan, "A", "2026-10-19", {"back-squat": [(100, 5), (102.5, 4)]})
    l1["notes"] = "ok, spalla bene"
    txt = L.logs_to_csv([l1])
    back = L.csv_to_logs(txt)
    assert len(back) == 1 and back[0]["id"] == l1["id"] and back[0]["notes"] == "ok, spalla bene"
    sq = next(e for e in back[0]["exercises"] if e["exerciseId"] == "back-squat")
    assert [(s["kg"], s["reps"]) for s in sq["sets"]] == [(100, 5), (102.5, 4)]
    with pytest.raises(ValueError):
        L.csv_to_logs("a,b\n1,2\n")


def test_validate_log():
    assert L.validate_log({"id": "../x", "date": "2026-01-01", "sessionId": "A", "exercises": []})
    assert L.validate_log({"id": "x", "date": "nope", "sessionId": "A", "exercises": []})


def test_finalize_id_is_stable_for_same_draft(plan):
    """Bug: l'id dipendeva dall'ora del salvataggio → un nuovo tentativo creava un duplicato."""
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    a = L.finalize(d, datetime(2026, 10, 19, 19, 0, 0))
    b = L.finalize(d, datetime(2026, 10, 19, 19, 0, 47))
    assert a["id"] == b["id"]


def test_prefill_without_history_uses_min_reps(plan):
    d = L.new_draft(plan, "B", [], week=1, day=date(2026, 10, 21), now_ms=T0)
    assert L.find_ex(d, "B-superset-b:military-press")["sets"][0]["reps"] == 6
    assert L.find_ex(d, "B-superset-a:stacco-da-terra")["sets"][0]["reps"] == 4


def test_kg_step(plan):
    get = lambda s, e: P.find_exercise(plan, s, e)[1]
    assert L.kg_step(get("A", "back-squat")) == 2.5
    assert L.kg_step(get("A", "stacco-rumeno-1-gamba-kb")) == 4
    assert L.kg_step(get("C", "trazioni-zavorrate-prona")) == 1
    assert L.kg_step(get("A", "trazioni-prona")) == 1
    assert L.kg_step({**get("A", "back-squat"), "kgStep": 5}) == 5
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    assert L.find_ex(d, "A-circuit:suitcase-carry-kb")["kgStep"] == 4


def test_warmup_rounds(plan):
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    assert L.find_ex(d, "A-warmup:kettlebell-swing")["rounds"] == [False, False]
    assert "rounds" not in L.find_ex(d, "A-cooldown:stretching-defaticamento")


def test_is_saved_draft(plan):
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    log = L.finalize(d, datetime(2026, 10, 19, 19, 0, 0))
    assert L.is_saved_draft(d, [log]) and not L.is_saved_draft(d, []) and not L.is_saved_draft(None, [log])


def test_reconcile_drafts_keeps_unsent_sets(plan):
    """Bug 4: 'Ricarica dal server' sostituiva la bozza locale perdendo le serie non inviate."""
    import copy
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    remote = copy.deepcopy(d)
    key = "A-superset-a:back-squat"
    L.apply_events(d, [{"id": "1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 100, "reps": 5, "done": True, "t": T0 + 1}], T0)
    L.apply_events(remote, [{"id": "2", "draftId": d["id"], "exKey": key, "type": "set", "n": 2, "kg": 100, "reps": 5, "done": True, "t": T0 + 2}], T0)
    m = L.reconcile_drafts(d, remote, local_unsynced=True)
    assert [s["done"] for s in L.find_ex(m, key)["sets"][:2]] == [True, True]
    assert L.reconcile_drafts(None, remote, False) is remote
    assert L.reconcile_drafts(d, None, True) is d
    assert L.reconcile_drafts(d, None, False) is None
    other = dict(remote, id="altra")
    assert L.reconcile_drafts(d, other, True) is d and L.reconcile_drafts(d, other, False) is other


def test_apply_emom_and_rounds(plan):
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    assert L.apply_emom(d, "A-warmup", 6, T0)
    sw = L.find_ex(d, "A-warmup:kettlebell-swing")
    assert sw["rounds"] == [True, True] and sw["done"]
    assert L.find_ex(d, "A-warmup:goblet-squat-kb")["rounds"] == [True, False]
    assert not L.apply_emom(d, "A-warmup", 6, T0)  # idempotente
    L.set_rounds(d, "A-warmup:kb-halo", [True, True], T0)
    assert L.find_ex(d, "A-warmup:kb-halo")["done"]


def test_rest_label_uneven_superset(plan):
    """Superset con serie diverse: dopo l'ultima di A1 il recupero non deve dire 'poi A1'."""
    d = L.new_draft(plan, "A", [], week=3, day=date(2026, 11, 2), now_ms=T0)  # A1 4 serie, A2 5 serie
    keys = ["A-superset-a:back-squat", "A-superset-a:trazioni-prona"]
    assert L.rest_label(d, keys, 0) == "poi A2 Trazioni corpo libero presa prona"
    for s in L.find_ex(d, keys[0])["sets"]:
        s["done"] = True
    for s in L.find_ex(d, keys[1])["sets"][:4]:
        s["done"] = True
    assert L.rest_label(d, keys, 1) == "fine blocco"   # 5ª trazione: nessun "poi A1"
    L.find_ex(d, keys[1])["sets"][3]["done"] = False
    assert L.rest_label(d, keys, 1) == "poi la serie successiva"

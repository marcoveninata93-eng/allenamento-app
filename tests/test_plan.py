import copy

import pytest

from lib import plan as P


def test_default_plan_is_valid_and_has_no_history(plan):
    assert P.validate_plan(plan) == []
    assert "history" not in plan
    assert P.session_ids(plan) == ["A", "B", "C"]


def test_shared_ids_across_sessions(plan):
    cat = P.exercise_catalog(plan)
    assert set(cat["trazioni-prona"]["sessions"]) == {"A", "B"}
    assert set(cat["stacco-rumeno-1-gamba-kb"]["sessions"]) == {"A", "C"}


@pytest.mark.parametrize("week,a2,c,vest", [(1, 4, 4, 8), (2, 4, 4, 8), (3, 5, 5, 8), (5, 5, 4, 10), (8, 5, 5, 10), (11, 5, 5, 10)])
def test_pullup_table(plan, week, a2, c, vest):
    _, a2_ex = P.find_exercise(plan, "A", "trazioni-prona")
    _, c_ex = P.find_exercise(plan, "C", "trazioni-zavorrate-prona")
    assert P.target_sets(plan, a2_ex, week) == a2
    assert P.target_sets(plan, c_ex, week) == c
    assert P.vest_kg(plan, week) == vest
    assert P.target_reps(plan, c_ex, week) == (4, 4)


def test_non_progression_sets(plan):
    _, sq = P.find_exercise(plan, "A", "back-squat")
    assert P.target_sets(plan, sq, 5) == 4


@pytest.mark.parametrize("txt,sec", [("60-90'' → A2", 90), ("30''", 30), ("90-120'' → A1", 120),
                                     ("60'' tra le gambe", 60), ("-", None), ("resto del min.", None), ("2'", 120), (None, None)])
def test_parse_rest(txt, sec):
    assert P.parse_rest_seconds(txt) == sec


def test_parse_rir():
    assert P.parse_rir_target("2-3") == 2
    assert P.parse_rir_target("-") is None


def test_metric_kind(plan):
    get = lambda s, e: P.find_exercise(plan, s, e)[1]
    assert P.metric_kind(get("A", "back-squat")) == "strength"
    assert P.metric_kind(get("A", "trazioni-prona")) == "bodyweight"
    assert P.metric_kind(get("C", "push-up-zavorrati")) == "bodyweight"
    assert P.metric_kind(get("A", "stacco-rumeno-1-gamba-kb")) == "reps_at_load"
    assert P.metric_kind(get("A", "suitcase-carry-kb")) == "reps_at_load"


def test_resolve_video(plan, videos):
    _, sq = P.find_exercise(plan, "A", "back-squat")
    v = P.resolve_video(sq, videos)
    assert v["embed"] and "youtube.com/watch" in v["embed"]
    va = P.resolve_video(sq, videos, alternative=True)
    assert va["embed"] and va["embed"] != v["embed"]
    _, st = P.find_exercise(plan, "A", "stretching-defaticamento")
    vs = P.resolve_video(st, videos)
    assert vs["embed"] is None and vs["search"].startswith(P.YT_SEARCH)
    assert P.resolve_video(sq, None)["embed"] is None


def test_youtube_id():
    assert P.youtube_id("https://www.youtube.com/watch?v=bDCeXbMJVNs") == "bDCeXbMJVNs"
    assert P.youtube_id("https://youtu.be/abcdefg") == "abcdefg"
    assert P.youtube_id("https://www.youtube.com/results?search_query=x") is None


def test_validate_detects_errors(plan):
    bad = copy.deepcopy(plan)
    bad["sessions"][0]["blocks"][1]["exercises"][0]["sets"] = 0
    bad["sessions"][0]["blocks"][1]["exercises"][0]["repsMin"] = 9
    bad["sessions"][1]["id"] = "A"
    errs = P.validate_plan(bad)
    assert any("'sets'" in e for e in errs)
    assert any("repsMin > repsMax" in e for e in errs)
    assert any("duplicato" in e for e in errs)
    assert P.validate_plan([]) and P.validate_plan({"sessions": []})


def test_update_exercise_and_new_version(plan):
    newp = P.update_exercise(plan, "A", "A-superset-a", "back-squat", {"sets": 5, "notes": "nuova", "startingLoadKg": "110"})
    _, sq = P.find_exercise(newp, "A", "back-squat")
    assert sq["sets"] == 5 and sq["startingLoadKg"] == 110 and sq["notes"] == "nuova"
    _, orig = P.find_exercise(plan, "A", "back-squat")
    assert orig["sets"] == 4  # originale intatto
    v2 = P.new_version(newp, [1])
    assert v2["version"] == 2 and P.validate_plan(v2) == []
    with pytest.raises(ValueError):
        P.update_exercise(plan, "A", "A-superset-a", "back-squat", {"id": "x"})
    with pytest.raises(KeyError):
        P.update_exercise(plan, "A", "A-superset-a", "nope", {"sets": 3})


def test_update_all_sessions(plan):
    newp = P.update_exercise(plan, "A", "A-superset-a", "trazioni-prona", {"notes": "N"}, all_sessions=True)
    assert P.find_exercise(newp, "B", "trazioni-prona")[1]["notes"] == "N"


def test_parse_plan_text(plan):
    data, errs = P.parse_plan_text("{bad")
    assert data is None and "JSON non valido" in errs[0]
    data, errs = P.parse_plan_text(P.plan_to_text(plan))
    assert errs == [] and data["sessions"]


def test_cue_short_and_notes_without_sheet_refs(plan):
    for s, b, e in P.iter_exercises(plan):
        assert e.get("cue"), f"{s['id']}/{e['id']} senza cue"
        assert len(e["cue"]) <= 50, e["cue"]
        assert "foglio" not in (e.get("notes") or "")


def test_migrate_plan_adds_missing_fields_and_keeps_user_edits(plan):
    old = copy.deepcopy(plan)
    for _, _, e in P.iter_exercises(old):
        e.pop("cue", None)
        e.pop("kgStep", None)
    _, sq = P.find_exercise(old, "A", "back-squat")
    sq["notes"] = "Carico e regola di progressione: foglio 'Carichi e Progressione'. Mia nota personale."
    sq["sets"] = 5
    _, tr = P.find_exercise(old, "C", "trazioni-zavorrate-prona")
    tr["cue"] = "cue mia"
    tr["kgStep"] = 2
    m = P.migrate_plan(old, plan)
    _, msq = P.find_exercise(m, "A", "back-squat")
    assert msq["cue"] == P.find_exercise(plan, "A", "back-squat")[1]["cue"]
    assert msq["kgStep"] == 5 and msq["sets"] == 5
    assert msq["notes"] == "Mia nota personale."
    _, mtr = P.find_exercise(m, "C", "trazioni-zavorrate-prona")
    assert mtr["cue"] == "cue mia" and mtr["kgStep"] == 2
    # la cue dipende dalla seduta quando lo stesso esercizio compare in più sedute
    assert P.find_exercise(m, "A", "trazioni-prona")[1]["cue"] == P.find_exercise(plan, "A", "trazioni-prona")[1]["cue"]
    assert P.find_exercise(m, "B", "trazioni-prona")[1]["cue"] == P.find_exercise(plan, "B", "trazioni-prona")[1]["cue"]
    # esercizio nuovo dell'utente (non nel piano predefinito): nessun campo inventato, passo dal codice
    old["sessions"][0]["blocks"][1]["exercises"].append({"id": "front-squat", "name": "Front squat", "sets": 3,
                                                          "startingLoadKg": 70})
    m2 = P.migrate_plan(old, plan)
    fs = P.find_exercise(m2, "A", "front-squat")[1]
    assert "cue" not in fs and P.kg_step(fs) == 5
    assert P.find_exercise(old, "A", "back-squat")[1].get("cue") is None  # originale intatto
    assert P.validate_plan(m) == []


def test_validate_kg_step(plan):
    bad = copy.deepcopy(plan)
    bad["sessions"][0]["blocks"][1]["exercises"][0]["kgStep"] = 0
    assert any("kgStep" in e for e in P.validate_plan(bad))


def test_update_exercise_cue_and_kg_step(plan):
    newp = P.update_exercise(plan, "A", "A-superset-a", "back-squat", {"cue": "Nuova", "kgStep": None})
    _, sq = P.find_exercise(newp, "A", "back-squat")
    assert sq["cue"] == "Nuova" and "kgStep" not in sq and P.kg_step(sq) == 5

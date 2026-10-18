"""Logica pura dell'app: settimana di ciclo, rotazione sedute, bozza, precompilazione,
eventi delle serie, e1RM/PR, peggioramenti, suggerimenti di progressione, CSV."""
from __future__ import annotations

import copy
import csv
import io
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from . import plan as P

SCHEMA = 2
KG_STEP = P.OTHER_STEP


# ======================================================================= date
def parse_date(v: str | date | None) -> date | None:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def cycle_week(d: date | str, start: date | str | None, weeks: int = 8) -> int:
    """Settimana di ciclo (1-based) calcolata dalla data di inizio. Prima dell'inizio → 1.
    Può superare `weeks` (ciclo finito): la UI lo segnala."""
    d = parse_date(d)
    start = parse_date(start)
    if not start or not d or d < start:
        return 1
    return (d - start).days // 7 + 1


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ======================================================================= rotazione
def sort_logs(logs: Iterable[dict]) -> list[dict]:
    return sorted(logs, key=lambda l: (str(l.get("date", "")), str(l.get("finishedAt") or l.get("startedAt") or ""), l.get("id", "")))


def next_session_id(logs: list[dict], order: list[str]) -> str:
    done = [l for l in sort_logs(logs) if not l.get("skipped") and l.get("sessionId") in order]
    if not done:
        return order[0]
    last = done[-1]["sessionId"]
    return order[(order.index(last) + 1) % len(order)]


def last_log_of_session(logs: list[dict], session_id: str) -> dict | None:
    cands = [l for l in sort_logs(logs) if l.get("sessionId") == session_id and not l.get("skipped")]
    return cands[-1] if cands else None


# ======================================================================= metriche
def e1rm(kg: float | None, reps: float | None) -> float | None:
    """Epley: kg × (1 + rip/30). Solo per carichi > 0 e 1-15 ripetizioni."""
    if not kg or not reps or kg <= 0 or reps <= 0:
        return None
    if reps == 1:
        return float(kg)
    if reps > 15:
        return None
    return round(kg * (1 + reps / 30.0), 1)


def is_countable(ex: dict) -> bool:
    """Esclude riscaldamento/defaticamento ed esercizi non tracciati da volume e PR."""
    return ex.get("blockType") not in P.NON_COUNTABLE_BLOCKS and ex.get("track", True) is not False


def work_sets(ex: dict) -> list[dict]:
    return [s for s in ex.get("sets", []) if s.get("done", True) and s.get("reps") not in (None, 0) and not s.get("warmup")]


def ex_kind(ex: dict) -> str:
    return ex.get("kind") or "reps_at_load"


def session_stats(ex: dict) -> dict | None:
    ws = work_sets(ex)
    if not ws:
        return None
    kind = ex_kind(ex)
    kgs = [float(s.get("kg") or 0) for s in ws]
    reps = [float(s.get("reps") or 0) for s in ws]
    out = {
        "kind": kind,
        "n_sets": len(ws),
        "max_kg": max(kgs),
        "total_reps": sum(reps),
        "best_reps": max(reps),
        "mean_reps": round(sum(reps) / len(reps), 2),
        "volume": round(sum(k * r for k, r in zip(kgs, reps)), 1),
        "best_e1rm": None,
    }
    if kind == "strength":
        vals = [e1rm(k, r) for k, r in zip(kgs, reps)]
        vals = [v for v in vals if v]
        out["best_e1rm"] = max(vals) if vals else None
    # ripetizioni migliori al carico massimo usato
    out["reps_at_max_kg"] = max(r for k, r in zip(kgs, reps) if k == out["max_kg"])
    return out


def series_key(ex: dict) -> str:
    return ex["exerciseId"] + ("@alt" if ex.get("usedAlternative") else "")


def exercise_history(logs: list[dict], exercise_id: str, session_id: str | None = None,
                     include_alt: bool = False) -> list[dict]:
    rows = []
    for log in sort_logs(logs):
        if log.get("skipped"):
            continue
        if session_id and log.get("sessionId") != session_id:
            continue
        for ex in log.get("exercises", []):
            if ex.get("exerciseId") != exercise_id or not is_countable(ex):
                continue
            if ex.get("usedAlternative") and not include_alt:
                continue
            st = session_stats(ex)
            if st:
                rows.append({"date": log["date"], "logId": log.get("id"), "sessionId": log.get("sessionId"),
                             "name": ex.get("name"), "usedAlternative": bool(ex.get("usedAlternative")),
                             "sets": work_sets(ex), **st})
    return rows


def tracked_exercises(logs: list[dict]) -> dict[str, dict]:
    """exerciseId → {name, kind, n} per gli esercizi con almeno una serie di lavoro."""
    out: dict[str, dict] = {}
    for log in logs:
        for ex in log.get("exercises", []):
            if is_countable(ex) and not ex.get("usedAlternative") and work_sets(ex):
                d = out.setdefault(ex["exerciseId"], {"name": ex.get("name"), "kind": ex_kind(ex), "n": 0})
                d["n"] += 1
    return out


def personal_records(logs: list[dict]) -> dict[str, dict]:
    recs: dict[str, dict] = {}
    for log in sort_logs(logs):
        if log.get("skipped"):
            continue
        for ex in log.get("exercises", []):
            if not is_countable(ex) or ex.get("usedAlternative"):
                continue
            kind = ex_kind(ex)
            r = recs.setdefault(ex["exerciseId"], {"name": ex.get("name"), "kind": kind, "best_e1rm": None,
                                                   "max_kg": None, "reps_at_load": {}, "best_volume": None})
            for s in work_sets(ex):
                kg = float(s.get("kg") or 0)
                reps = float(s.get("reps") or 0)
                if kind == "strength":
                    v = e1rm(kg, reps)
                    if v and (r["best_e1rm"] is None or v > r["best_e1rm"]["value"]):
                        r["best_e1rm"] = {"value": v, "kg": kg, "reps": reps, "date": log["date"]}
                    if r["max_kg"] is None or kg > r["max_kg"]["kg"] or (kg == r["max_kg"]["kg"] and reps > r["max_kg"]["reps"]):
                        r["max_kg"] = {"kg": kg, "reps": reps, "date": log["date"]}
                key = _fmt_kg(kg)
                cur = r["reps_at_load"].get(key)
                if cur is None or reps > cur["reps"]:
                    r["reps_at_load"][key] = {"kg": kg, "reps": reps, "date": log["date"]}
            st = session_stats(ex)
            if st and kind == "strength" and (r["best_volume"] is None or st["volume"] > r["best_volume"]["value"]):
                r["best_volume"] = {"value": st["volume"], "date": log["date"]}
    return recs


def new_records(log: dict, prior_logs: list[dict]) -> list[str]:
    """Messaggi dei PR battuti nella seduta `log` rispetto a `prior_logs`."""
    before = personal_records([l for l in prior_logs if l.get("id") != log.get("id")])
    after = personal_records([l for l in prior_logs if l.get("id") != log.get("id")] + [log])
    msgs = []
    for exid, a in after.items():
        b = before.get(exid)
        if not any(e.get("exerciseId") == exid for e in log.get("exercises", [])):
            continue
        if a["kind"] == "strength" and a["best_e1rm"]:
            if not b or not b["best_e1rm"] or a["best_e1rm"]["value"] > b["best_e1rm"]["value"]:
                if b and b["best_e1rm"]:
                    msgs.append(f"{a['name']}: nuovo e1RM {a['best_e1rm']['value']:g} kg "
                                f"({_fmt_kg(a['best_e1rm']['kg'])}×{a['best_e1rm']['reps']:g})")
        for k, v in a["reps_at_load"].items():
            if b and k in b["reps_at_load"] and v["reps"] > b["reps_at_load"][k]["reps"]:
                label = "zavorra " if a["kind"] == "bodyweight" else ""
                msgs.append(f"{a['name']}: {v['reps']:g} rip a {label}{k} kg (prima {b['reps_at_load'][k]['reps']:g})")
            elif b and b["reps_at_load"] and k not in b["reps_at_load"]:
                prev_max = max(x["kg"] for x in b["reps_at_load"].values())
                if v["kg"] > prev_max:
                    msgs.append(f"{a['name']}: carico mai usato prima, {k} kg × {v['reps']:g}")
    return msgs


def _score(row: dict) -> tuple:
    if row["kind"] == "strength" and row.get("best_e1rm"):
        return (row["best_e1rm"],)
    return (row["max_kg"], row["mean_reps"])


def declines(logs: list[dict]) -> list[dict]:
    """Esercizi peggiorati 2 sedute di fila: stesso exerciseId nella stessa seduta, solo serie di lavoro."""
    out = []
    pairs = set()
    for log in logs:
        for ex in log.get("exercises", []):
            if is_countable(ex) and not ex.get("usedAlternative"):
                pairs.add((ex["exerciseId"], log.get("sessionId")))
    for exid, sid in sorted(pairs):
        hist = exercise_history(logs, exid, session_id=sid)
        if len(hist) < 3:
            continue
        a, b, c = hist[-3:]
        if _score(c) < _score(b) < _score(a):
            out.append({"exerciseId": exid, "sessionId": sid, "name": c["name"],
                        "dates": [a["date"], b["date"], c["date"]],
                        "values": [_score(a), _score(b), _score(c)]})
    return out


# ======================================================================= progressione
def suggest_progression(plan: dict, session_id: str, exercise_id: str, logs: list[dict]) -> dict | None:
    """Suggerimento (mai automatico) basato sulle ripetizioni completate nell'ultima seduta uguale."""
    hist = exercise_history(logs, exercise_id, session_id=session_id)
    if not hist:
        hist = exercise_history(logs, exercise_id)
    if not hist:
        return None
    last = hist[-1]
    rule = P.get_rule(plan, exercise_id)
    found = P.find_exercise(plan, session_id, exercise_id)
    ex_def = found[1] if found else {}
    kg = last["max_kg"]
    at_kg = [s for s in last["sets"] if float(s.get("kg") or 0) == kg]
    if rule and rule.get("trigger"):
        trig = rule["trigger"]
        hit = sum(1 for s in at_kg if (s.get("reps") or 0) >= trig["reps"])
        if hit >= trig["sets"]:
            nxt = rule.get("next", {})
            sugg_kg = nxt.get("loadKg")
            if sugg_kg is None and nxt.get("loadKgDelta"):
                sugg_kg = kg + nxt["loadKgDelta"]
            if sugg_kg is not None and ex_def:
                # al passo dell'attrezzo, ma mai sotto l'ultimo carico registrato
                sugg_kg = max(snap_kg(ex_def, sugg_kg), kg)
            txt = f"Ultima volta {trig['sets']}×{trig['reps']} a {_fmt_kg(kg)} kg completato. Regola: {rule['rule']}"
            if trig.get("rirMin") is not None:
                txt += f" (vale se avevi ancora ~{trig['rirMin']} rip di margine: controlla le note)"
            if rule.get("blockedBy"):
                txt += f" Attenzione: non salire di carico se c'è {rule['blockedBy']}."
            sugg = sugg_kg if sugg_kg != kg else None
            short = f"Prova {_fmt_kg(sugg)} kg" if sugg is not None else "Obiettivo raggiunto: vedi la regola"
            return {"kind": "increase", "text": txt, "suggestKg": sugg, "short": short}
        reps_txt = "-".join(f"{s.get('reps'):g}" if isinstance(s.get('reps'), float) else str(s.get("reps")) for s in at_kg)
        return {"kind": "hold", "suggestKg": None,
                "short": f"Resta a {_fmt_kg(kg)} kg, punta a {trig['sets']}×{trig['reps']}",
                "text": f"Ultima volta {_fmt_kg(kg)} kg: {reps_txt}. Resta su questo carico e aggiungi ripetizioni "
                        f"fino a {trig['sets']}×{trig['reps']}."}
    rmax = ex_def.get("repsMax")
    target = int(ex_def.get("sets") or 0)
    if rmax and target and last["kind"] != "bodyweight":
        hit = sum(1 for s in at_kg if (s.get("reps") or 0) >= rmax)
        if hit >= target:
            return {"kind": "increase", "suggestKg": None, "short": "Obiettivo raggiunto: valuta un aumento",
                    "text": f"Ultima volta {target}×{rmax} a {_fmt_kg(kg)} kg completato: valuta un aumento o una variante più difficile."}
    return None


# ======================================================================= bozza
def _prev_lookup(logs: list[dict], session_id: str, exercise_id: str, used_alt: bool) -> tuple[dict | None, dict | None]:
    """Ultima esecuzione dello stesso esercizio nella STESSA seduta (A con A); se non c'è,
    l'ultima in qualsiasi seduta."""
    best_same = best_any = None
    for log in sort_logs(logs):
        if log.get("skipped"):
            continue
        for ex in log.get("exercises", []):
            if ex.get("exerciseId") != exercise_id or bool(ex.get("usedAlternative")) != used_alt:
                continue
            if not [s for s in ex.get("sets", []) if s.get("done", True)]:
                continue
            best_any = (log, ex)
            if log.get("sessionId") == session_id:
                best_same = (log, ex)
    return best_same or best_any or (None, None)


def kg_mode(ex: dict) -> str:
    if ex.get("loadFrom") == "giubbotto":
        return "vest"
    if ex.get("bodyweight"):
        return "bw"
    if ex.get("startingLoadKg") is None:
        return "none"
    return "free"


def kg_step(ex: dict) -> float:
    """Passo dei tasti ±: campo 'kgStep' del piano, altrimenti dal tipo di attrezzo
    (bilanciere 5 kg, kettlebell 4 kg, giubbotto/zavorra 1 kg, resto 2,5 kg)."""
    return P.kg_step(ex)


def snap_kg(ex: dict, kg: Any) -> Any:
    """Carico arrotondato al passo dell'esercizio (es. multipli di 5 per il bilanciere)."""
    return P.round_kg(kg, kg_step(ex), P.equipment(ex))


def make_prescription(plan: dict, ex: dict, week: int) -> dict:
    rmin, rmax = P.target_reps(plan, ex, week)
    return {
        "setsTarget": P.target_sets(plan, ex, week), "setsText": ex.get("setsText"), "repsMin": rmin,
        "repsMax": rmax, "repsUnit": ex.get("repsUnit", "rip"), "tempo": ex.get("tempo"), "rir": ex.get("rir"),
        "rest": ex.get("rest"), "restSec": P.parse_rest_seconds(ex.get("rest")), "phase": ex.get("phase"),
        "startingLoadKg": ex.get("startingLoadKg"),
    }


def build_sets(ex_def: dict, presc: dict, prev_ex: dict | None, vest: float | None, n: int) -> list[dict]:
    mode = kg_mode(ex_def)
    prev_sets = [s for s in (prev_ex or {}).get("sets", []) if s.get("done", True)]
    out = []
    for i in range(n):
        ps = prev_sets[i] if i < len(prev_sets) else (prev_sets[-1] if prev_sets else None)
        prev = {"kg": ps.get("kg"), "reps": ps.get("reps")} if (ps and i < len(prev_sets)) else None
        if mode == "vest":
            kg = vest
        elif mode == "bw":
            kg = ps.get("kg") if ps and ps.get("kg") is not None else 0
        elif mode == "none":
            kg = ps.get("kg") if ps else None
        else:
            # lo storico si ripropone com'è (anche 102,5); solo il carico iniziale del piano va al passo
            kg = ps.get("kg") if ps and ps.get("kg") is not None else snap_kg(ex_def, ex_def.get("startingLoadKg"))
        reps = ps.get("reps") if ps and ps.get("reps") else (presc.get("repsMin") or presc.get("repsMax"))
        out.append({"n": i + 1, "kg": kg, "reps": reps, "done": False, "t": 0, "rev": 0, "prev": prev})
    return out


def new_draft(plan: dict, session_id: str, logs: list[dict], *, week: int, day: date, now_ms: int,
              vest: float | None = None, week_auto: int | None = None) -> dict:
    sess = P.get_session(plan, session_id)
    if vest is None:
        vest = P.vest_kg(plan, week)
    exercises = []
    for b in sess["blocks"]:
        for e in b["exercises"]:
            presc = make_prescription(plan, e, week)
            plog, pex = _prev_lookup(logs, session_id, e["id"], False)
            entry = {
                "key": f"{b['id']}:{e['id']}", "exerciseId": e["id"], "name": e["name"], "code": e.get("code"),
                "blockId": b["id"], "blockType": b.get("type"), "track": e.get("track", True),
                "kind": P.metric_kind(e), "kgMode": kg_mode(e), "kgStep": kg_step(e), "painCheck": e.get("painCheck"),
                "loadFrom": e.get("loadFrom"), "bodyweight": bool(e.get("bodyweight")),
                "prescription": presc, "usedAlternative": False, "alternative": e.get("alternative"),
                "done": False, "pain": None, "note": "", "t": 0,
                "prevSource": {"date": plog["date"], "logId": plog.get("id"), "sessionId": plog.get("sessionId")} if plog else None,
            }
            if e.get("track", True) is not False and b.get("type") not in P.NON_COUNTABLE_BLOCKS:
                entry["sets"] = build_sets(e, presc, pex, vest, presc["setsTarget"])
            else:
                entry["sets"] = []
                if b.get("type") == "warmup":
                    entry["rounds"] = [False] * int(e.get("sets") or 1)
            if e.get("warmupSets"):
                entry["warmupSets"] = [{"kg": w["kg"], "reps": w["reps"], "done": False} for w in e["warmupSets"]]
            exercises.append(entry)
    return {
        "schema": SCHEMA, "status": "draft", "id": f"d{now_ms}-{session_id}", "sessionId": session_id,
        "sessionTitle": sess.get("title"), "planVersion": plan.get("version", 1), "date": day.isoformat(),
        "startedAt": now_ms, "updatedAt": now_ms, "rev": 1, "cycleWeek": week,
        "cycleWeekAuto": week_auto if week_auto is not None else week, "vestKg": vest if _uses_vest(sess) else None,
        "blockIndex": 0, "bodyweightKg": None, "energy": None, "tennis": "", "notes": "", "exercises": exercises,
    }


def _uses_vest(sess: dict) -> bool:
    return any(e.get("loadFrom") == "giubbotto" for b in sess["blocks"] for e in b["exercises"])


def find_ex(draft: dict, key: str) -> dict | None:
    for e in draft.get("exercises", []):
        if e["key"] == key:
            return e
    return None


def bump(draft: dict, now_ms: int) -> int:
    draft["rev"] = int(draft.get("rev", 0)) + 1
    draft["updatedAt"] = now_ms
    return draft["rev"]


def apply_events(draft: dict, events: list[dict], now_ms: int) -> tuple[list[str], list[str], bool]:
    """Applica gli eventi inviati dal telefono (✓ serie, aggiungi/togli serie).
    Idempotente: ogni serie è 'last-writer-wins' sul timestamp t del tap."""
    accepted, rejected = [], []
    changed = False
    for ev in events or []:
        eid = ev.get("id")
        if ev.get("draftId") != draft.get("id"):
            rejected.append(eid)
            continue
        ex = find_ex(draft, ev.get("exKey", ""))
        if ex is None:
            rejected.append(eid)
            continue
        typ = ev.get("type", "set")
        n = int(ev.get("n") or 0)
        t = int(ev.get("t") or 0)
        sets = ex.setdefault("sets", [])
        if typ == "set":
            if n < 1 or n > 20:
                rejected.append(eid)
                continue
            while len(sets) < n:
                tmpl = dict(sets[-1]) if sets else {"kg": None, "reps": None}
                sets.append({"n": len(sets) + 1, "kg": tmpl.get("kg"), "reps": tmpl.get("reps"),
                             "done": False, "t": 0, "rev": 0, "prev": None, "extra": True})
            s = sets[n - 1]
            if t > int(s.get("t") or 0):
                s["kg"] = _num(ev.get("kg"))
                s["reps"] = _num(ev.get("reps"))
                s["done"] = bool(ev.get("done", True))
                s["t"] = t
                changed = True
                s["rev"] = draft.get("rev", 0) + 1
            accepted.append(eid)
        elif typ == "add":
            if len(sets) < min(n, 20):
                tmpl = dict(sets[-1]) if sets else {"kg": None, "reps": None}
                sets.append({"n": len(sets) + 1, "kg": tmpl.get("kg"), "reps": tmpl.get("reps"),
                             "done": False, "t": 0, "rev": 0, "prev": None, "extra": True})
                changed = True
            accepted.append(eid)
        elif typ == "remove":
            if sets and len(sets) == n and not sets[-1].get("done"):
                sets.pop()
                changed = True
            accepted.append(eid)
        else:
            rejected.append(eid)
    if changed:
        bump(draft, now_ms)
    return accepted, rejected, changed


def set_states(draft: dict) -> dict[str, int]:
    """'exKey|n' → t della serie (per dire al telefono cosa il server ha già)."""
    out = {}
    for ex in draft.get("exercises", []):
        for s in ex.get("sets", []):
            if s.get("t"):
                out[f"{ex['key']}|{s['n']}"] = int(s["t"])
    return out


def merge_drafts(local: dict, remote: dict) -> dict:
    """Unisce due versioni della stessa bozza (conflitto SHA): per ogni serie vince il tap più recente."""
    if not remote or remote.get("id") != local.get("id"):
        return local
    merged = copy.deepcopy(local)
    for rex in remote.get("exercises", []):
        lex = find_ex(merged, rex["key"])
        if lex is None:
            merged["exercises"].append(copy.deepcopy(rex))
            continue
        lsets = lex.setdefault("sets", [])
        for rs in rex.get("sets", []):
            i = rs["n"] - 1
            while len(lsets) <= i:
                lsets.append(copy.deepcopy(rs))
            if int(rs.get("t") or 0) > int(lsets[i].get("t") or 0):
                lsets[i] = copy.deepcopy(rs)
        if int(rex.get("t") or 0) > int(lex.get("t") or 0):
            for f in ("done", "pain", "note", "usedAlternative", "t"):
                lex[f] = rex.get(f)
    merged["rev"] = max(int(local.get("rev", 0)), int(remote.get("rev", 0))) + 1
    return merged


def pending_count(draft: dict, synced_rev: int) -> int:
    n = 0
    for ex in draft.get("exercises", []):
        for s in ex.get("sets", []):
            if s.get("t") and int(s.get("rev") or 0) > synced_rev:
                n += 1
    return n if draft.get("rev", 0) > synced_rev else 0


def propagate_vest(draft: dict, vest: float | None) -> None:
    draft["vestKg"] = vest
    for ex in draft["exercises"]:
        if ex.get("kgMode") == "vest" and not ex.get("usedAlternative"):
            for s in ex.get("sets", []):
                if not s.get("done"):
                    s["kg"] = vest


def set_alternative(draft: dict, key: str, used: bool, logs: list[dict]) -> None:
    ex = find_ex(draft, key)
    if ex is None:
        return
    ex["usedAlternative"] = used
    if used:
        ex["kind"] = "reps_at_load"
    for s in ex.get("sets", []):
        if not s.get("done"):
            if used and ex.get("kgMode") == "vest":
                s["kg"] = 0
            elif not used and ex.get("kgMode") == "vest":
                s["kg"] = draft.get("vestKg")


def draft_progress(draft: dict) -> tuple[int, int]:
    done = total = 0
    for ex in draft.get("exercises", []):
        if ex.get("sets"):
            total += len(ex["sets"])
            done += sum(1 for s in ex["sets"] if s.get("done"))
        else:
            total += 1
            done += 1 if ex.get("done") else 0
    return done, total


# ======================================================================= salvataggio log
def finalize(draft: dict, now: datetime) -> dict:
    """Trasforma la bozza in log definitivo: tiene solo le serie confermate."""
    d = copy.deepcopy(draft)
    # id stabile derivato dalla bozza (ora di inizio): un nuovo tentativo di salvataggio
    # della stessa bozza produce lo stesso file, mai un duplicato
    started = d.get("startedAt")
    if isinstance(started, (int, float)) and started > 0:
        hhmmss = datetime.fromtimestamp(started / 1000, now.tzinfo).strftime("%H%M%S")
    else:
        hhmmss = now.strftime("%H%M%S")
    log = {
        "schema": SCHEMA, "id": f"{d['date']}_{d['sessionId']}_{hhmmss}", "status": "done",
        "date": d["date"], "sessionId": d["sessionId"], "sessionTitle": d.get("sessionTitle"),
        "planVersion": d.get("planVersion"), "cycleWeek": d.get("cycleWeek"),
        "cycleWeekAuto": d.get("cycleWeekAuto"), "vestKg": d.get("vestKg"),
        "startedAt": d.get("startedAt"), "finishedAt": now.isoformat(timespec="seconds"),
        "bodyweightKg": d.get("bodyweightKg"), "energy": d.get("energy"), "tennis": d.get("tennis") or "",
        "notes": d.get("notes") or "", "imported": False, "draftId": d.get("id"), "exercises": [],
    }
    for ex in d["exercises"]:
        sets = [{"n": s["n"], "kg": s.get("kg"), "reps": s.get("reps"), "done": True,
                 **({"extra": True} if s.get("extra") else {})}
                for s in ex.get("sets", []) if s.get("done")]
        out = {k: ex.get(k) for k in ("key", "exerciseId", "name", "code", "blockId", "blockType", "track",
                                       "kind", "kgMode", "painCheck", "prescription", "usedAlternative",
                                       "alternative", "pain", "note")}
        out["done"] = bool(ex.get("done")) or bool(sets)
        out["sets"] = sets
        if ex.get("warmupSets"):
            out["warmupSets"] = ex["warmupSets"]
        if not out["usedAlternative"]:
            out.pop("alternative")
        log["exercises"].append(out)
    return log


def log_path(log: dict) -> str:
    return f"logs/{log['id']}.json"


def summarize_log(log: dict) -> str:
    parts = []
    for ex in log.get("exercises", []):
        ws = work_sets(ex)
        if not ws or not is_countable(ex):
            continue
        parts.append(f"{ex.get('code') or ''} {ex['name']}: {format_sets(ws)}".strip())
    return " · ".join(parts)


def _fmt_kg(kg: Any) -> str:
    if kg is None:
        return "–"
    f = float(kg)
    return f"{int(f)}" if f.is_integer() else f"{f:g}"


def fmt_kg(kg: Any) -> str:
    return _fmt_kg(kg)


def format_sets(sets: list[dict]) -> str:
    """Formato del diario: "100: 5-5-5-4" (raggruppa per carico)."""
    if not sets:
        return ""
    groups: list[tuple[Any, list]] = []
    for s in sets:
        kg = s.get("kg")
        r = s.get("reps")
        r = int(r) if isinstance(r, float) and r.is_integer() else r
        if groups and groups[-1][0] == kg:
            groups[-1][1].append(r)
        else:
            groups.append((kg, [r]))
    return " | ".join((f"{_fmt_kg(kg)}: " if kg not in (None, 0) else "") + "-".join(str(x) for x in reps) for kg, reps in groups)


def _num(v: Any) -> float | int | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f):
        return None
    return int(f) if f.is_integer() else round(f, 2)


# ======================================================================= peso corporeo
def weekly_bodyweight(entries: list[dict]) -> list[dict]:
    buckets: dict[date, list[float]] = defaultdict(list)
    for e in entries:
        d = parse_date(e.get("date"))
        if d and e.get("kg"):
            buckets[week_start(d)].append(float(e["kg"]))
    return [{"weekStart": k.isoformat(), "mean": round(sum(v) / len(v), 2), "n": len(v)} for k, v in sorted(buckets.items())]


def upsert_bodyweight(entries: list[dict], d: date | str, kg: float) -> list[dict]:
    d = parse_date(d).isoformat()
    out = [e for e in entries if e.get("date") != d]
    out.append({"date": d, "kg": round(float(kg), 2)})
    return sorted(out, key=lambda e: e["date"])


# ======================================================================= CSV / backup
CSV_FIELDS = ["logId", "date", "sessionId", "planVersion", "cycleWeek", "vestKg", "bodyweightKg", "energy",
              "tennis", "sessionNotes", "blockId", "blockType", "exerciseId", "exerciseName", "code", "kind",
              "usedAlternative", "exerciseDone", "pain", "exerciseNote", "setN", "kg", "reps"]


def logs_to_csv(logs: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    w.writeheader()
    for log in sort_logs(logs):
        base = {"logId": log.get("id"), "date": log.get("date"), "sessionId": log.get("sessionId"),
                "planVersion": log.get("planVersion"), "cycleWeek": log.get("cycleWeek"),
                "vestKg": log.get("vestKg"), "bodyweightKg": log.get("bodyweightKg"), "energy": log.get("energy"),
                "tennis": log.get("tennis"), "sessionNotes": log.get("notes")}
        for ex in log.get("exercises", []):
            exb = {**base, "blockId": ex.get("blockId"), "blockType": ex.get("blockType"),
                   "exerciseId": ex.get("exerciseId"), "exerciseName": ex.get("name"), "code": ex.get("code"),
                   "kind": ex.get("kind"), "usedAlternative": int(bool(ex.get("usedAlternative"))),
                   "exerciseDone": int(bool(ex.get("done"))), "pain": ex.get("pain"), "exerciseNote": ex.get("note")}
            sets = ex.get("sets") or []
            if not sets:
                w.writerow({**exb, "setN": "", "kg": "", "reps": ""})
            for s in sets:
                w.writerow({**exb, "setN": s.get("n"), "kg": s.get("kg"), "reps": s.get("reps")})
    return buf.getvalue()


def csv_to_logs(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    missing = {"logId", "date", "sessionId", "exerciseId"} - set(reader.fieldnames or [])
    if missing:
        raise ValueError(f"CSV senza colonne obbligatorie: {', '.join(sorted(missing))}")
    logs: dict[str, dict] = {}
    for row in reader:
        lid = row["logId"]
        log = logs.get(lid)
        if log is None:
            log = logs[lid] = {
                "schema": SCHEMA, "id": lid, "status": "done", "date": row["date"], "sessionId": row["sessionId"],
                "planVersion": _num(row.get("planVersion")), "cycleWeek": _num(row.get("cycleWeek")),
                "vestKg": _num(row.get("vestKg")), "bodyweightKg": _num(row.get("bodyweightKg")),
                "energy": _num(row.get("energy")), "tennis": row.get("tennis") or "",
                "notes": row.get("sessionNotes") or "", "imported": False, "importedFrom": "csv", "exercises": []}
        key = f"{row.get('blockId')}:{row['exerciseId']}"
        ex = next((e for e in log["exercises"] if e["key"] == key), None)
        if ex is None:
            ex = {"key": key, "exerciseId": row["exerciseId"], "name": row.get("exerciseName"),
                  "code": row.get("code"), "blockId": row.get("blockId"), "blockType": row.get("blockType"),
                  "track": True, "kind": row.get("kind") or "reps_at_load",
                  "usedAlternative": row.get("usedAlternative") in ("1", "True", "true"),
                  "done": row.get("exerciseDone") in ("1", "True", "true"), "pain": _num(row.get("pain")),
                  "note": row.get("exerciseNote") or "", "sets": []}
            log["exercises"].append(ex)
        if row.get("setN"):
            ex["sets"].append({"n": int(float(row["setN"])), "kg": _num(row.get("kg")), "reps": _num(row.get("reps")), "done": True})
    return list(logs.values())


def validate_log(log: Any) -> list[str]:
    errs = []
    if not isinstance(log, dict):
        return ["log non è un oggetto"]
    for f in ("id", "date", "sessionId", "exercises"):
        if f not in log:
            errs.append(f"manca '{f}'")
    if "date" in log:
        try:
            parse_date(log["date"])
        except ValueError:
            errs.append(f"data non valida: {log['date']}")
    if not isinstance(log.get("exercises", []), list):
        errs.append("'exercises' deve essere una lista")
    if "id" in log and ("/" in str(log["id"]) or ".." in str(log["id"])):
        errs.append("id non valido")
    return errs


def retarget_week(draft: dict, plan: dict, week: int) -> None:
    """Cambio manuale della settimana di ciclo: aggiorna serie previste (tabella trazioni) e giubbotto
    per gli esercizi non ancora iniziati."""
    draft["cycleWeek"] = week
    vest_started = any(s.get("done") for ex in draft["exercises"] if ex.get("kgMode") == "vest" for s in ex.get("sets", []))
    if draft.get("vestKg") is not None and not vest_started:
        v = P.vest_kg(plan, week)
        if v is not None:
            propagate_vest(draft, v)
    for ex in draft["exercises"]:
        found = P.find_exercise(plan, draft["sessionId"], ex["exerciseId"], ex.get("blockId"))
        if not found or any(s.get("done") or s.get("t") for s in ex.get("sets", [])):
            continue
        _, e = found
        presc = make_prescription(plan, e, week)
        ex["prescription"] = presc
        if ex.get("sets"):
            n = presc["setsTarget"]
            sets = ex["sets"]
            while len(sets) < n:
                last = dict(sets[-1])
                last.update({"n": len(sets) + 1, "done": False, "t": 0, "rev": 0, "prev": None})
                sets.append(last)
            del sets[n:]


def is_saved_draft(draft: dict | None, logs: list[dict]) -> bool:
    """True se la bozza è già diventata una seduta salvata (stesso draftId in un log)."""
    return bool(draft) and any(l.get("draftId") == draft.get("id") for l in logs)


def reconcile_drafts(local: dict | None, remote: dict | None, local_unsynced: bool) -> dict | None:
    """'Ricarica dal server' senza perdere le modifiche non ancora inviate."""
    if local is None:
        return remote
    if remote is None:
        return local if local_unsynced else None
    if remote.get("id") == local.get("id"):
        return merge_drafts(local, remote)
    return local if local_unsynced else remote


def set_rounds(draft: dict, key: str, rounds: list[bool], now_ms: int) -> None:
    ex = find_ex(draft, key)
    if ex is None:
        return
    ex["rounds"] = [bool(r) for r in rounds]
    ex["done"] = bool(rounds) and all(rounds)
    ex["t"] = now_ms


def apply_emom(draft: dict, block_id: str, done_minutes: int, now_ms: int) -> bool:
    """Minuti EMOM completati → spunta il giro dell'esercizio di quel minuto (mai toglie spunte)."""
    exs = [e for e in draft.get("exercises", []) if e.get("blockId") == block_id and "rounds" in e]
    if not exs or done_minutes <= 0:
        return False
    changed = False
    for m in range(int(done_minutes)):
        ex = exs[m % len(exs)]
        r = m // len(exs)
        if r < len(ex["rounds"]) and not ex["rounds"][r]:
            rounds = list(ex["rounds"])
            rounds[r] = True
            set_rounds(draft, ex["key"], rounds, now_ms)
            changed = True
    return changed


def rest_label(draft: dict, keys: list[str], idx: int) -> str:
    """Etichetta del recupero dopo la prossima serie dell'esercizio keys[idx] in un superset/circuito:
    il prossimo esercizio del blocco che ha ancora serie da fare; se nessuno, la serie successiva
    dello stesso esercizio (es. la 5ª trazione da sola); altrimenti fine blocco."""
    exs = [find_ex(draft, k) for k in keys]
    undone = lambda e: sum(1 for s in (e or {}).get("sets", []) if not s.get("done"))
    for j in range(1, len(exs)):
        e = exs[(idx + j) % len(exs)]
        if e and e.get("sets") and undone(e) > 0:
            return f"poi {e.get('code') or ''} {e['name']}".replace("  ", " ")
    if undone(exs[idx]) > 1:
        return "poi la serie successiva"
    return "fine blocco"


def _next_set(ex: dict, skip: int = 0) -> dict | None:
    undone = [s for s in ex.get("sets", []) if not s.get("done")]
    return undone[skip] if len(undone) > skip else None


def _reps_txt(ex: dict, s: dict | None) -> str:
    presc = ex.get("prescription") or {}
    r = (s or {}).get("reps")
    if r in (None, ""):
        r = presc.get("repsMin")
    unit = (presc.get("repsUnit") or "rip").strip()
    return f"× {_fmt_kg(r)}" + ("" if unit == "rip" else f" {unit}")


def rest_info(draft: dict, keys: list[str], idx: int) -> dict:
    """Cosa viene dopo il recupero che parte con la prossima serie di keys[idx]
    (stessa logica di rest_label): {label, code, name, set, reps} per il pannello del timer."""
    exs = [find_ex(draft, k) for k in keys]
    undone = lambda e: sum(1 for s in (e or {}).get("sets", []) if not s.get("done"))
    for j in range(1, len(exs)):
        e = exs[(idx + j) % len(exs)]
        if e and e.get("sets") and undone(e) > 0:
            s = _next_set(e)
            return {"label": f"poi {e.get('code') or ''} {e['name']}".replace("  ", " "), "key": e["key"], "code": e.get("code") or "",
                    "name": e["name"], "set": s["n"] if s else None, "reps": _reps_txt(e, s)}
    me = exs[idx] if exs else None
    if me and undone(me) > 1:
        s = _next_set(me, 1)
        return {"label": "poi la serie successiva", "key": me["key"], "code": me.get("code") or "", "name": me["name"],
                "set": s["n"] if s else None, "reps": _reps_txt(me, s)}
    return {"label": "fine blocco", "key": None, "code": "", "name": "Fine blocco", "set": None, "reps": ""}


def active_exercise(draft: dict, keys: list[str]) -> int:
    """In un superset/circuito: l'esercizio a cui tocca adesso. Si alternano: quello con meno serie
    fatte (a parità, il primo nell'ordine del blocco); se sono tutti finiti, il primo."""
    best, best_done = 0, None
    for i, k in enumerate(keys):
        e = find_ex(draft, k)
        if not e or not e.get("sets"):
            continue
        done = sum(1 for s in e["sets"] if s.get("done"))
        if done >= len(e["sets"]):
            continue
        if best_done is None or done < best_done:
            best, best_done = i, done
    return best

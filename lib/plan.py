"""Lettura, validazione e modifica del piano di allenamento (logica pura, niente Streamlit)."""
from __future__ import annotations

import copy
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote_plus

BLOCK_TYPES = {"warmup", "superset", "circuit", "cooldown", "single", "main"}
NON_COUNTABLE_BLOCKS = {"warmup", "cooldown"}
YT_SEARCH = "https://www.youtube.com/results?search_query="

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PLAN_PATH = ROOT / "data" / "plan_v1.json"
DEFAULT_VIDEOS_PATH = ROOT / "data" / "videos.json"


# ---------------------------------------------------------------- caricamento
def load_json_file(path: str | Path) -> Any:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_default_plan() -> dict:
    plan = load_json_file(DEFAULT_PLAN_PATH)
    return strip_plan(plan)


def load_videos(path: str | Path = DEFAULT_VIDEOS_PATH) -> dict:
    try:
        data = load_json_file(path)
    except (OSError, ValueError):
        return {"exercises": {}, "alternatives": {}}
    if not isinstance(data, dict):
        return {"exercises": {}, "alternatives": {}}
    data.setdefault("exercises", {})
    data.setdefault("alternatives", {})
    return data


def strip_plan(plan: dict) -> dict:
    """Toglie dal piano le parti che non servono all'app (storico ciclo 1)."""
    plan = copy.deepcopy(plan)
    plan.pop("history", None)
    plan.pop("historyMeta", None)
    return plan


# ---------------------------------------------------------------- navigazione
def session_ids(plan: dict) -> list[str]:
    return [s["id"] for s in plan.get("sessions", [])]


def get_session(plan: dict, session_id: str) -> dict:
    for s in plan.get("sessions", []):
        if s["id"] == session_id:
            return s
    raise KeyError(f"Seduta {session_id!r} non trovata nel piano")


def iter_exercises(plan: dict, session_id: str | None = None) -> Iterator[tuple[dict, dict, dict]]:
    """Restituisce (seduta, blocco, esercizio)."""
    for s in plan.get("sessions", []):
        if session_id and s["id"] != session_id:
            continue
        for b in s.get("blocks", []):
            for e in b.get("exercises", []):
                yield s, b, e


def exercise_catalog(plan: dict) -> dict[str, dict]:
    """exerciseId -> prima definizione trovata (con nome e info utili per i grafici)."""
    out: dict[str, dict] = {}
    for s, b, e in iter_exercises(plan):
        if e["id"] not in out:
            out[e["id"]] = {**e, "blockType": b.get("type"), "sessions": [s["id"]]}
        elif s["id"] not in out[e["id"]]["sessions"]:
            out[e["id"]]["sessions"].append(s["id"])
    return out


def find_exercise(plan: dict, session_id: str, exercise_id: str, block_id: str | None = None) -> tuple[dict, dict] | None:
    for _, b, e in iter_exercises(plan, session_id):
        if e["id"] == exercise_id and (block_id is None or b["id"] == block_id):
            return b, e
    return None


def get_rule(plan: dict, exercise_id: str) -> dict | None:
    for r in plan.get("progression", {}).get("rules", []):
        if r.get("exerciseId") == exercise_id:
            return r
    return None


def block_short(block: dict) -> str:
    """Nome breve del blocco per le linguette: campo 'short', altrimenti dal titolo
    ("PESANTE 1 — SUPERSET A (≈17')" → "Superset A", "BLOCCO GIUBBOTTO — …" → "Giubbotto")."""
    if block.get("short"):
        return str(block["short"])
    typ = block.get("type")
    if typ == "warmup":
        return "Riscaldamento"
    if typ == "cooldown":
        return "Defaticamento"
    title = str(block.get("title") or block.get("id") or "")
    m = re.search(r"SUPERSET\s+([A-Z0-9])\b", title, re.I)
    if m:
        return f"Superset {m.group(1).upper()}"
    head = re.split(r"[—(+]", title)[0].strip()
    head = re.sub(r"^blocco\s+", "", head, flags=re.I).strip()
    words = head.split()
    return " ".join(words[:2]).capitalize() if words else title


# ---------------------------------------------------------------- tipo di metrica
def metric_kind(ex: dict) -> str:
    """'strength' = carico in kg con unità 'rip' → e1RM sensato.
    'bodyweight' = corpo libero / zavorrato → PR come ripetizioni a una data zavorra.
    'reps_at_load' = altre unità (rip/lato, m, s, KB) → PR come ripetizioni a dato carico.
    """
    if ex.get("bodyweight") or ex.get("loadFrom") == "giubbotto":
        return "bodyweight"
    unit = (ex.get("repsUnit") or "rip").strip()
    if unit == "rip" and ex.get("startingLoadKg") not in (None, 0):
        return "strength"
    return "reps_at_load"


# ---------------------------------------------------------------- attrezzo e passo dei kg
BARBELL_STEP = 5.0      # niente dischi da 2,5: il bilanciere sale/scende di 5 kg
KETTLEBELL_STEP = 4.0   # le kettlebell vanno di 4 in 4 (8, 12, 16…)
WEIGHTED_STEP = 1.0     # giubbotto e zavorra
OTHER_STEP = 2.5
_KB_RE = re.compile(r"(^|[\s-])kb($|[\s-])|kettlebell")
_BARBELL_RE = re.compile(r"bilanciere|barbell|back[\s-]squat|front[\s-]squat|stacco[\s-]da[\s-]terra|military|"
                         r"panca[\s-](piana|inclinata)|bench")


def equipment(ex: dict) -> str:
    """Tipo di attrezzo: campo 'equipment' del piano, altrimenti ricavato da id/nome/campi.
    'vest' (giubbotto), 'bodyweight' (corpo libero/zavorra), 'kettlebell', 'barbell', 'other'."""
    if ex.get("equipment"):
        return str(ex["equipment"])
    txt = f"{ex.get('id', '')} {ex.get('name', '')}".lower()
    if ex.get("loadFrom") == "giubbotto":
        return "vest"
    if ex.get("bodyweight") or "zavorrat" in txt:
        return "bodyweight"
    if _KB_RE.search(txt):
        return "kettlebell"
    if _BARBELL_RE.search(txt) or ex.get("warmupSets"):
        return "barbell"
    return "other"


def default_kg_step(ex: dict) -> float:
    return {"barbell": BARBELL_STEP, "kettlebell": KETTLEBELL_STEP, "vest": WEIGHTED_STEP,
            "bodyweight": WEIGHTED_STEP}.get(equipment(ex), OTHER_STEP)


def kg_step(ex: dict) -> float:
    """Passo dei tasti ±kg: campo 'kgStep' del piano, altrimenti default per attrezzo."""
    try:
        v = float(ex.get("kgStep") or 0)
    except (TypeError, ValueError):
        v = 0
    return v if v > 0 else default_kg_step(ex)


def round_kg(kg: float | int | None, step: float, kind: str | None = None) -> float | int | None:
    """Arrotonda al multiplo del passo più vicino (a metà strada scende: più prudente).
    Le kettlebell non si arrotondano (sono pesi fissi)."""
    if kg is None or not step or step <= 0 or kind == "kettlebell":
        return kg
    try:
        f = float(kg)
    except (TypeError, ValueError):
        return kg
    r = math.ceil(round(f / step, 6) - 0.5) * step
    r = round(r, 2)
    return int(r) if float(r).is_integer() else r


# ---------------------------------------------------------------- migrazione piani salvati
_SHEET_REF = re.compile(r"[^.]*\bfoglio\s+'[^']*'[^.]*\.\s*")


def strip_sheet_refs(text: str | None) -> str | None:
    """Toglie i rimandi al vecchio foglio di calcolo ("foglio 'Carichi e Progressione'")."""
    if not text or "foglio" not in text:
        return text
    return _SHEET_REF.sub("", text).strip()


def migrate_plan(plan: dict, default: dict | None = None) -> dict:
    """Completa un piano salvato (copia di plan_v1) con i campi nuovi presi dal piano predefinito,
    senza toccare quello che l'utente ha cambiato: aggiunge 'cue' e 'kgStep' solo se mancano
    (prima per seduta+blocco+esercizio, poi per exerciseId) e toglie i rimandi al foglio dalle note."""
    if default is None:
        default = load_default_plan()
    p = copy.deepcopy(plan)
    exact: dict[tuple, dict] = {}
    by_id: dict[str, dict] = {}
    for s, b, e in iter_exercises(default):
        exact[(s["id"], b["id"], e["id"])] = e
        by_id.setdefault(e["id"], e)
    for s, b, e in iter_exercises(p):
        src = exact.get((s["id"], b["id"], e.get("id"))) or by_id.get(e.get("id")) or {}
        for field in ("cue", "kgStep"):
            if field not in e and src.get(field) not in (None, ""):
                e[field] = src[field]
        if e.get("notes"):
            e["notes"] = strip_sheet_refs(e["notes"])
    return p


# ---------------------------------------------------------------- trazioni / giubbotto
def pullup_group(plan: dict, week: int) -> dict | None:
    for g in plan.get("progression", {}).get("pullUps", {}).get("weeks", []):
        if week in g.get("weeks", []):
            return g
    groups = plan.get("progression", {}).get("pullUps", {}).get("weeks", [])
    if groups and week > max(max(g["weeks"]) for g in groups):
        return groups[-1]
    return groups[0] if groups else None


def vest_kg(plan: dict, week: int) -> float | None:
    g = pullup_group(plan, week)
    return g.get("vestKg") if g else None


def target_sets(plan: dict, ex: dict, week: int) -> int:
    """Numero di serie previste per la settimana (tabella trazioni se setsFromProgression)."""
    ref = ex.get("setsFromProgression")
    base = int(ex.get("sets") or 1)
    if not ref:
        return base
    g = pullup_group(plan, week)
    if not g:
        return base
    node: Any = g
    for part in ref.split("."):
        if not isinstance(node, dict) or part not in node:
            return base
        node = node[part]
    if isinstance(node, dict) and "sets" in node:
        return int(node["sets"])
    return base


def target_reps(plan: dict, ex: dict, week: int) -> tuple[int | None, int | None]:
    ref = ex.get("setsFromProgression")
    if ref:
        g = pullup_group(plan, week)
        node: Any = g or {}
        for part in ref.split("."):
            node = node.get(part, {}) if isinstance(node, dict) else {}
        if isinstance(node, dict) and node.get("reps"):
            return int(node["reps"]), int(node["reps"])
    return ex.get("repsMin"), ex.get("repsMax")


# ---------------------------------------------------------------- parsing testi
_NUM = r"(\d+(?:[.,]\d+)?)"


def parse_rest_seconds(text: str | None) -> int | None:
    """"60-90'' → A2" → 90 ; "30''" → 30 ; "2'" → 120 ; "-" / "resto del min." → None."""
    if not text:
        return None
    t = text.strip()
    m = re.search(_NUM + r"\s*(?:-\s*" + _NUM + r")?\s*(''|\"|”|″|s\b|sec)", t)
    if m:
        hi = m.group(2) or m.group(1)
        return int(float(hi.replace(",", ".")))
    m = re.search(_NUM + r"\s*(?:-\s*" + _NUM + r")?\s*('|’|min)", t)
    if m:
        hi = m.group(2) or m.group(1)
        return int(float(hi.replace(",", ".")) * 60)
    return None


def parse_rir_target(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", str(text))
    return int(m.group()) if m else None


# ---------------------------------------------------------------- video
def youtube_id(url: str | None) -> str | None:
    if not url:
        return None
    m = re.search(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|shorts/|embed/)|youtu\.be/)([A-Za-z0-9_-]{6,})", url)
    return m.group(1) if m else None


def resolve_video(ex: dict, videos: dict | None, alternative: bool = False) -> dict:
    """Restituisce {embed, url, title, channel, search} per l'esercizio (o la sua alternativa).

    Priorità: campo 'video' del piano (link diretto) → videos.json (alternativa per testo,
    poi esercizio per id, poi per nome) → ricerca YouTube del piano.
    """
    videos = videos or {}
    search = ex.get("videoUrl") or (YT_SEARCH + quote_plus(ex.get("name", "") + " esecuzione corretta"))
    entry = None
    if alternative and ex.get("alternative"):
        alt = ex["alternative"]
        entry = (videos.get("alternatives") or {}).get(alt)
        search = YT_SEARCH + quote_plus(alt + " esercizio")
    if entry is None and ex.get("video") and youtube_id(ex.get("video")):
        entry = {"url": ex["video"], "title": ex.get("name")}
    if entry is None:
        entry = (videos.get("exercises") or {}).get(ex.get("id"))
    if entry is None:
        for v in (videos.get("exercises") or {}).values():
            if isinstance(v, dict) and v.get("name", "").lower() == ex.get("name", "").lower():
                entry = v
                break
    if entry and youtube_id(entry.get("url")):
        return {
            "embed": entry["url"],
            "url": entry["url"],
            "title": entry.get("title"),
            "channel": entry.get("channel"),
            "lang": entry.get("lang"),
            "search": search,
        }
    return {"embed": None, "url": None, "title": None, "channel": None, "lang": None, "search": search}


# ---------------------------------------------------------------- validazione
def validate_plan(plan: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["Il piano deve essere un oggetto JSON."]
    sessions = plan.get("sessions")
    if not isinstance(sessions, list) or not sessions:
        return ["Manca l'elenco 'sessions' (almeno una seduta)."]
    seen_sessions = set()
    for si, s in enumerate(sessions):
        where = f"sessions[{si}]"
        if not isinstance(s, dict) or not s.get("id"):
            errors.append(f"{where}: manca 'id'.")
            continue
        if s["id"] in seen_sessions:
            errors.append(f"{where}: id seduta duplicato {s['id']!r}.")
        seen_sessions.add(s["id"])
        if not s.get("title"):
            errors.append(f"Seduta {s['id']}: manca 'title'.")
        blocks = s.get("blocks")
        if not isinstance(blocks, list) or not blocks:
            errors.append(f"Seduta {s['id']}: nessun blocco.")
            continue
        block_ids = set()
        for bi, b in enumerate(blocks):
            bw = f"Seduta {s['id']} blocco {bi + 1}"
            if not isinstance(b, dict) or not b.get("id"):
                errors.append(f"{bw}: manca 'id'.")
                continue
            if b["id"] in block_ids:
                errors.append(f"{bw}: id blocco duplicato {b['id']!r}.")
            block_ids.add(b["id"])
            if b.get("type") not in BLOCK_TYPES:
                errors.append(f"{bw}: 'type' deve essere uno di {sorted(BLOCK_TYPES)}.")
            exs = b.get("exercises")
            if not isinstance(exs, list) or not exs:
                errors.append(f"{bw}: nessun esercizio.")
                continue
            ex_ids = set()
            for ei, e in enumerate(exs):
                ew = f"{bw} esercizio {ei + 1}"
                if not isinstance(e, dict):
                    errors.append(f"{ew}: non è un oggetto.")
                    continue
                for field in ("id", "name"):
                    if not e.get(field):
                        errors.append(f"{ew}: manca '{field}'.")
                if e.get("id") in ex_ids:
                    errors.append(f"{ew}: esercizio {e.get('id')!r} ripetuto nello stesso blocco.")
                ex_ids.add(e.get("id"))
                if e.get("id") and not re.fullmatch(r"[a-z0-9][a-z0-9-]*", str(e["id"])):
                    errors.append(f"{ew}: id {e['id']!r} non valido (solo minuscole, numeri e '-').")
                sets = e.get("sets")
                if not isinstance(sets, int) or not (1 <= sets <= 12):
                    errors.append(f"{ew} ({e.get('name')}): 'sets' deve essere un intero tra 1 e 12.")
                for f in ("repsMin", "repsMax"):
                    v = e.get(f)
                    if v is not None and (not isinstance(v, (int, float)) or v < 0):
                        errors.append(f"{ew} ({e.get('name')}): '{f}' deve essere un numero ≥ 0.")
                if isinstance(e.get("repsMin"), (int, float)) and isinstance(e.get("repsMax"), (int, float)):
                    if e["repsMin"] > e["repsMax"]:
                        errors.append(f"{ew} ({e.get('name')}): repsMin > repsMax.")
                load = e.get("startingLoadKg")
                if load is not None and (not isinstance(load, (int, float)) or load < 0):
                    errors.append(f"{ew} ({e.get('name')}): 'startingLoadKg' deve essere un numero ≥ 0 o null.")
                step = e.get("kgStep")
                if step is not None and (not isinstance(step, (int, float)) or isinstance(step, bool) or step <= 0):
                    errors.append(f"{ew} ({e.get('name')}): 'kgStep' deve essere un numero > 0.")
                if "track" in e and not isinstance(e["track"], bool):
                    errors.append(f"{ew} ({e.get('name')}): 'track' deve essere true/false.")
    return errors


# ---------------------------------------------------------------- versioni
EDITABLE_FIELDS = {
    "name": str, "code": str, "cue": str, "setsText": str, "tempo": str, "rir": str, "rest": str, "notes": str,
    "alternative": str, "videoUrl": str, "video": str, "repsUnit": str,
    "sets": int, "setsMax": int, "repsMin": int, "repsMax": int, "startingLoadKg": float, "kgStep": float,
    "track": bool, "phase": int, "painCheck": str,
}


def new_version(plan: dict, existing_versions: list[int] | None = None, today: date | None = None) -> dict:
    p = strip_plan(plan)
    nums = list(existing_versions or []) + [int(plan.get("version") or 1)]
    p["version"] = max(nums) + 1
    p["updatedAt"] = (today or date.today()).isoformat()
    return p


def update_exercise(plan: dict, session_id: str, block_id: str, exercise_id: str, changes: dict,
                    all_sessions: bool = False) -> dict:
    """Restituisce una copia del piano con i campi modificati. Con all_sessions=True applica
    i campi testuali comuni (nome, note, alternativa, video) a ogni occorrenza dello stesso id."""
    p = copy.deepcopy(plan)
    clean: dict[str, Any] = {}
    for k, v in changes.items():
        if k not in EDITABLE_FIELDS:
            raise ValueError(f"Campo non modificabile: {k}")
        typ = EDITABLE_FIELDS[k]
        if v is None or v == "":
            clean[k] = None if typ in (int, float) or k in ("painCheck", "video") else ""
        elif typ is bool:
            clean[k] = bool(v)
        elif typ is int:
            clean[k] = int(v)
        elif typ is float:
            fv = float(v)
            clean[k] = int(fv) if fv.is_integer() else fv
        else:
            clean[k] = str(v)
    found = False
    shared = {"name", "cue", "notes", "alternative", "videoUrl", "video"}
    for s in p["sessions"]:
        for b in s["blocks"]:
            for e in b["exercises"]:
                if e["id"] != exercise_id:
                    continue
                if s["id"] == session_id and b["id"] == block_id:
                    found = True
                    for k, v in clean.items():
                        if v is None and k in ("painCheck", "video", "setsMax", "phase", "kgStep"):
                            e.pop(k, None)
                        else:
                            e[k] = v
                elif all_sessions:
                    for k in shared & clean.keys():
                        e[k] = clean[k]
    if not found:
        raise KeyError(f"Esercizio {exercise_id} non trovato in {session_id}/{block_id}")
    return p


def plan_to_text(plan: dict) -> str:
    return json.dumps(plan, ensure_ascii=False, indent=2)


def parse_plan_text(text: str) -> tuple[dict | None, list[str]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        return None, [f"JSON non valido (riga {exc.lineno}, colonna {exc.colno}): {exc.msg}"]
    errs = validate_plan(data)
    return (data if not errs else None), errs

"""Componenti lato browser: registro serie (outbox in localStorage + timer di recupero),
ponte bozza/telefono e timer EMOM per il riscaldamento."""
from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

_WEB = Path(__file__).resolve().parent / "components" / "web"
_allen = components.declare_component("allen_web", path=str(_WEB))


def set_logger(*, key: str, draft_id: str, ex: dict, synced_rev: int, draft_rev: int, settings: dict,
               rest_label: str = "", kg_step: float | None = None, next_info: dict | None = None) -> dict | None:
    sets = []
    ack = {}
    for s in ex.get("sets", []):
        sets.append({"n": s["n"], "kg": s.get("kg"), "reps": s.get("reps"), "done": bool(s.get("done")),
                     "t": int(s.get("t") or 0), "prev": s.get("prev"), "extra": bool(s.get("extra"))})
        if s.get("t") and int(s.get("rev") or 0) <= synced_rev:
            ack[str(s["n"])] = int(s["t"])
    presc = ex.get("prescription") or {}
    mode = ex.get("kgMode", "free")
    step = kg_step or ex.get("kgStep") or (1.0 if mode in ("bw", "vest") else 2.5)
    if ex.get("usedAlternative") and mode == "vest":
        mode, step = "bw", 1.0
    return _allen(
        mode="sets", draftId=draft_id, exKey=ex["key"], sets=sets, ackT=ack, synced=draft_rev <= synced_rev,
        kgMode=mode, kgStep=float(step), unit=presc.get("repsUnit") or "rip",
        restSec=presc.get("restSec"), restLabel=rest_label, next=next_info, code=ex.get("code") or "",
        name=ex.get("name") or "", sound=settings.get("sound", True),
        vibrate=settings.get("vibrate", True), wakeLock=settings.get("wakeLock", True),
        key=key, default=None,
    )


def bridge(*, draft: dict | None, synced_rev: int, clear: str | None = None, visible: bool = True,
           key: str = "allen_bridge") -> dict | None:
    known, ack = {}, {}
    mirror = None
    if draft:
        for ex in draft.get("exercises", []):
            for s in ex.get("sets", []):
                if s.get("t"):
                    k = f"{ex['key']}|{s['n']}"
                    known[k] = int(s["t"])
                    if int(s.get("rev") or 0) <= synced_rev:
                        ack[k] = int(s["t"])
        mirror = _slim(draft)
    pending = 0 if not draft else max(0, int(draft.get("rev", 0)) - int(synced_rev))
    return _allen(mode="bridge", draftId=draft.get("id") if draft else None, draft=mirror, known=known, ackT=ack,
                  synced=bool(draft) and pending == 0, pendingServer=pending, clear=clear, visible=visible,
                  key=key, default=None)


def auth_bridge(*, set_token: str | None = None, clear: bool = False, key: str = "allen_auth") -> dict | None:
    """Legge (all'avvio) e scrive il token di questo dispositivo nel localStorage del browser."""
    return _allen(mode="auth", set=set_token, clear=clear, key=key, default=None)


def _slim(draft: dict) -> dict:
    """Copia leggera della bozza per il telefono (senza i valori 'precedente')."""
    d = json.loads(json.dumps(draft))
    for ex in d.get("exercises", []):
        for s in ex.get("sets", []):
            s.pop("prev", None)
    return d


def emom_timer(names: list[str], *, minutes: int = 10, storage_key: str = "emom", key: str = "emom") -> dict | None:
    """Timer EMOM a intervalli di 1' (beep e vibrazione a ogni cambio). Ritorna {done: minuti completati}
    così l'app spunta da sola l'esercizio di ogni minuto finito. Si avvia con un tap (sblocca l'audio)."""
    return _allen(mode="emom", names=names, minutes=minutes, lsKey="allen_emom_" + storage_key, key=key, default=None)

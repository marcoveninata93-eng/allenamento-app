"""Storico: elenco sedute, dettaglio, modifica ed eliminazione."""
from __future__ import annotations

import copy
from datetime import date

import pandas as pd
import streamlit as st

from lib import logic as L
from lib import services as S
from lib import ui as U
from lib.storage import StorageError

U.page_title("Storico", "storico")
logs = S.logs()
if not logs:
    st.info("Nessuna seduta salvata finora.")
    st.stop()

flt = st.segmented_control("Filtro", ["Tutte", "A", "B", "C"], default="Tutte", key="hist_filter", width="stretch")
shown = [l for l in reversed(logs) if flt in (None, "Tutte") or l.get("sessionId") == flt]
st.caption(f"{len(shown)} sedute")

DAYS = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]


def edit_form(log: dict) -> None:
    rows = []
    for i, ex in enumerate(log.get("exercises", [])):
        for s in ex.get("sets", []):
            rows.append({"#": i, "Esercizio": f"{ex.get('code') or ''} {ex['name']}".strip(), "Serie": s.get("n"),
                         "kg": s.get("kg"), "rip": s.get("reps")})
    with st.form(f"edit_{log['id']}"):
        d = st.date_input("Data", value=date.fromisoformat(log["date"]), format="DD/MM/YYYY")
        df = st.data_editor(pd.DataFrame(rows), hide_index=True, width="stretch", num_rows="dynamic",
                            disabled=["Esercizio"], column_config={
                                "#": None,
                                "kg": st.column_config.NumberColumn(step=0.25, min_value=0),
                                "rip": st.column_config.NumberColumn(step=1, min_value=0)},
                            key=f"ed_{log['id']}") if rows else None
        notes = st.text_area("Note seduta", value=log.get("notes") or "")
        if st.form_submit_button("Salva modifiche", icon=":material/save:", type="primary", width="stretch"):
            new = copy.deepcopy(log)
            new["date"] = d.isoformat()
            new["notes"] = notes
            new["editedAt"] = S.now_local().isoformat(timespec="seconds")
            if df is not None:
                for ex in new["exercises"]:
                    ex["sets"] = []
                for r in df.to_dict("records"):
                    idx = r.get("#")
                    if idx is None or pd.isna(idx):
                        continue
                    ex = new["exercises"][int(idx)]
                    if pd.isna(r.get("rip")) or not r.get("rip"):
                        continue
                    ex["sets"].append({"n": len(ex["sets"]) + 1, "kg": None if pd.isna(r.get("kg")) else float(r["kg"]),
                                       "reps": float(r["rip"]), "done": True})
                for ex in new["exercises"]:
                    for s in ex["sets"]:
                        for f in ("kg", "reps"):
                            if isinstance(s[f], float) and s[f].is_integer():
                                s[f] = int(s[f])
            try:
                S.store().save_log(new, overwrite=True)
                S.invalidate()
                st.session_state[f"editing_{log['id']}"] = False
                st.success("Seduta aggiornata.")
                st.rerun()
            except StorageError as exc:
                st.error(str(exc), icon=":material/error:")


for log in shown[:60]:
    d = date.fromisoformat(log["date"])
    nsets = sum(len(L.work_sets(e)) for e in log.get("exercises", []) if L.is_countable(e))
    title = f"{DAYS[d.weekday()]} {d.strftime('%d/%m/%Y')} · Seduta {log.get('sessionId')} · sett. {log.get('cycleWeek') or '–'} · {nsets} serie"
    with st.expander(title):
        tags = []
        if log.get("planVersion"):
            tags.append(U.pill(f"piano v{log['planVersion']}"))
        if log.get("vestKg") is not None:
            tags.append(U.pill(f"giubbotto {L.fmt_kg(log['vestKg'])} kg"))
        if log.get("bodyweightKg"):
            tags.append(U.pill(f"peso {log['bodyweightKg']} kg"))
        if log.get("energy"):
            tags.append(U.pill(f"energia {log['energy']}/5"))
        if log.get("imported") or log.get("importedFrom"):
            tags.append(U.pill("importata", "warn"))
        if tags:
            st.html("<div>" + "".join(tags) + "</div>")
        lines = []
        for ex in log.get("exercises", []):
            ws = L.work_sets(ex)
            label = f"**{(ex.get('code') or '')} {ex['name']}**".replace("** ", "**")
            if ex.get("usedAlternative"):
                label += f" (alternativa: {ex.get('alternative') or '—'})"
            if ws:
                txt = L.format_sets(ws)
            elif ex.get("done"):
                txt = "fatto"
            else:
                continue
            if ex.get("warmupSets") and any(w.get("done") for w in ex["warmupSets"]):
                txt += "  · avv. " + ", ".join(f"{L.fmt_kg(w['kg'])}×{w['reps']}" for w in ex["warmupSets"] if w.get("done"))
            if ex.get("pain") is not None:
                txt += f" · dolore {ex['pain']}/10"
            if ex.get("note"):
                txt += f" · _{ex['note']}_"
            lines.append(f"- {label}: {txt}")
        st.markdown("\n".join(lines) or "_Nessun esercizio registrato._")
        if log.get("tennis"):
            st.markdown(f"**Attività extra:** {log['tennis']}")
        if log.get("notes"):
            st.markdown(f"**Note:** {log['notes']}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Modifica", icon=":material/edit:", key=f"edbtn_{log['id']}", width="stretch"):
                st.session_state[f"editing_{log['id']}"] = not st.session_state.get(f"editing_{log['id']}", False)
        with c2:
            confirm = st.checkbox("Conferma eliminazione", key=f"delc_{log['id']}")
            if st.button("Elimina", icon=":material/delete:", key=f"del_{log['id']}", disabled=not confirm, width="stretch"):
                try:
                    S.store().delete_log(log["id"])
                    S.invalidate()
                    st.rerun()
                except StorageError as exc:
                    st.error(str(exc), icon=":material/error:")
        if st.session_state.get(f"editing_{log['id']}"):
            edit_form(log)

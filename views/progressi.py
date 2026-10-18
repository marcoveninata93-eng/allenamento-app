"""📈 Progressi: grafici per esercizio, PR, peggioramenti, peso corporeo, monitoraggio settimanale."""
from __future__ import annotations

from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

from lib import logic as L
from lib import services as S
from lib import ui as U
from lib.storage import StorageError

st.markdown("## 📈 Progressi")
logs = S.logs()
plan = S.active_plan()
tracked = L.tracked_exercises(logs)

KIND_METRICS = {
    "strength": {"e1RM stimato (Epley)": "best_e1rm", "Carico massimo (kg)": "max_kg", "Volume (kg × rip)": "volume"},
    "bodyweight": {"Ripetizioni migliori in una serie": "best_reps", "Ripetizioni totali": "total_reps",
                   "Zavorra (kg)": "max_kg"},
    "reps_at_load": {"Ripetizioni migliori in una serie": "best_reps", "Ripetizioni totali": "total_reps",
                     "Carico (kg)": "max_kg"},
}


def line_chart(df: pd.DataFrame, y: str, title: str, color: str | None = "Seduta") -> alt.Chart:
    base = alt.Chart(df).encode(
        x=alt.X("Data:T", title=None, axis=alt.Axis(format="%d/%m", labelAngle=0)),
        y=alt.Y(f"{y}:Q", title=title, scale=alt.Scale(zero=False, padding=12), axis=alt.Axis(format="~f", tickCount=5)),
        tooltip=[alt.Tooltip("Data:T", format="%d/%m/%Y"), *( [color] if color else []), alt.Tooltip(f"{y}:Q", format=".1f"), "Serie"],
    )
    enc = {"color": alt.Color(f"{color}:N", scale=alt.Scale(range=["#FF7A1A", "#3b82f6", "#22c55e", "#e879f9"]),
                              legend=alt.Legend(orient="top", title=None))} if color else {}
    return (base.mark_line(strokeWidth=2.5).encode(**enc) + base.mark_point(size=70, filled=True).encode(**enc)).properties(height=260)


tab1, tab2, tab3 = st.tabs(["🏋️ Esercizi", "⚖️ Peso", "🗓️ Settimane"])

with tab1:
    if not tracked:
        st.info("Ancora nessun dato: completa e salva una seduta per vedere grafici e record.")
    else:
        ids = sorted(tracked, key=lambda i: (-tracked[i]["n"], tracked[i]["name"] or i))
        exid = st.selectbox("Esercizio", ids, format_func=lambda i: f"{tracked[i]['name']} ({tracked[i]['n']})")
        kind = tracked[exid]["kind"]
        metrics = KIND_METRICS.get(kind, KIND_METRICS["reps_at_load"])
        c1, c2 = st.columns([3, 2])
        with c1:
            mlabel = st.selectbox("Metrica", list(metrics))
        with c2:
            sess_filter = st.selectbox("Seduta", ["Tutte", "A", "B", "C"])
        hist = L.exercise_history(logs, exid, session_id=None if sess_filter == "Tutte" else sess_filter)
        if kind == "strength":
            st.caption("e1RM = carico × (1 + rip/30), solo serie di lavoro (avvicinamento, riscaldamento e defaticamento esclusi).")
        elif kind == "bodyweight":
            st.caption("Esercizio a corpo libero/zavorrato: niente e1RM, si confrontano le ripetizioni a parità di zavorra.")
        if hist:
            key = metrics[mlabel]
            df = pd.DataFrame([{"Data": pd.to_datetime(h["date"]), "Seduta": h["sessionId"], key: h.get(key),
                                "Serie": L.format_sets(h["sets"])} for h in hist])
            df = df.dropna(subset=[key])
            if len(df):
                st.altair_chart(line_chart(df, key, mlabel), width="stretch")
            st.dataframe(pd.DataFrame([{"Data": date.fromisoformat(h["date"]).strftime("%d/%m"), "Seduta": h["sessionId"],
                                        "Serie": L.format_sets(h["sets"]),
                                        **({"e1RM": h["best_e1rm"]} if kind == "strength" else {})}
                                       for h in reversed(hist)]), hide_index=True, width="stretch")
        else:
            st.info("Nessuna seduta per questo filtro.")

        rec = L.personal_records(logs).get(exid)
        if rec:
            st.markdown("#### 🏆 Record")
            html = ""
            if rec.get("best_e1rm"):
                b = rec["best_e1rm"]
                html += U.pill(f"e1RM {b['value']:g} kg ({L.fmt_kg(b['kg'])}×{b['reps']:g}, {b['date'][8:10]}/{b['date'][5:7]})", "ok")
            if rec.get("max_kg"):
                m = rec["max_kg"]
                html += U.pill(f"Carico max {L.fmt_kg(m['kg'])} kg × {m['reps']:g}", "ok")
            if rec.get("best_volume"):
                html += U.pill(f"Volume max {rec['best_volume']['value']:g} kg", "ok")
            for k, v in sorted(rec["reps_at_load"].items(), key=lambda kv: kv[1]["kg"]):
                lab = "zavorra " if rec["kind"] == "bodyweight" else ""
                html += U.pill(f"{lab}{k} kg → {v['reps']:g} rip")
            st.html(f"<div>{html}</div>")

    decl = L.declines(logs)
    if decl:
        st.markdown("#### 📉 Attenzione")
        for x in decl:
            st.warning(f"**{x['name']}** (seduta {x['sessionId']}) è peggiorato 2 sedute di fila "
                       f"({', '.join(d[8:10] + '/' + d[5:7] for d in x['dates'])}). "
                       "Regola del piano: settimana con metà delle serie e lo stesso carico.")

with tab2:
    entries = S.bodyweight()
    with st.form("bw_form", clear_on_submit=False):
        c1, c2 = st.columns(2)
        with c1:
            d = st.date_input("Data", value=S.today_local(), format="DD/MM/YYYY")
        with c2:
            kg = st.number_input("Peso (kg)", min_value=30.0, max_value=200.0, step=0.1, value=None, placeholder="75.0")
        if st.form_submit_button("➕ Salva pesata", width="stretch") and kg:
            try:
                S.store().save_bodyweight(L.upsert_bodyweight(entries, d, kg))
                S.invalidate()
                st.success("Pesata salvata.")
                entries = S.bodyweight()
            except StorageError as exc:
                st.error(f"⚠️ {exc}")
    st.caption("Pesati al mattino a digiuno: conta la media settimanale, non il singolo giorno.")
    start = (plan.get("progression", {}).get("monitoring", {}) or {}).get("bodyWeightStartKg")
    if entries:
        dfd = pd.DataFrame([{"Data": pd.to_datetime(e["date"]), "kg": e["kg"]} for e in entries])
        wk = L.weekly_bodyweight(entries)
        dfw = pd.DataFrame([{"Data": pd.to_datetime(w["weekStart"]) + pd.Timedelta(days=3), "media": w["mean"]} for w in wk])
        pts = alt.Chart(dfd).mark_point(color="#9aa3b5", size=50).encode(
            x=alt.X("Data:T", title=None, axis=alt.Axis(format="%d/%m")), y=alt.Y("kg:Q", scale=alt.Scale(zero=False), title="kg"),
            tooltip=[alt.Tooltip("Data:T", format="%d/%m"), "kg"])
        line = alt.Chart(dfw).mark_line(color="#FF7A1A", strokeWidth=3, point=True).encode(x="Data:T", y="media:Q",
                                                                                            tooltip=["media"])
        st.altair_chart((pts + line).properties(height=240), width="stretch")
        last_w = wk[-1]
        msg = f"Media settimana dal {last_w['weekStart'][8:10]}/{last_w['weekStart'][5:7]}: **{last_w['mean']} kg** ({last_w['n']} pesate)"
        if start:
            msg += f" · inizio ciclo {start} kg ({last_w['mean'] - start:+.1f})"
        st.markdown(msg)
        st.dataframe(pd.DataFrame([{"Settimana dal": w["weekStart"], "Media kg": w["mean"], "Pesate": w["n"]} for w in reversed(wk)]),
                     hide_index=True, width="stretch")
    else:
        st.info("Nessuna pesata registrata." + (f" Peso a inizio ciclo dal piano: {start} kg." if start else ""))

with tab3:
    st.caption("Monitoraggio settimanale: per ogni settimana di ciclo l'ultima esecuzione registrata.")
    cols = {"back-squat": "Squat", "stacco-da-terra": "Stacco", "panca-inclinata-bilanciere": "Panca incl.",
            "military-press": "Military", "affondi-bulgari-bilanciere": "Bulgari"}
    weeks: dict[int, dict] = {}
    for log in L.sort_logs(logs):
        w = log.get("cycleWeek")
        if not w:
            continue
        row = weeks.setdefault(int(w), {"Sett.": int(w)})
        for ex in log.get("exercises", []):
            if ex.get("exerciseId") in cols and L.work_sets(ex) and not ex.get("usedAlternative"):
                row[cols[ex["exerciseId"]]] = L.format_sets(L.work_sets(ex))
        if log.get("vestKg") is not None:
            row["Giubbotto"] = f"{L.fmt_kg(log['vestKg'])} kg"
        pains = [f"{e['pain']}" for e in log.get("exercises", []) if e.get("pain") is not None]
        if pains:
            row["Dolore spalla (max)"] = max(int(p) for p in pains)
    if weeks:
        st.dataframe(pd.DataFrame([weeks[k] for k in sorted(weeks)]), hide_index=True, width="stretch")
    else:
        st.info("Nessuna seduta registrata in questo ciclo.")

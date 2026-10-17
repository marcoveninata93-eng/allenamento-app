"""📋 Piano: vista completa, regole di progressione, tabella trazioni, modifica come nuova versione."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from lib import plan as P
from lib import services as S
from lib import ui as U
from lib.storage import StorageError

st.markdown("## 📋 Piano")
sett = S.settings()
versions = S.plan_versions()
active_v = int(sett.get("activePlanVersion") or 1)
if "_plan_v_next" in st.session_state:
    st.session_state["plan_v_sel"] = st.session_state.pop("_plan_v_next")
if st.session_state.get("plan_v_sel") not in versions:
    st.session_state["plan_v_sel"] = active_v if active_v in versions else max(versions)
v = st.selectbox("Versione", sorted(versions, reverse=True),
                 format_func=lambda x: f"v{x}" + (" (attiva)" if x == active_v else ""), key="plan_v_sel")
plan = S.get_plan(v)
st.caption(f"{plan.get('name', '')} · aggiornato {plan.get('updatedAt', '')}")
if v != active_v and st.button(f"Usa la versione v{v} come piano attivo", width="stretch"):
    if S.save_settings({**sett, "activePlanVersion": v}):
        st.rerun()

videos = S.videos()
tabs = st.tabs([f"Seduta {s['id']}" for s in plan["sessions"]] + ["Progressione", "✏️ Modifica"])

for tab, sess in zip(tabs, plan["sessions"]):
    with tab:
        st.markdown(f"**{sess['title']}**")
        if sess.get("notes"):
            st.caption(sess["notes"])
        for b in sess["blocks"]:
            st.html(f'<div class="blk-title" style="margin-top:12px">{U.esc(b["title"])}</div>')
            for e in b["exercises"]:
                with st.container(border=True):
                    presc = {"setsTarget": e.get("sets"), "repsMin": e.get("repsMin"), "repsMax": e.get("repsMax"),
                             "repsUnit": e.get("repsUnit"), "tempo": e.get("tempo"), "rir": e.get("rir"),
                             "rest": e.get("rest"), "phase": e.get("phase")}
                    U.exercise_header(e, presc)
                    extra = []
                    if e.get("startingLoadKg") is not None:
                        extra.append(U.pill(f"carico iniziale {e['startingLoadKg']} kg"))
                    if e.get("loadFrom") == "giubbotto":
                        extra.append(U.pill("peso = giubbotto"))
                    if e.get("setsFromProgression"):
                        extra.append(U.pill("serie da tabella trazioni"))
                    if e.get("painCheck"):
                        extra.append(U.pill(f"controllo dolore {e['painCheck']}", "warn"))
                    if e.get("warmupSets"):
                        extra.append(U.pill("avvicinamento " + ", ".join(f"{w['kg']}×{w['reps']}" for w in e["warmupSets"])))
                    if extra:
                        st.html("<div>" + "".join(extra) + "</div>")
                    if e.get("alternative") and e["alternative"] != "-":
                        st.markdown(f"🔁 **Alternativa:** {e['alternative']}")
                    U.video_toggle(e, videos, key=f"pv|{v}|{b['id']}|{e['id']}")
                    if e.get("alternative") and e["alternative"] != "-" and P.resolve_video(e, videos, True)["embed"]:
                        U.video_toggle(e, videos, key=f"pva|{v}|{b['id']}|{e['id']}", alternative=True)

prog = plan.get("progression", {})
with tabs[len(plan["sessions"])]:
    st.markdown(f"**{prog.get('title', 'Progressione')}**")
    if prog.get("method"):
        st.info(prog["method"])
    rules = prog.get("rules", [])
    if rules:
        st.markdown("#### Regole per esercizio")
        for r in rules:
            st.markdown(f"**{r['name']}** — {r.get('setsText', '')} · RIR {r.get('rir', '-')}  \n"
                        f"Partenza: {r.get('startingLoadKg') if r.get('startingLoadKg') is not None else r.get('startingLoadText', '-')} kg"
                        + (f" · ciclo precedente: {r['lastResultCycle1']}" if r.get("lastResultCycle1") else "")
                        + f"  \n➡️ {r['rule']}")
    pu = prog.get("pullUps")
    if pu:
        st.markdown(f"#### {pu.get('title', 'Trazioni')}")
        st.caption(pu.get("legend", ""))
        st.dataframe(pd.DataFrame([{"Settimane": g["label"], "A": g["text"]["A"], "B": g["text"]["B"], "C": g["text"]["C"],
                                    "Giubbotto": f"{g['vestKg']} kg", "Rip/sett.": g.get("weeklyReps"), "Note": g.get("note")}
                                   for g in pu.get("weeks", [])]), hide_index=True, width="stretch")
        wk = S.current_week(sett)
        g = P.pullup_group(plan, wk)
        if g:
            st.success(f"Questa settimana (sett. {wk}): A {g['text']['A']} · B {g['text']['B']} · C {g['text']['C']} con giubbotto {g['vestKg']} kg")
    for title, key in (("Note generali", "generalNotes"), ("Spalla", "shoulderNotes")):
        if prog.get(key):
            st.markdown(f"#### {title}")
            st.markdown("\n".join(f"- {n}" for n in prog[key]))
    if prog.get("deload"):
        st.warning(f"**Scarico:** se {prog['deload']['trigger']} → {prog['deload']['action']}.")

# ------------------------------------------------------------------ modifica
with tabs[-1]:
    st.caption("Ogni modifica crea una **nuova versione** del piano (v{} → v{}). Le sedute già salvate mantengono "
               "la versione con cui sono state fatte.".format(v, max(versions) + 1))
    mode = st.segmented_control("Modalità", ["Esercizio", "JSON completo"], default="Esercizio", key="edit_mode")
    if mode == "Esercizio":
        sid = st.selectbox("Seduta", P.session_ids(plan), key="ed_sid")
        options = [(b["id"], e["id"]) for _, b, e in P.iter_exercises(plan, sid)]
        names = {(b["id"], e["id"]): f"{e.get('code')} · {e['name']}  [{b['title'][:28]}…]" for _, b, e in P.iter_exercises(plan, sid)}
        bid, eid = st.selectbox("Esercizio", options, format_func=lambda o: names[o], key="ed_ex")
        _, e = P.find_exercise(plan, sid, eid, bid)
        with st.form(f"edit_{sid}_{bid}_{eid}"):
            name = st.text_input("Nome", e.get("name", ""))
            c1, c2, c3 = st.columns(3)
            with c1:
                sets = st.number_input("Serie", 1, 12, int(e.get("sets") or 1))
            with c2:
                rmin = st.number_input("Rip min", 0, 100, int(e.get("repsMin") or 0))
            with c3:
                rmax = st.number_input("Rip max", 0, 100, int(e.get("repsMax") or 0))
            c1, c2 = st.columns(2)
            with c1:
                sets_text = st.text_input("Testo serie", e.get("setsText") or "")
                tempo = st.text_input("Tempo", e.get("tempo") or "")
                rest = st.text_input("Recupero", e.get("rest") or "", help="Es. 60-90'' → A2 (il timer usa il valore più alto)")
            with c2:
                load = st.number_input("Carico iniziale kg (vuoto = nessun carico)", 0.0, 400.0,
                                       value=float(e["startingLoadKg"]) if e.get("startingLoadKg") is not None else None,
                                       step=2.5)
                rir = st.text_input("RIR target", e.get("rir") or "")
                unit = st.text_input("Unità", e.get("repsUnit") or "rip")
            notes = st.text_area("Note tecniche", e.get("notes") or "")
            alt_txt = st.text_input("Alternativa", e.get("alternative") or "")
            video = st.text_input("Link video YouTube diretto (facoltativo, sostituisce quello predefinito)", e.get("video") or "")
            track = st.checkbox("Registra serie (kg/rip)", value=e.get("track", True) is not False)
            all_sessions = st.checkbox("Applica nome/note/alternativa/video a tutte le sedute con questo esercizio", value=False)
            activate = st.checkbox("Rendi attiva la nuova versione", value=True)
            ok = st.form_submit_button("💾 Salva come nuova versione", type="primary", width="stretch")
        if ok:
            changes = {"name": name, "sets": sets, "repsMin": rmin, "repsMax": rmax, "setsText": sets_text,
                       "tempo": tempo, "rest": rest, "startingLoadKg": load, "rir": rir, "repsUnit": unit,
                       "notes": notes, "alternative": alt_txt, "video": video or None, "track": track}
            try:
                newp = P.update_exercise(plan, sid, bid, eid, changes, all_sessions=all_sessions)
                newp = P.new_version(newp, versions, S.today_local())
                errs = P.validate_plan(newp)
                if errs:
                    st.error("Piano non valido:\n- " + "\n- ".join(errs))
                else:
                    S.store().save_plan(newp, f"Piano v{newp['version']}: modifica {eid}")
                    if activate:
                        S.store().save_settings({**sett, "activePlanVersion": newp["version"]})
                    S.invalidate()
                    st.session_state["_plan_v_next"] = newp["version"]
                    st.toast(f"Salvata la versione v{newp['version']}.")
                    st.rerun()
            except (ValueError, KeyError, StorageError) as exc:
                st.error(f"⚠️ {exc}")
    else:
        st.caption("Modifica avanzata: il JSON viene validato prima del salvataggio.")
        txt = st.text_area("Piano (JSON)", P.plan_to_text(plan), height=420, key=f"json_{v}")
        if st.button("✅ Valida e salva come nuova versione", type="primary", width="stretch"):
            data, errs = P.parse_plan_text(txt)
            if errs:
                st.error("Correggi questi problemi:\n- " + "\n- ".join(errs))
            else:
                newp = P.new_version(data, versions, S.today_local())
                try:
                    S.store().save_plan(newp, f"Piano v{newp['version']} (JSON)")
                    S.store().save_settings({**sett, "activePlanVersion": newp["version"]})
                    S.invalidate()
                    st.session_state["_plan_v_next"] = newp["version"]
                    st.toast(f"Salvata e attivata la versione v{newp['version']}.")
                    st.rerun()
                except StorageError as exc:
                    st.error(f"⚠️ {exc}")

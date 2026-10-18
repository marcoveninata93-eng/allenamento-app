"""Allenamento: home (prossima seduta, ripresa bozza) e seduta in corso, un blocco alla volta."""
from __future__ import annotations

from datetime import date

import streamlit as st

from lib import logic as L
from lib import plan as P
from lib import services as S
from lib import timer as T
from lib import ui as U
from lib.storage import StorageError

ss = st.session_state
ds = S.store()


# ======================================================================= stato bozza
def load_draft() -> None:
    if ss.get("draft_loaded"):
        return
    try:
        d = ds.get_draft()
        if d is not None and L.is_saved_draft(d, S.logs()):
            # già salvata come seduta (es. cancellazione della bozza fallita): la scarto
            try:
                ds.clear_draft()
            except StorageError:
                pass
            d = None
    except StorageError as exc:
        ss.draft_error = str(exc)
        return
    ss.draft_error = None
    ss.draft = d
    ss.synced_rev = int(d.get("rev", 0)) if d else 0
    ss.draft_loaded = True


def mutate(fn, *args):
    """Applica una modifica alla bozza e ne aumenta la revisione (sarà sincronizzata)."""
    d = ss.get("draft")
    if not d:
        return
    fn(d, *args)
    L.bump(d, S.now_ms())


def process_component_events() -> None:
    d = ss.get("draft")
    events = []
    for k in list(ss.keys()):
        if not (str(k).startswith("sl|") or k == "allen_bridge"):
            continue
        v = ss.get(k)
        if not isinstance(v, dict):
            continue
        if v.get("type") == "mount" and ss.get("_mount_nonce") != v.get("nonce"):
            ss._mount_nonce = v.get("nonce")
            ss.bridge_mount = v
        if v.get("events"):
            events.extend(v["events"])
    if d and events:
        L.apply_events(d, events, S.now_ms())


def sync_draft() -> None:
    d = ss.get("draft")
    if not d or int(d.get("rev", 0)) <= int(ss.get("synced_rev", 0)):
        ss.sync_error = None
        return
    try:
        saved = ds.save_draft(d)
        if saved is not d:
            ss.draft = saved
        ss.synced_rev = int(saved.get("rev", 0))
        ss.sync_error = None
    except StorageError as exc:
        ss.sync_error = str(exc)


# ======================================================================= azioni
def start_session(plan: dict, sid: str, week: int, week_auto: int) -> None:
    # mai sovrascrivere una bozza che esiste già sul server (es. iniziata da un altro dispositivo)
    try:
        remote = ds.get_draft()
    except StorageError as exc:
        ss.start_error = f"Non riesco a controllare il server: {exc}. Riprova tra poco."
        return
    if remote is not None and not L.is_saved_draft(remote, S.logs()):
        ss.draft, ss.synced_rev = remote, int(remote.get("rev", 0))
        ss.start_error = (f"C'è già una seduta {remote.get('sessionId')} in corso sul server "
                          f"(iniziata il {remote.get('date')}): riprendila o scartala prima di iniziarne un'altra.")
        return
    ss.start_error = None
    d = L.new_draft(plan, sid, S.logs(), week=week, day=S.today_local(), now_ms=S.now_ms(), week_auto=week_auto)
    ss.draft = d
    ss.synced_rev = 0
    ss.in_session = True
    ss.last_saved = None
    _reset_widget_keys()


def _reset_widget_keys() -> None:
    for k in list(ss.keys()):
        if isinstance(k, str) and k.startswith(("w|", "sl|", "vid|")):
            del ss[k]


def discard_session() -> None:
    d = ss.get("draft")
    try:
        ds.clear_draft()
    except StorageError as exc:
        st.error(f"Bozza non eliminata dal server: {exc}", icon=":material/error:")
        return
    ss.clear_id = d.get("id") if d else None
    ss.draft, ss.synced_rev, ss.in_session = None, 0, False
    _reset_widget_keys()


def finish_session() -> None:
    d = ss.get("draft")
    if not d:
        return
    log = L.finalize(d, S.now_local())
    prior = S.logs()
    try:
        ds.save_log(log)
    except StorageError as exc:
        ss.finish_error = f"Seduta NON salvata: {exc}. La bozza resta sul telefono e sul server: riprova."
        return
    if d.get("bodyweightKg"):
        try:
            ds.save_bodyweight(L.upsert_bodyweight(ds.get_bodyweight(), d["date"], d["bodyweightKg"]))
        except StorageError:
            pass
    try:
        ds.clear_draft()
    except StorageError:
        pass  # verrà riconosciuta come già salvata (draftId nel log)
    S.invalidate()
    ss.last_saved = {"log": log, "prs": L.new_records(log, prior),
                     "declines": [x for x in L.declines(prior + [log]) if x["sessionId"] == log["sessionId"]]}
    ss.clear_id = d.get("id")
    ss.draft, ss.synced_rev, ss.in_session, ss.finish_error = None, 0, False, None
    _reset_widget_keys()


def restore_from_phone(stored: dict) -> None:
    server = ss.get("draft")
    d = L.merge_drafts(stored, server) if server and server.get("id") == stored.get("id") else stored
    d["rev"] = max(int(d.get("rev", 0)), int((server or {}).get("rev", 0))) + 1
    ss.draft = d
    ss.in_session = True
    _reset_widget_keys()


# ======================================================================= callbacks widget
def cb_field(field: str, wkey: str):
    def _f():
        mutate(lambda d: d.__setitem__(field, ss.get(wkey)))
    return _f


def cb_ex_field(ex_key: str, field: str, wkey: str):
    def _f():
        def m(d):
            ex = L.find_ex(d, ex_key)
            if ex is not None:
                ex[field] = ss.get(wkey)
                ex["t"] = S.now_ms()
        mutate(m)
    return _f


def cb_alt(ex_key: str, wkey: str):
    def _f():
        mutate(lambda d: L.set_alternative(d, ex_key, bool(ss.get(wkey)), S.logs()))
        ex = L.find_ex(ss.draft, ex_key)
        if ex:
            ex["t"] = S.now_ms()
    return _f


def cb_warmup_sets(ex_key: str, wkey: str, labels: list[str]):
    def _f():
        chosen = set(ss.get(wkey) or [])

        def m(d):
            ex = L.find_ex(d, ex_key)
            for lab, w in zip(labels, ex.get("warmupSets", [])):
                w["done"] = lab in chosen
        mutate(m)
    return _f


def cb_vest(wkey: str):
    def _f():
        mutate(lambda d: L.propagate_vest(d, ss.get(wkey)))
    return _f


def cb_week(wkey: str, plan: dict):
    def _f():
        mutate(lambda d: L.retarget_week(d, plan, int(ss.get(wkey) or 1)))
        for k in list(ss.keys()):
            if isinstance(k, str) and k.startswith("sl|"):
                del ss[k]
    return _f


def go_block(i: int):
    def _f():
        if ss.get("draft"):
            ss.draft["blockIndex"] = i
    return _f


def wk(*parts) -> str:
    return "w|" + "|".join(str(p) for p in parts)


def init_widget(key: str, value):
    if key not in ss:
        ss[key] = value


# ======================================================================= HOME
def render_home(plan: dict) -> None:
    sett = S.settings()
    logs = S.logs()
    order = plan.get("progression", {}).get("schedule", {}).get("order") or P.session_ids(plan)
    week_auto = S.current_week(sett)
    weeks_total = int(sett.get("cycleWeeks") or 8)

    U.page_title("Allenamento", "allena")
    S.mode_banner()
    if ss.get("draft_error"):
        U.msg(f"Non riesco a leggere dal server se c'è una seduta in corso: {U.esc(ss.draft_error)}", "err")
        st.caption("Per non sovrascrivere dati, non puoi iniziare una nuova seduta finché la lettura non riesce.")
        if st.button("Riprova", icon=":material/refresh:", type="primary", width="stretch"):
            st.rerun()
        T.bridge(draft=None, synced_rev=0, visible=False)
        return
    if ss.get("start_error"):
        U.msg(U.esc(ss.pop("start_error")), "warn")

    # ---- seduta appena salvata
    last = ss.get("last_saved")
    if last:
        log = last["log"]
        done = sum(len(L.work_sets(e)) for e in log["exercises"] if L.is_countable(e))
        U.msg(f"<b>Seduta {U.esc(log['sessionId'])} del {date.fromisoformat(log['date']).strftime('%d/%m')} salvata</b>"
              f" · {done} serie di lavoro.", "ok")
        for m in last.get("prs", []):
            U.msg(U.esc(m), "ok", "trophy")
        for x in last.get("declines", []):
            U.msg(f"<b>{U.esc(x['name'])}</b> è peggiorato 2 sedute di fila ({', '.join(x['dates'])}): "
                  "valuta una settimana di scarico (metà serie, stesso carico).", "warn", "down")

    # ---- bozza sul telefono più recente di quella sul server?
    mount = ss.get("bridge_mount") or {}
    stored = mount.get("stored")
    server = ss.get("draft")
    already_saved = stored and any(l.get("draftId") == stored.get("id") for l in logs)
    if stored and already_saved:
        ss.clear_id = stored.get("id")
    elif stored and stored.get("id") != (ss.get("clear_id") or "") and (
            not server or (server.get("id") == stored.get("id") and int(stored.get("rev", 0)) > int(server.get("rev", 0)))):
        dn, tot = L.draft_progress(stored)
        U.msg(f"Sul telefono c'è una bozza della seduta <b>{U.esc(stored.get('sessionId'))}</b> del "
              f"{U.esc(stored.get('date'))} ({dn}/{tot} fatte) più recente di quella sul server.", "warn", "phone")
        if st.button("Ripristina la bozza dal telefono", icon=":material/restore:", type="primary", width="stretch"):
            restore_from_phone(stored)
            st.rerun()

    # ---- bozza in corso sul server
    if server:
        dn, tot = L.draft_progress(server)
        U.card(f'<div class="mut">Seduta in corso</div><div class="big">Seduta {U.esc(server["sessionId"])} · '
               f'settimana {server.get("cycleWeek")}</div><div class="mut">{U.esc(server.get("sessionTitle") or "")}<br>'
               f'Iniziata il {U.esc(server.get("date"))} · {dn}/{tot} completati</div>')
        if st.button("Riprendi la seduta", icon=":material/play_arrow:", type="primary", width="stretch"):
            ss.in_session = True
            st.rerun()
        with st.expander("Scarta la seduta in corso"):
            st.caption("Le serie registrate in questa bozza verranno perse.")
            if st.checkbox("Confermo, voglio scartarla", key="confirm_discard_home"):
                if st.button("Scarta bozza", icon=":material/delete:", width="stretch"):
                    discard_session()
                    st.rerun()
        T.bridge(draft=None, synced_rev=0, clear=ss.get("clear_id"), visible=False)
        return

    nxt = L.next_session_id(logs, order)
    if week_auto > weeks_total:
        U.msg(f"Il ciclo di {weeks_total} settimane è terminato (siamo alla settimana {week_auto}). "
              "Imposta la data del nuovo ciclo in Impostazioni.")
    choice = st.segmented_control("Seduta", order, default=nxt, key="home_sid",
                                  format_func=lambda s: f"Seduta {s}" + (" · prossima" if s == nxt else ""), width="stretch")
    sid = choice or nxt
    sess = P.get_session(plan, sid)
    week = st.number_input("Settimana di ciclo", 1, 12, value=min(week_auto, 12), step=1, key="home_week",
                           help=f"Calcolata dalla data di inizio ciclo ({sett.get('cycleStartDate')}): {week_auto}. "
                                "Cambiala se hai saltato sedute o fatto uno scarico.")
    g = P.pullup_group(plan, int(week))
    pull = (g or {}).get("text", {}).get(sid, "")
    extra = f"Trazioni <b>{U.esc(pull)}</b>" if pull else ""
    if sid == "C" and g:
        extra += f" · giubbotto <b>{g.get('vestKg')} kg</b>"
    last_same = L.last_log_of_session(logs, sid)
    when = f"Ultima {sid}: {date.fromisoformat(last_same['date']).strftime('%d/%m')}" if last_same else f"Prima seduta {sid}"
    blocks = " · ".join(P.block_short(b) for b in sess["blocks"])
    U.card(f'<div class="mut">{"Prossima in rotazione A → B → C" if sid == nxt else "Scelta manuale"} · '
           f'settimana {int(week)} di {weeks_total}</div><div class="big">{U.esc(session_short_title(sess))}</div>'
           f'<div class="mut">{U.esc(blocks)}<br>{extra}{"<br>" if extra else ""}{when}</div>')
    if st.button(f"Inizia seduta {sid}", icon=":material/play_arrow:", type="primary", width="stretch"):
        start_session(plan, sid, int(week), week_auto)
        sync_draft()
        st.rerun()

    decl = L.declines(logs)
    for x in decl:
        U.msg(f"<b>{U.esc(x['name'])}</b> (seduta {x['sessionId']}) peggiorato 2 sedute di fila: valuta lo scarico.",
              "warn", "down")
    if logs:
        st.markdown("#### Ultime sedute")
        for log in list(reversed(logs))[:3]:
            st.caption(f"**{date.fromisoformat(log['date']).strftime('%d/%m')} · Seduta {log['sessionId']}** — "
                       f"{L.summarize_log(log) or '—'}")
    T.bridge(draft=None, synced_rev=0, clear=ss.get("clear_id"), visible=False)


def session_short_title(sess: dict) -> str:
    """"Squat + Panca inclinata | trazioni corpo libero · ≈50'" → "Squat + Panca inclinata"."""
    t = sess.get("subtitle") or sess.get("title") or sess.get("id")
    return t.split("|")[0].split("·")[0].strip()


# ======================================================================= SEDUTA
def cb_toggle(wkey: str):
    def _f():
        ss[wkey] = not ss.get(wkey, False)
    return _f


def cb_pick(block_id: str, i: int, done_total: int):
    def _f():
        ss[wk("pick", block_id)] = (i, done_total)
    return _f


def _done_count(ex: dict) -> int:
    return sum(1 for s in ex.get("sets", []) if s.get("done"))


def render_block_exercise(plan: dict, d: dict, block: dict, ex_def: dict, videos: dict, sett: dict,
                          next_info: dict | None = None) -> None:
    """Card dell'esercizio attivo (stile Studio): tessera, nome, prescrizione, tasto video, cue,
    serie a chip, stepper kg/rip e "Fatta, avvia recupero"; sotto, dettagli, dolore e nota."""
    ex = L.find_ex(d, f"{block['id']}:{ex_def['id']}")
    if ex is None:
        return
    presc = ex.get("prescription") or {}
    used_alt = bool(ex.get("usedAlternative"))
    vkey = wk("vid", ex["key"])
    with st.container(key=f"excard_{ex['key'].replace(':', '_')}"):
        with st.container(key=f"exhead_{ex['key'].replace(':', '_')}"):
            c1, c2 = st.columns([1, 0.2], vertical_alignment="center")
            with c1:
                U.html_block(U.exercise_title(ex_def, presc))
            with c2:
                on = bool(ss.get(vkey))
                st.button(":material/smart_display:", key=("vidon_" if on else "vid_") + ex["key"].replace(":", "_"),
                          help="Chiudi il video" if on else "Apri il video tutorial", on_click=cb_toggle(vkey))
        if ss.get(vkey):
            U.show_video(P.resolve_video(ex_def, videos, alternative=used_alt))
        U.exercise_cue(ex_def, used_alt=used_alt)
        sugg = L.suggest_progression(plan, d["sessionId"], ex["exerciseId"], S.logs()) if ex.get("sets") else None
        if sugg and not used_alt:
            st.caption(sugg.get("short") or sugg["text"])
        if ex.get("warmupSets"):
            labels = [f"{L.fmt_kg(w['kg'])}×{w['reps']}" for w in ex["warmupSets"]]
            k = wk("wu", ex["key"])
            init_widget(k, [lab for lab, w in zip(labels, ex["warmupSets"]) if w.get("done")])
            st.pills("Avvicinamento (non conta nel volume)", labels, selection_mode="multi", key=k,
                     on_change=cb_warmup_sets(ex["key"], k, labels))
        if ex.get("sets"):
            T.set_logger(key=f"sl|{d['id']}|{ex['key']}", draft_id=d["id"], ex=ex,
                         synced_rev=int(ss.get("synced_rev", 0)), draft_rev=int(d.get("rev", 0)), settings=sett,
                         rest_label=(next_info or {}).get("label", ""), kg_step=L.kg_step(ex_def), next_info=next_info)
        else:
            k = wk("done", ex["key"])
            init_widget(k, bool(ex.get("done")))
            st.checkbox("Fatto", key=k, on_change=cb_ex_field(ex["key"], "done", k))
        if ex.get("painCheck"):
            k = wk("pain", ex["key"])
            init_widget(k, ex.get("pain"))
            st.pills(f"Dolore {ex['painCheck']} (0 = nessuno)", list(range(11)), key=k,
                     on_change=cb_ex_field(ex["key"], "pain", k))
            if (ss.get(k) or 0) >= 4:
                U.msg("Dolore ≥ 4: fermati e passa all'alternativa (non spingere sul dolore).", "warn", "alert")
        has_alt = bool(ex_def.get("alternative")) and ex_def["alternative"] != "-"
        with st.expander(":material/info: Dettagli", expanded=False):
            U.exercise_details(ex_def, presc)
            if sugg and not used_alt:
                st.caption("Suggerimento: " + sugg["text"])
            if has_alt:
                k = wk("alt", ex["key"])
                init_widget(k, used_alt)
                st.toggle("Uso l'alternativa", key=k, on_change=cb_alt(ex["key"], k))
            k = wk("note", ex["key"])
            init_widget(k, ex.get("note") or "")
            st.text_input("Nota esercizio (es. RIR reale, sensazioni)", key=k,
                          on_change=cb_ex_field(ex["key"], "note", k), placeholder="facoltativa")


def render_partner(d: dict, block: dict, ex_def: dict, i: int, done_total: int) -> None:
    """Card compatta dell'esercizio che non tocca adesso (toccala per aprirla)."""
    ex = L.find_ex(d, f"{block['id']}:{ex_def['id']}")
    if ex is None:
        return
    presc = ex.get("prescription") or {}
    n_done, n_tot = _done_count(ex), len(ex.get("sets", []))
    rmin, rmax = presc.get("repsMin"), presc.get("repsMax")
    reps = f"{rmin}" if rmin == rmax or rmax is None else f"{rmin}-{rmax}"
    sub = (f"{presc.get('setsTarget')} × {reps} · {n_done} di {n_tot} fatte" if n_tot
           else ("fatto" if ex.get("done") else "da fare"))
    with st.container(key=f"pc_{ex['key'].replace(':', '_')}"):
        U.html_block(f'<div class="pcard">{U.exercise_title(ex_def, presc, sub=U.esc(sub), muted=True)}</div>')
        st.button(f"Apri {ex_def['name']}", key=f"pick_{ex['key']}", on_click=cb_pick(block["id"], i, done_total))


def render_exercise_block(plan: dict, d: dict, block: dict, videos: dict, sett: dict) -> None:
    exs = block["exercises"]
    keys = [f"{block['id']}:{x['id']}" for x in exs]
    grouped = block.get("type") in ("superset", "circuit") and len(exs) > 1
    if not grouped:
        for e in exs:
            render_block_exercise(plan, d, block, e, videos, sett)
        return
    done_total = sum(_done_count(L.find_ex(d, k) or {}) for k in keys)
    act = L.active_exercise(d, keys)
    pick = ss.get(wk("pick", block["id"]))
    if pick and pick[1] == done_total and 0 <= pick[0] < len(exs):
        act = pick[0]          # scelto a mano: vale finché non registri un'altra serie del blocco
    word = "in superset con" if block.get("type") == "superset" else "in circuito con"
    render_block_exercise(plan, d, block, exs[act], videos, sett, next_info=L.rest_info(d, keys, act))
    order = list(range(act + 1, len(exs))) + list(range(0, act))
    for j in order:
        U.html_block(f'<div class="sup"><i></i>{word}</div>')
        render_partner(d, block, exs[j], j, done_total)


def cb_rounds(ex_key: str, wkey: str, labels: list[str]):
    def _f():
        chosen = set(ss.get(wkey) or [])
        mutate(lambda d: L.set_rounds(d, ex_key, [lab in chosen for lab in labels], S.now_ms()))
    return _f


def render_warmup(d: dict, block: dict, videos: dict) -> None:
    names = [e["name"] for e in block["exercises"]]
    st.caption("Un esercizio al minuto, 2 giri: spunta ogni giro. Col timer EMOM i giri si spuntano da soli a fine minuto.")
    if st.toggle(":material/timer: Timer EMOM 1'", key=wk("emom", block["id"])):
        v = T.emom_timer(names, minutes=10, storage_key=f"{d['id']}_{block['id']}", key=f"emom|{d['id']}|{block['id']}")
        if isinstance(v, dict) and v.get("done"):
            if L.apply_emom(d, block["id"], int(v["done"]), S.now_ms()):
                L.bump(d, S.now_ms())
                sync_draft()
                d = ss.draft
                for e in block["exercises"]:
                    ss.pop(wk("rounds", f"{block['id']}:{e['id']}"), None)
    with st.container(key="box_warmup"):
        for e in block["exercises"]:
            ex = L.find_ex(d, f"{block['id']}:{e['id']}")
            rounds = ex.get("rounds") or [bool(ex.get("done"))]
            labels = [f"{i + 1}° giro" for i in range(len(rounds))]
            k = wk("rounds", ex["key"])
            init_widget(k, [lab for lab, r in zip(labels, rounds) if r])
            U.html_block(U.exercise_title(e, {}, sub=U.esc(f"{e.get('setsText') or ''}" + (f" · {e['cue']}" if e.get("cue") else ""))))
            st.pills(f"Giri {e['name']}", labels, selection_mode="multi", key=k, label_visibility="collapsed",
                     on_change=cb_rounds(ex["key"], k, labels))
    with st.expander(":material/info: Note, alternative e video del riscaldamento"):
        for e in block["exercises"]:
            st.markdown(f"**{e['name']}** — {e.get('notes') or ''}  \nAlternativa: {e.get('alternative') or '-'}")
            U.video_toggle(e, videos, key=f"vid|{block['id']}:{e['id']}")


def render_finish(plan: dict, d: dict) -> None:
    st.markdown("### Fine seduta")
    dn, tot = L.draft_progress(d)
    open_sets = sum(1 for e in d["exercises"] for s in e.get("sets", []) if not s.get("done"))
    st.progress(dn / tot if tot else 0, text=f"{dn}/{tot} completati")
    if open_sets:
        st.caption(f"{open_sets} serie non confermate: non verranno salvate.")
    k = wk("bw")
    init_widget(k, d.get("bodyweightKg"))
    st.number_input("Peso corporeo oggi (kg, facoltativo)", min_value=30.0, max_value=200.0, step=0.1, value=None,
                    key=k, on_change=cb_field("bodyweightKg", k), placeholder="es. 75.0")
    k = wk("energy")
    init_widget(k, d.get("energy"))
    st.pills("Energia (1 = a terra, 5 = al top)", [1, 2, 3, 4, 5], key=k, on_change=cb_field("energy", k))
    k = wk("tennis")
    init_widget(k, d.get("tennis") or "")
    st.text_input("Attività extra della settimana (sport, camminate…)", key=k, on_change=cb_field("tennis", k),
                  placeholder="es. tennis martedì 1h, gomito ok")
    k = wk("notes")
    init_widget(k, d.get("notes") or "")
    st.text_area("Note seduta (sensazioni, spalla, gomiti, sonno…)", key=k, on_change=cb_field("notes", k))
    if ss.get("finish_error"):
        U.msg(U.esc(ss.finish_error), "err")
    if st.button("Termina e salva seduta", icon=":material/check:", type="primary", width="stretch"):
        finish_session()
        st.rerun()
    with st.expander("Scarta questa seduta"):
        if st.checkbox("Confermo: elimina la bozza senza salvare", key="confirm_discard"):
            if st.button("Scarta", icon=":material/delete:", width="stretch"):
                discard_session()
                st.rerun()


def cb_block_pill(wkey: str, labels: list[str]):
    def _f():
        v = ss.get(wkey)
        if v in labels and ss.get("draft"):
            ss.draft["blockIndex"] = labels.index(v)
    return _f


def render_session(plan_for_draft: dict) -> None:
    d = ss.draft
    sett = S.settings()
    videos = S.videos()
    plan = plan_for_draft
    try:
        sess = P.get_session(plan, d["sessionId"])
    except KeyError:
        U.msg("La seduta della bozza non esiste più nel piano attivo.", "err")
        return
    blocks = sess["blocks"]
    n_steps = len(blocks) + 1
    idx = max(0, min(int(d.get("blockIndex", 0)), n_steps - 1))

    # ---- intestazione: "Seduta A · Settimana 1", titolo, anello dei blocchi
    dn, tot = L.draft_progress(d)
    U.html_block(f'<div class="ss-h"><div><div class="k">Seduta {U.esc(d["sessionId"])} · Settimana {d.get("cycleWeek")}</div>'
            f'<div class="t">{U.esc(session_short_title(sess))}</div>'
            f'<div class="b">{U.sync_badge(d, int(ss.get("synced_rev", 0)), ss.get("sync_error"))}'
            f'{U.pill(f"{dn}/{tot} fatti")}</div></div>{U.ring(idx + 1, n_steps)}</div>')
    if ss.get("sync_error"):
        st.caption(f"Sincronizzazione non riuscita: {ss.sync_error}")
        if st.button("Riprova a sincronizzare", icon=":material/sync:", key="retry_sync"):
            st.rerun()
    T.bridge(draft=d, synced_rev=int(ss.get("synced_rev", 0)), clear=ss.get("clear_id"), visible=False)

    # ---- linguette dei blocchi (toccabili)
    labels = [P.block_short(b) for b in blocks] + ["Fine"]
    seen = {}
    for i, lab in enumerate(labels):  # nomi unici per st.pills
        seen[lab] = seen.get(lab, 0) + 1
        if seen[lab] > 1:
            labels[i] = f"{lab} {seen[lab]}"
    pk = wk("blocks", d["id"], idx)
    ss[pk] = labels[idx]
    with st.container(key="blockpills"):
        st.pills("Blocchi", labels, key=pk, label_visibility="collapsed", required=True, on_change=cb_block_pill(pk, labels))

    if idx < len(blocks):
        block = blocks[idx]
        U.html_block(f'<div class="blk-title">{U.esc(block["title"])}</div>')
        if block.get("type") == "warmup":
            render_warmup(d, block, videos)
        else:
            if any(e.get("loadFrom") == "giubbotto" for e in block["exercises"]):
                k = wk("vest")
                init_widget(k, d.get("vestKg"))
                g = P.pullup_group(plan, int(d.get("cycleWeek") or 1))
                st.number_input(f"Giubbotto per tutto il blocco (kg) · previsto {g.get('vestKg') if g else '–'}",
                                min_value=0.0, max_value=40.0, step=1.0, key=k, on_change=cb_vest(k))
            render_exercise_block(plan, d, block, videos, sett)
    else:
        render_finish(plan, d)

    with st.expander(":material/calendar_month: Dati seduta: data, settimana, home"):
        k = wk("date")
        init_widget(k, date.fromisoformat(d["date"]))
        st.date_input("Data", key=k, format="DD/MM/YYYY",
                      on_change=lambda: mutate(lambda dd: dd.__setitem__("date", ss[wk("date")].isoformat())))
        k = wk("week")
        init_widget(k, int(d.get("cycleWeek") or 1))
        st.number_input(f"Settimana di ciclo (calcolata: {d.get('cycleWeekAuto')})", 1, 12, step=1, key=k,
                        on_change=cb_week(k, plan),
                        help="Aggiorna serie di trazioni e giubbotto per gli esercizi non ancora iniziati.")
        if st.button("Torna alla home (la bozza resta salvata)", icon=":material/home:", width="stretch"):
            ss.in_session = False
            st.rerun()

    # ---- navigazione blocchi (in basso, tasti grandi)
    with st.container(key="blocknav"):
        c1, c2, c3 = st.columns([1, 0.3, 1], wrap=False)
    with c1:
        st.button("Blocco", icon=":material/chevron_left:", key="nav_prev", disabled=idx == 0,
                  on_click=go_block(idx - 1), width="stretch")
    with c2:
        U.html_block(f'<div class="navpos">{idx + 1}/{n_steps}</div>')
    with c3:
        st.button("Blocco" if idx < n_steps - 1 else "Fine", icon=":material/chevron_right:", icon_position="right",
                  key="nav_next", disabled=idx >= n_steps - 1, on_click=go_block(idx + 1), type="primary", width="stretch")


# ======================================================================= main
load_draft()
process_component_events()
sync_draft()

draft = ss.get("draft")
if draft and ss.get("in_session"):
    pv = int(draft.get("planVersion") or 1)
    render_session(S.get_plan(pv))
else:
    render_home(S.active_plan())

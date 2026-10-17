"""⚙️ Impostazioni e backup."""
from __future__ import annotations

import json
from datetime import date

import streamlit as st

from lib import logic as L
from lib import services as S
from lib.storage import StorageError

st.markdown("## ⚙️ Impostazioni")
sett = S.settings()
S.mode_banner()

with st.form("settings"):
    start = st.date_input("Inizio ciclo (lunedì della settimana 1)", value=date.fromisoformat(sett.get("cycleStartDate", "2026-10-19")),
                          format="DD/MM/YYYY")
    weeks = st.number_input("Durata ciclo (settimane)", 1, 16, int(sett.get("cycleWeeks") or 8))
    st.markdown("**Timer di recupero**")
    sound = st.toggle("🔔 Beep a fine recupero", value=bool(sett.get("sound", True)))
    vib = st.toggle("📳 Vibrazione a fine recupero", value=bool(sett.get("vibrate", True)))
    wake = st.toggle("💡 Tieni lo schermo acceso durante la seduta (Wake Lock)", value=bool(sett.get("wakeLock", True)))
    if st.form_submit_button("💾 Salva impostazioni", type="primary", width="stretch"):
        if S.save_settings({**sett, "cycleStartDate": start.isoformat(), "cycleWeeks": int(weeks), "sound": sound,
                            "vibrate": vib, "wakeLock": wake}):
            st.success("Impostazioni salvate.")
            sett = S.settings()

wk = S.current_week(sett)
st.caption(f"Oggi siamo nella settimana **{wk}** del ciclo (inizio {sett.get('cycleStartDate')}). "
           "Nella seduta puoi comunque cambiarla a mano.")

st.markdown("### 💾 Backup")
ds = S.store()
c1, c2 = st.columns(2)
try:
    bundle = S.export_bundle()
    stamp = S.today_local().isoformat()
    with c1:
        st.download_button("⬇️ Esporta JSON", json.dumps(bundle, ensure_ascii=False, indent=1).encode("utf-8"),
                           file_name=f"allenamento-backup-{stamp}.json", mime="application/json", width="stretch")
    with c2:
        st.download_button("⬇️ Esporta CSV", L.logs_to_csv(bundle["logs"]).encode("utf-8"),
                           file_name=f"allenamento-serie-{stamp}.csv", mime="text/csv", width="stretch")
    st.caption(f"{len(bundle['logs'])} sedute · {len(bundle['bodyweight'])} pesate · {len(bundle['plans'])} versioni del piano.")
except StorageError as exc:
    st.error(f"⚠️ Export non disponibile: {exc}")

with st.expander("⬆️ Importa backup (JSON o CSV)"):
    up = st.file_uploader("File di backup", type=["json", "csv"])
    overwrite = st.checkbox("Sovrascrivi le sedute con lo stesso id", value=False)
    with_settings = st.checkbox("Importa anche le impostazioni (solo JSON)", value=False)
    if up is not None and st.button("Importa", type="primary", width="stretch"):
        try:
            raw = up.getvalue().decode("utf-8-sig")
            if up.name.lower().endswith(".csv"):
                rep = ds.import_logs(L.csv_to_logs(raw), overwrite=overwrite)
            else:
                rep = ds.import_bundle(json.loads(raw), overwrite=overwrite, include_settings=with_settings)
            S.invalidate()
            st.success(f"Importate {rep['logs_added']} sedute, sovrascritte {rep['logs_overwritten']}, saltate "
                       f"{rep['logs_skipped']}; piani aggiunti {rep['plans_added']}; pesate {rep['bodyweight']}.")
            for e in rep["errors"]:
                st.warning(e)
        except (ValueError, StorageError) as exc:
            st.error(f"⚠️ Import fallito: {exc}")

st.markdown("### 🔌 Connessione dati")
kind = S.backend_kind()
if kind == "github":
    if st.button("Verifica connessione GitHub", width="stretch"):
        info = ds.st.status()
        if info.get("ok"):
            st.success(f"Connesso a **{info['repo']}** (branch `{info['branch']}`, privato: {info.get('private')}). "
                       f"Richieste API rimaste: {info.get('rate', {}).get('remaining', '?')}")
        else:
            st.error(info.get("error"))
    else:
        st.caption(f"Backend GitHub: repo `{ds.st.repo}`, branch dati `{ds.st.branch}`.")
else:
    from pathlib import Path
    st.caption(f"Backend locale: cartella `{Path(ds.st.status().get('root', '')).name}/` sul computer che esegue l'app.")

caps = (st.session_state.get("bridge_mount") or {}).get("caps") or {}
if caps:
    st.markdown("**Questo telefono supporta:** " + " · ".join(
        f"{lab} {'✅' if caps.get(k) else '❌'}" for k, lab in (("vibrate", "vibrazione"), ("wakeLock", "schermo acceso"), ("audio", "audio"))))

if st.button("🔄 Ricarica dati dal server", width="stretch"):
    S.invalidate()
    ss = st.session_state
    local = ss.get("draft")
    unsynced = bool(local) and int(local.get("rev", 0)) > int(ss.get("synced_rev", 0))
    try:
        remote = ds.get_draft()
        merged = L.reconcile_drafts(local, remote, unsynced)
        ss.draft = merged
        # se l'unione contiene qualcosa che il server non ha, verrà inviata al prossimo passaggio
        ss.synced_rev = int(remote.get("rev", 0)) if (remote and merged is remote) else int(ss.get("synced_rev", 0))
        if merged is None:
            ss.synced_rev = 0
        ss.draft_loaded = True
        st.success("Dati ricaricati" + (" (le serie non ancora inviate sono state conservate)." if unsynced else "."))
    except StorageError as exc:
        st.error(f"⚠️ Ricarica non riuscita, i dati locali restano invariati: {exc}")

st.markdown("### 📱 Dispositivi autorizzati")
devs = list(sett.get("devices") or [])
if not S._secrets().get("APP_PASSWORD"):
    st.caption("Login disattivato (nessuna APP_PASSWORD): niente dispositivi da gestire.")
elif not devs:
    st.caption("Nessun dispositivo memorizzato.")
for dv in devs:
    c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
    with c1:
        me = " · **questo**" if dv.get("id") == st.session_state.get("device_id") else ""
        st.markdown(f"**{dv.get('name')}** — dal {dv.get('created')}{me}")
    with c2:
        if st.button("Revoca", key=f"rev_{dv.get('id')}", width="stretch"):
            from lib import auth as A
            cur = ds.get_settings()
            if S.save_settings({**cur, "devices": A.revoke(list(cur.get("devices") or []), dv.get("id"))}):
                st.rerun()

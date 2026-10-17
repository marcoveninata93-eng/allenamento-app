"""Collante Streamlit: configurazione da st.secrets, backend, login, cache e helper di stato."""
from __future__ import annotations

import hashlib
import hmac
import os
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import streamlit as st

from . import auth as A
from . import logic as L
from . import plan as P
from .storage import DataStore, GitHubStorage, StorageError, make_storage

ROOT = Path(__file__).resolve().parent.parent
TZ = ZoneInfo("Europe/Rome")


# ------------------------------------------------------------------ config
def _secrets() -> dict:
    out = {}
    try:
        for k in ("GITHUB_TOKEN", "GITHUB_REPO", "DATA_BRANCH", "APP_PASSWORD"):
            if k in st.secrets:
                out[k] = str(st.secrets[k])
    except Exception:  # nessun secrets.toml
        pass
    return out


@st.cache_resource(show_spinner=False)
def get_backend():
    """Backend condiviso (connessione + cache dei file per SHA, sicura da condividere)."""
    sec = _secrets()
    local_dir = os.environ.get("ALLENAMENTO_LOCAL_DIR") or str(ROOT / "local_data")
    storage, warn = make_storage(sec, local_dir)
    return storage, storage.kind, warn


def store() -> DataStore:
    """DataStore PER SESSIONE: gli SHA dei file non vengono condivisi tra schede/dispositivi."""
    ds = st.session_state.get("_datastore")
    if ds is None or ds.st is not get_backend()[0]:
        ds = st.session_state["_datastore"] = DataStore(get_backend()[0])
    return ds


def backend_kind() -> str:
    return get_backend()[1]


def now_local() -> datetime:
    return datetime.now(TZ)


def today_local() -> date:
    return now_local().date()


def now_ms() -> int:
    return int(time.time() * 1000)


# ------------------------------------------------------------------ login
@st.cache_resource(show_spinner=False)
def _limiter() -> A.RateLimiter:
    """Condiviso dal server: il limite vale anche aprendo nuove schede."""
    return A.RateLimiter(max_fails=5, window=600)


def _devices() -> list[dict]:
    return list(store().get_settings().get("devices") or [])


def require_login() -> None:
    from . import timer as T  # import locale: evita di caricare i componenti nei test

    sec = _secrets()
    pw = sec.get("APP_PASSWORD")
    if backend_kind() == "github" and not pw:
        st.error("🔒 Backend GitHub configurato ma manca **APP_PASSWORD** nei Secrets: per sicurezza l'app non "
                 "legge né scrive dati finché non la imposti.")
        st.markdown("Streamlit Community Cloud → la tua app → **⋮ → Settings → Secrets** e aggiungi:\n\n"
                    "```toml\nAPP_PASSWORD = \"una-password-lunga\"\n```\n\nSalva: l'app si riavvia da sola.")
        st.stop()
    if "k" in st.query_params:  # vecchia chiave nell'indirizzo: non più usata
        del st.query_params["k"]
    if not pw:
        return
    ss = st.session_state
    if ss.get("authed"):
        if ss.get("_auth_write"):  # scrive il token nel browser (resta finché dura la sessione)
            T.auth_bridge(set_token=ss["_auth_write"])
        return

    v = T.auth_bridge(clear=bool(ss.get("_auth_clear")))
    if isinstance(v, dict) and v.get("type") == "auth" and ss.get("_auth_nonce") != v.get("nonce"):
        ss._auth_nonce = v.get("nonce")
        if v.get("token"):
            try:
                dev = A.verify_token(v["token"], _devices())
            except StorageError as exc:
                st.error(f"Non riesco a verificare questo dispositivo: {exc}")
                dev = None
            if dev:
                ss.authed, ss.device_id = True, dev.get("id")
                st.rerun()
            elif not ss.get("_auth_clear"):
                ss._auth_clear = True  # token revocato o sconosciuto: lo tolgo dal browser
                st.rerun()

    st.markdown("## 🏋️ Allenamento")
    wait = _limiter().locked_for()
    if wait > 0:
        st.error(f"Troppi tentativi errati. Riprova tra {int(wait // 60) + 1} minuti.")
        st.stop()
    with st.form("login"):
        val = st.text_input("Password", type="password")
        name = st.text_input("Nome di questo dispositivo", value="Telefono",
                             help="Serve per riconoscerlo (e revocarlo) in ⚙️ Impostazioni.")
        remember = st.checkbox("Ricorda questo dispositivo", value=True)
        ok = st.form_submit_button("Entra", type="primary", width="stretch")
    if ok:
        if A.check_password(val, pw):
            _limiter().success()
            ss.authed = True
            if remember:
                token, rec = A.new_device(name, today_local().isoformat())
                try:
                    cur = store().get_settings()
                    store().save_settings({**cur, "devices": list(cur.get("devices") or []) + [rec]})
                    invalidate()
                    ss._auth_write, ss.device_id = token, rec["id"]
                except StorageError as exc:
                    st.warning(f"Accesso consentito, ma il dispositivo non è stato memorizzato: {exc}")
            st.rerun()
        else:
            _limiter().fail()
            time.sleep(1.0)
            wait = _limiter().locked_for()
            if wait > 0:
                st.error(f"Password errata. Troppi tentativi errati: riprova tra {int(wait // 60) + 1} minuti.")
            else:
                st.error(f"Password errata. Tentativi rimasti: {5 - len(_limiter().fails)}.")
    st.stop()


# ------------------------------------------------------------------ bootstrap e cache
def bootstrap() -> None:
    if st.session_state.get("_booted"):
        return
    try:
        store().bootstrap(P.load_default_plan())
    except StorageError as exc:
        st.error(f"Impossibile inizializzare l'archivio dati: {exc}")
        st.stop()
    st.session_state._booted = True


@st.cache_data(ttl=300, show_spinner=False)
def _logs(_ds_id: int, token: int) -> list[dict]:
    return DataStore(get_backend()[0]).load_logs()


@st.cache_data(ttl=300, show_spinner=False)
def _settings(_ds_id: int, token: int) -> dict:
    return DataStore(get_backend()[0]).get_settings()


@st.cache_data(ttl=3600, show_spinner=False)
def _plan(_ds_id: int, version: int, token: int) -> dict | None:
    return DataStore(get_backend()[0]).get_plan(version)


@st.cache_data(ttl=300, show_spinner=False)
def _plan_versions(_ds_id: int, token: int) -> list[int]:
    return DataStore(get_backend()[0]).list_plan_versions()


@st.cache_data(ttl=300, show_spinner=False)
def _bodyweight(_ds_id: int, token: int) -> list[dict]:
    return DataStore(get_backend()[0]).get_bodyweight()


@st.cache_data(show_spinner=False)
def videos() -> dict:
    return P.load_videos()


def _tok() -> int:
    return st.session_state.setdefault("_data_token", 0)


def invalidate() -> None:
    """Da chiamare dopo ogni scrittura."""
    st.session_state["_data_token"] = _tok() + 1
    for f in (_logs, _settings, _plan_versions, _bodyweight):
        f.clear()


def safe(fn, *a, default=None, **kw):
    try:
        return fn(*a, **kw)
    except StorageError as exc:
        st.error(f"⚠️ {exc}")
        return default


def logs() -> list[dict]:
    return safe(_logs, id(get_backend()[0]), _tok(), default=[]) or []


def settings() -> dict:
    return safe(_settings, id(get_backend()[0]), _tok(), default={}) or {}


def plan_versions() -> list[int]:
    return safe(_plan_versions, id(get_backend()[0]), _tok(), default=[1]) or [1]


def active_plan() -> dict:
    v = int(settings().get("activePlanVersion") or 1)
    return get_plan(v)


def get_plan(v: int) -> dict:
    p = safe(_plan, id(get_backend()[0]), int(v), _tok())
    if not p:
        p = P.load_default_plan()
    return p


def bodyweight() -> list[dict]:
    return safe(_bodyweight, id(get_backend()[0]), _tok(), default=[]) or []


def save_settings(new: dict) -> bool:
    try:
        store().save_settings(new)
    except StorageError as exc:
        st.error(f"⚠️ Impostazioni non salvate: {exc}")
        return False
    invalidate()
    return True


def current_week(s: dict | None = None, d: date | None = None) -> int:
    s = s or settings()
    return L.cycle_week(d or today_local(), s.get("cycleStartDate"), int(s.get("cycleWeeks") or 8))


def mode_banner() -> None:
    ds, kind, warn = get_backend()
    if warn:
        st.warning(warn)
    if kind == "local":
        st.info("💾 **Modalità locale**: i dati sono salvati in `local_data/` su questo computer "
                "(nessun GitHub configurato nei Secrets).", icon="ℹ️")


def export_bundle() -> dict:
    """Backup completo costruito dai dati in cache (nessuna richiesta extra a GitHub)."""
    return {"format": "allenamento-backup", "schema": L.SCHEMA,
            "exportedAt": now_local().isoformat(timespec="seconds"), "settings": settings(),
            "bodyweight": bodyweight(), "plans": [get_plan(v) for v in plan_versions()],
            "logs": logs(), "draft": st.session_state.get("draft")}

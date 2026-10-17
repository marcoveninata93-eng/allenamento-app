"""Componenti UI riutilizzabili e CSS mobile."""
from __future__ import annotations

import html

import streamlit as st

from . import logic as L
from . import plan as P

ACCENT = "#FF7A1A"

CSS = """
<style>
/* ---- layout mobile ---- */
.block-container, [data-testid="stMainBlockContainer"] { padding: 0.7rem 0.75rem 7.5rem !important; max-width: 760px; }
header[data-testid="stHeader"] { display: none !important; }
h1 { font-size: 1.55rem !important; } h2 { font-size: 1.3rem !important; } h3 { font-size: 1.12rem !important; }
/* ---- tasti grandi ---- */
.stButton button, .stDownloadButton button, .stFormSubmitButton button, [data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"] {
  min-height: 48px; border-radius: 12px; font-weight: 650; font-size: 1rem; }
.stButton button[kind="primary"], [data-testid="stBaseButton-primary"] { min-height: 54px; font-size: 1.08rem; }
/* ---- input grandi ---- */
input, textarea, [data-baseweb="select"] > div { font-size: 17px !important; }
[data-testid="stNumberInput"] input { min-height: 46px; }
[data-testid="stNumberInput"] button { min-width: 44px; }
[data-testid="stCheckbox"] label { min-height: 40px; align-items: center; padding: 4px 0; }
[data-testid="stCheckbox"] label p { font-size: 1rem; }
[data-testid="stExpander"] summary { min-height: 46px; }
/* ---- card esercizio ---- */
.ex-h { display:flex; align-items:baseline; gap:8px; margin: 2px 0 0; }
.ex-code { background:#FF7A1A; color:#141414; font-weight:800; border-radius:8px; padding:1px 7px; font-size:.9rem; }
.ex-name { font-weight:750; font-size:1.06rem; line-height:1.25; }
.ex-presc { color:#c8cfdc; font-size:.92rem; margin:4px 0 2px; }
.ex-presc b { color:#fff; }
.ex-note { color:#aab3c3; font-size:.86rem; border-left:3px solid #FF7A1A; padding:2px 0 2px 8px; margin:6px 0; }
.blk-title { font-size:.8rem; letter-spacing:.04em; color:#FF9A4D; font-weight:800; text-transform:uppercase; margin-bottom:2px; }
.pill { display:inline-block; padding:2px 9px; border-radius:999px; background:#232a3a; border:1px solid #33405a; font-size:.82rem; margin:0 4px 4px 0; }
.pill.ok { background:#12301f; border-color:#1f6b3d; color:#bdf5d0; }
.pill.warn { background:#3a2a10; border-color:#8a5a12; color:#ffd99a; }
.pill.err { background:#3a1414; border-color:#8a2a2a; color:#ffc2c2; }
.card { background:#161b26; border:1px solid #2a3142; border-radius:14px; padding:12px 14px; margin:6px 0 10px; }
.card .big { font-size:1.35rem; font-weight:800; }
.card .mut { color:#9aa3b5; font-size:.9rem; }
.navpos { text-align:center; color:#9aa3b5; font-size:.9rem; padding-top:12px; }
/* barra di navigazione */
.st-key-navbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; overflow: visible !important; gap: 6px !important; }
.st-key-navbar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
.st-key-navbar [data-testid="stPageLink"] a { justify-content:center; min-height:46px; border-radius:12px; background:#161b26; border:1px solid #2a3142; padding:4px 0; }
.st-key-navbar [data-testid="stPageLink"] a { flex-direction: column; gap: 0 !important; min-height: 54px; }
.st-key-navbar [data-testid="stPageLink"] a span { font-size: 21px; line-height: 1.1; }
.st-key-navbar [data-testid="stPageLink"] a > span:last-child { font-size: 11px; }
.st-key-navbar [data-testid="stPageLink"] p { font-size: 11px !important; line-height: 1.2; margin: 0; white-space: nowrap; color: #c8cfdc; }
.st-key-navactive [data-testid="stPageLink"] a { border-color:#FF7A1A; background:#2a1f16; }
.st-key-blocknav [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important; }
.st-key-blocknav [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
.st-key-blocknav [data-testid="stColumn"]:nth-child(1), .st-key-blocknav [data-testid="stColumn"]:nth-child(3) { flex: 1 1 0 !important; }
.st-key-blocknav [data-testid="stColumn"]:nth-child(2) { flex: 0 0 48px !important; }
.st-key-blocknav button { min-height: 56px !important; }
.st-key-blocknav button p { font-size: 1.05rem !important; font-weight: 700; }
/* niente salto orizzontale */
html, body, [data-testid="stAppViewContainer"] { overflow-x: hidden; }
[data-testid="stIFrame"], iframe { border: 0 !important; }
</style>
"""


def inject_css() -> None:
    st.html(CSS)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def pill(text: str, kind: str = "") -> str:
    return f'<span class="pill {kind}">{esc(text)}</span>'


def card(inner_html: str) -> None:
    st.html(f'<div class="card">{inner_html}</div>')


def exercise_header(ex_def: dict, presc: dict, *, used_alt: bool = False) -> None:
    code = ex_def.get("code") or ""
    name = ex_def["name"]
    parts = []
    if presc.get("setsTarget") and presc.get("repsMin") is not None:
        rmin, rmax = presc.get("repsMin"), presc.get("repsMax")
        reps = f"{rmin}" if rmin == rmax else f"{rmin}-{rmax}"
        parts.append(f"<b>{presc['setsTarget']} × {esc(reps)}</b> {esc(presc.get('repsUnit') or 'rip')}")
    elif ex_def.get("setsText"):
        parts.append(f"<b>{esc(ex_def['setsText'])}</b>")
    if presc.get("tempo") and presc["tempo"] != "-":
        parts.append(f"tempo <b>{esc(presc['tempo'])}</b>")
    if presc.get("rir") and presc["rir"] != "-":
        parts.append(f"RIR <b>{esc(presc['rir'])}</b>")
    if presc.get("rest") and presc["rest"] != "-":
        parts.append(f"rec. {esc(presc['rest'])}")
    if presc.get("phase"):
        parts.append(f"fase <b>{esc(presc['phase'])}</b>")
    alt = f'<div class="ex-presc">🔁 <b>Alternativa in uso:</b> {esc(ex_def.get("alternative"))}</div>' if used_alt else ""
    st.html(
        f'<div class="ex-h">{f"<span class=ex-code>{esc(code)}</span>" if code else ""}'
        f'<span class="ex-name">{esc(name)}</span></div>'
        f'<div class="ex-presc">{" · ".join(parts)}</div>{alt}'
        + (f'<div class="ex-note">{esc(ex_def.get("notes"))}</div>' if ex_def.get("notes") else "")
    )


def video_toggle(ex_def: dict, videos: dict, key: str, alternative: bool = False) -> None:
    """Video incorporato solo su richiesta (un iframe alla volta, pagina leggera)."""
    v = P.resolve_video(ex_def, videos, alternative=alternative)
    label = "▶ Tutorial" + (" (alternativa)" if alternative else "")
    if st.toggle(label, key=key):
        if v["embed"]:
            st.video(v["embed"])
            meta = " · ".join(x for x in [v.get("title"), v.get("channel"), (v.get("lang") or "").upper()] if x)
            st.caption(f"{meta}  \n[Apri su YouTube]({v['url']}) · [Cerca altri video]({v['search']})")
        else:
            st.caption(f"Nessun video scelto per questo esercizio. [Cerca su YouTube]({v['search']})")


def sync_badge(draft: dict, synced_rev: int, error: str | None) -> str:
    pend = L.pending_count(draft, synced_rev)
    unsynced = int(draft.get("rev", 0)) > synced_rev
    if not unsynced:
        return pill("✓ sincronizzato", "ok")
    txt = f"⏳ {pend} serie in attesa" if pend else "⏳ modifiche in attesa"
    if error:
        return pill(txt + " · offline", "err")
    return pill(txt, "warn")


def fmt_presc_short(presc: dict) -> str:
    rmin, rmax = presc.get("repsMin"), presc.get("repsMax")
    reps = f"{rmin}" if rmin == rmax else f"{rmin}-{rmax}"
    return f"{presc.get('setsTarget')}×{reps}"


SHORT = {"Allenamento": "Allena", "Progressi": "Progressi", "Storico": "Storico", "Piano": "Piano",
         "Impostazioni": "Opzioni"}


def nav_bar(pages, current) -> None:
    """Barra di navigazione compatta (icone grandi), visibile anche su telefono."""
    with st.container(key="navbar"):
        cols = st.columns(len(pages), gap="small", wrap=False)
        for c, p in zip(cols, pages):
            with c:
                active = getattr(current, "url_path", None) == p.url_path
                with st.container(key="navactive" if active else f"nav_{p.url_path}"):
                    st.page_link(p, label=SHORT.get(p.title, p.title), icon=p.icon, width="stretch", help=p.title)

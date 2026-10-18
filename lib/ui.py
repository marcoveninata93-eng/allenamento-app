"""Componenti UI riutilizzabili, icone e CSS mobile (stile "Studio")."""
from __future__ import annotations

import html
from urllib.parse import quote

import streamlit as st

from . import logic as L
from . import plan as P

# ---------------------------------------------------------------- palette "Studio"
BG = "#0F1730"
CARD = "#18223F"
LINE = "#2C3A6A"
CHIP = "#24305A"
NOTE = "#1F2A4D"
ACCENT = "#5AB8FF"
FG = "#EEF2FF"
MUTED = "#9DAAD0"
DONE_BG = "#1E3B5E"
DONE_FG = "#8FD0FF"
WARN = "#F4B860"
ERR = "#FF8FA3"

# ---------------------------------------------------------------- icone "Linea" (viewBox 24, tratto 1.75)
ICONS = {
    "allena": '<path d="M6.5 6.5v11M3.5 9v6M17.5 6.5v11M20.5 9v6M6.5 12h11"/>',
    "progressi": '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
    "storico": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><path d="M12 8v4l3 2"/>',
    "piano": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 3h6v3H9z"/><path d="M9 11h6M9 15h4"/>',
    "impostazioni": ('<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/>'
                     '<circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>'),
    "timer": '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7"/>',
    "video": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M10 9.5v5l4.5-2.5z"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    # stesse regole di disegno, per i messaggi
    "alert": '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
    "trophy": '<path d="M8 4h8v5a4 4 0 0 1-8 0z"/><path d="M8 6H5a3 3 0 0 0 3 4M16 6h3a3 3 0 0 1-3 4M12 13v4M9 20h6"/>',
    "down": '<path d="M3 7l6 6 4-4 8 8"/><path d="M15 17h6v-6"/>',
    "phone": '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 18h2"/>',
}


def icon(name: str, size: int = 20, color: str = "currentColor", cls: str = "ic") -> str:
    return (f'<svg class="{cls}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" '
            f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>')


def _mask(name: str) -> str:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="black" '
           f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    return f'url("data:image/svg+xml,{quote(svg)}")'


NAV_KEYS = {"Allenamento": "allenamento", "Progressi": "progressi", "Storico": "storico", "Piano": "piano",
            "Impostazioni": "impostazioni"}
NAV_ICONS = {"allenamento": "allena", "progressi": "progressi", "storico": "storico", "piano": "piano",
             "impostazioni": "impostazioni"}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700&display=swap');
:root { --bg:#0F1730; --card:#18223F; --line:#2C3A6A; --chip:#24305A; --note:#1F2A4D; --acc:#5AB8FF;
  --fg:#EEF2FF; --mut:#9DAAD0; --done:#1E3B5E; --donefg:#8FD0FF; --warn:#F4B860; --err:#FF8FA3; }
html, body, .stApp, [data-testid="stAppViewContainer"], button, input, textarea, select { font-family: 'Outfit', sans-serif !important; }
.stApp, [data-testid="stAppViewContainer"] { background: var(--bg) !important; color: var(--fg); }
/* ---- layout mobile ---- */
.block-container, [data-testid="stMainBlockContainer"] { padding: 0.9rem 1rem 9.5rem !important; max-width: 760px; }
header[data-testid="stHeader"] { display: none !important; }
h1, h2, h3, h4 { font-family: 'Outfit', sans-serif !important; letter-spacing: -0.01em; }
h1 { font-size: 1.6rem !important; } h2 { font-size: 1.45rem !important; font-weight: 700 !important; }
h3 { font-size: 1.15rem !important; } h4 { font-size: 1.02rem !important; color: var(--fg); }
[data-testid="stCaptionContainer"], .stCaption { color: var(--mut) !important; }
a { color: #8FD0FF; }
/* ---- tasti ---- */
.stButton button, .stDownloadButton button, .stFormSubmitButton button {
  min-height: 48px; border-radius: 16px !important; font-weight: 600; font-size: 1rem; border: 0 !important;
  background: var(--chip) !important; color: var(--fg) !important; }
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"], .stDownloadButton button[kind="primary"] {
  min-height: 56px; font-size: 1.08rem; font-weight: 700; border-radius: 18px !important; background: var(--acc) !important; color: var(--bg) !important; }
.stButton button:disabled { opacity: .45; }
.stButton button p, .stDownloadButton button p, .stFormSubmitButton button p { font-weight: inherit; font-size: inherit; }
/* ---- input ---- */
input, textarea, [data-baseweb="select"] > div { font-size: 17px !important; }
[data-baseweb="input"], [data-baseweb="textarea"], [data-baseweb="select"] > div, [data-testid="stNumberInputContainer"] {
  background: var(--chip) !important; border-radius: 14px !important; border-color: transparent !important; }
[data-baseweb="input"] input, [data-baseweb="textarea"] textarea { background: transparent !important; }
[data-testid="stNumberInput"] input { min-height: 46px; }
[data-testid="stNumberInput"] button { min-width: 44px; background: transparent !important; }
[data-testid="stCheckbox"] label { min-height: 40px; align-items: center; padding: 4px 0; }
[data-testid="stCheckbox"] label p { font-size: 1rem; }
[data-testid="stWidgetLabel"] p { color: var(--mut); font-size: .92rem; }
/* ---- card, expander, tabs, alert ---- */
[data-testid="stExpander"] details { background: var(--card); border: 1px solid var(--line) !important; border-radius: 18px !important; }
[data-testid="stExpander"] summary { min-height: 46px; border-radius: 18px; }
[data-testid="stExpander"] summary:hover { color: var(--acc); }
div[data-testid="stVerticalBlock"] > div > div[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 22px; }
.st-key-card, [class*="st-key-excard"], [class*="st-key-box"] {
  background: var(--card); border: 1px solid var(--line) !important; border-radius: 22px !important; padding: 16px !important; }
[data-testid="stAlert"] > div { border-radius: 16px; }
[data-testid="stAlertContainer"] { border-radius: 16px; }
.stTabs [data-baseweb="tab-list"] { gap: 6px; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; }
.stTabs [data-baseweb="tab"] { background: var(--chip); border-radius: 999px; padding: 6px 14px !important; height: auto; color: var(--mut); white-space: nowrap; }
.stTabs [data-baseweb="tab"][aria-selected="true"] { background: var(--acc); color: var(--bg); font-weight: 600; }
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] { display: none; }
.stTabs [role="tablist"] { gap: 6px; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: none; border: 0 !important; padding-bottom: 4px; }
.stTabs [role="tablist"]::-webkit-scrollbar { display: none; }
[data-testid="stTab"] { background: var(--chip); border-radius: 999px; padding: 6px 14px !important; color: var(--mut); white-space: nowrap; flex: 0 0 auto; min-height: 34px; }
[data-testid="stTab"] p { color: inherit !important; font-size: 14px !important; }
[data-testid="stTab"][aria-selected="true"] { background: var(--acc); color: var(--bg); }
[data-testid="stTab"][aria-selected="true"] p { font-weight: 600; }
.stTabs .react-aria-SelectionIndicator { display: none !important; }
[data-testid="stDataFrame"], [data-testid="stTable"] { border-radius: 16px; overflow: hidden; }
/* ---- pillole (st.pills / st.segmented_control) ---- */
button[data-variant="pills"], button[data-variant="segmented_control"] { background: var(--chip) !important; border: 0 !important; color: var(--mut) !important; min-height: 36px; }
button[data-variant="pills"] { border-radius: 999px !important; }
button[data-variant="pills"][data-selected="true"], button[data-variant="segmented_control"][data-selected="true"],
button[data-variant="pills"][aria-checked="true"], button[data-variant="segmented_control"][aria-checked="true"] {
  background: var(--acc) !important; color: var(--bg) !important; }
button[data-variant="pills"][data-selected="true"] p, button[data-variant="segmented_control"][data-selected="true"] p,
button[data-variant="pills"][aria-checked="true"] p, button[data-variant="segmented_control"][aria-checked="true"] p { color: var(--bg) !important; font-weight: 600; }
button[data-variant="segmented_control"] { border-radius: 14px !important; margin: 0 2px; }
[data-testid="stBaseButton-pills"], [data-testid="stBaseButton-segmented_control"] {
  background: var(--chip) !important; border: 0 !important; border-radius: 999px !important; color: var(--mut) !important; min-height: 36px; }
[data-testid="stBaseButton-pillsActive"], [data-testid="stBaseButton-segmented_controlActive"] {
  background: var(--acc) !important; border: 0 !important; border-radius: 999px !important; color: var(--bg) !important; font-weight: 600; min-height: 36px; }
[data-testid="stBaseButton-pillsActive"] p, [data-testid="stBaseButton-segmented_controlActive"] p { color: var(--bg) !important; font-weight: 600; }
/* ---- toggle ---- */
[data-testid="stToggle"] label p, .stCheckbox label p { color: var(--fg); }
/* ---- intestazioni di pagina ---- */
.pg-h { display:flex; align-items:center; gap:10px; margin: 4px 0 12px; }
.pg-h .ic { color: var(--acc); }
.pg-h span { font-size: 1.55rem; font-weight: 700; letter-spacing: -0.01em; }
.sec { display:flex; align-items:center; gap:8px; font-size:1.05rem; font-weight:600; margin:14px 0 6px; }
.msg { display:flex; gap:10px; align-items:flex-start; background: var(--note); border-radius: 16px; padding: 12px 14px; margin: 6px 0; color: var(--fg); font-size: .95rem; }
.msg .ic { flex: 0 0 auto; margin-top: 1px; color: var(--acc); }
.msg.warn .ic { color: var(--warn); } .msg.err .ic { color: var(--err); } .msg.ok .ic { color: var(--donefg); }
/* ---- seduta ---- */
.ss-h { display:flex; justify-content:space-between; align-items:center; gap:12px; margin: 2px 0 4px; }
.ss-h .k { font-size: 14px; color: var(--mut); }
.ss-h .t { font-size: 24px; font-weight: 700; line-height: 1.15; }
.ss-h .b { margin-top: 4px; }
.ring { position: relative; width: 52px; height: 52px; flex: 0 0 52px; }
.ring svg { transform: rotate(-90deg); }
.ring div { position:absolute; inset:0; display:flex; align-items:center; justify-content:center; font-size:13px; font-weight:600; }
.st-key-blockpills [data-testid="stButtonGroup"] > div, .st-key-blockpills [role="radiogroup"], .st-key-blockpills div[data-baseweb="button-group"] {
  flex-wrap: nowrap !important; overflow-x: auto; scrollbar-width: none; }
.st-key-blockpills [role="radiogroup"] { flex-wrap: nowrap !important; overflow-x: auto !important; scrollbar-width: none; padding-bottom: 2px; }
.st-key-blockpills [role="radiogroup"]::-webkit-scrollbar { display: none; }
.st-key-blockpills [data-testid="stElementContainer"], .st-key-blockpills [data-testid="stButtonGroup"] { width: 100% !important; max-width: 100%; }
.st-key-blockpills button { flex: 0 0 auto !important; max-width: none !important; }
.st-key-blockpills button * { overflow: visible !important; text-overflow: clip !important; max-width: none !important; }
.st-key-blockpills button { white-space: nowrap; font-size: 13px; padding: 4px 12px !important; min-height: 32px !important; }
.st-key-blockpills button p { font-size: 13px !important; }
.ex-h { display:flex; gap:12px; align-items:center; }
.tile { width:44px; height:44px; flex:0 0 44px; border-radius:14px; background: var(--chip); color: var(--acc); display:flex; align-items:center; justify-content:center; font-weight:700; font-size: 15px; }
.tile.off { color: var(--mut); }
.ex-h .nm { display:flex; flex-direction:column; gap:2px; min-width:0; }
.ex-name { font-size: 19px; font-weight: 700; line-height: 1.2; }
.ex-presc { font-size: 13px; color: var(--mut); }
.ex-presc b { color: var(--fg); font-weight: 600; }
.ex-cue { font-size: 14px; color: var(--fg); background: var(--note); border-radius: 12px; padding: 10px 12px; margin: 2px 0; }
.ex-cue.alt { color: var(--donefg); }
.ex-det { color: var(--mut); font-size: .9rem; line-height: 1.45; }
.ex-det b { color: var(--fg); font-weight: 600; }
.ex-note { color: var(--fg); font-size: .9rem; background: var(--note); border-radius: 12px; padding: 8px 12px; margin: 6px 0; }
.sup { display:flex; align-items:center; gap:10px; color: var(--mut); font-size: 13px; padding: 0 8px; margin: -4px 0; }
.sup i { display:block; width:2px; height:26px; background:#3B4A7E; margin-left:21px; }
.pcard { background: var(--card); border-radius: 22px; padding: 14px 18px; display:flex; gap:12px; align-items:center; border: 1px solid transparent; }
.pcard .nm { font-size:17px; font-weight:600; } .pcard .ex-presc { margin-top: 2px; }
[class*="st-key-pc_"] { position: relative; }
[class*="st-key-pc_"] .stButton { position: absolute; inset: 0; z-index: 2; }
[class*="st-key-pc_"] .stButton button { width: 100%; height: 100%; opacity: 0; }
[class*="st-key-vid_"] button { width: 44px !important; min-height: 44px !important; height: 44px; padding: 0 !important; border-radius: 14px !important; color: var(--acc) !important; }
[class*="st-key-vid_"] button.on, [class*="st-key-vidon_"] button { background: var(--acc) !important; color: var(--bg) !important; }
[class*="st-key-vidon_"] button { width: 44px !important; min-height: 44px !important; height: 44px; padding: 0 !important; border-radius: 14px !important; }
[class*="st-key-exhead"] [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; align-items: center; gap: 8px !important; }
[class*="st-key-exhead"] [data-testid="stColumn"]:first-child { flex: 1 1 auto !important; min-width: 0 !important; width: auto !important; }
[class*="st-key-exhead"] [data-testid="stColumn"]:last-child { flex: 0 0 44px !important; min-width: 44px !important; width: 44px !important; }
.blk-title { font-size:.78rem; letter-spacing:.06em; color: var(--mut); font-weight:600; text-transform:uppercase; margin: 2px 0; }
.pill { display:inline-block; padding:3px 10px; border-radius:999px; background: var(--chip); font-size:.82rem; margin:0 4px 4px 0; color: var(--fg); }
.pill.ok { background: var(--done); color: var(--donefg); }
.pill.warn { background:#3a3220; color: var(--warn); }
.pill.err { background:#3a2030; color: var(--err); }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 22px; padding: 16px 18px; margin: 6px 0 12px; }
.card .big { font-size: 1.4rem; font-weight: 700; line-height: 1.2; margin: 2px 0; }
.card .mut { color: var(--mut); font-size: .92rem; }
.card b { font-weight: 600; }
.navpos { text-align:center; color: var(--mut); font-size:.9rem; padding-top:16px; }
/* ---- barra di navigazione in basso ---- */
.st-key-navbar { position: fixed !important; left: 0; right: 0; bottom: 0; z-index: 990; background: rgba(15,23,48,.97);
  border-top: 1px solid var(--line); padding: 8px 8px calc(10px + env(safe-area-inset-bottom)) !important; backdrop-filter: blur(6px); }
.st-key-navbar > div, .st-key-navbar [data-testid="stHorizontalBlock"] { max-width: 640px; margin: 0 auto; }
.st-key-navbar [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 0 !important; }
.st-key-navbar [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; flex: 1 1 0 !important; }
.st-key-navbar [data-testid="stPageLink"] a { flex-direction: column; justify-content: center; align-items: center; gap: 4px !important;
  min-height: 52px; padding: 2px 0; background: transparent !important; border: 0; border-radius: 14px; color: var(--mut); }
.st-key-navbar [data-testid="stPageLink"] a::before { content: ""; display: block; width: 26px; height: 26px; background: currentColor;
  -webkit-mask: var(--ico) center / contain no-repeat; mask: var(--ico) center / contain no-repeat; }
.st-key-navbar [data-testid="stPageLink"] p { font-size: 11px !important; line-height: 1.2; margin: 0; white-space: nowrap; color: inherit !important; }
.st-key-navbar [data-testid="stPageLink"] a:hover { background: transparent !important; color: var(--fg); }
[class*="st-key-nav_"][class*="_on"] [data-testid="stPageLink"] a { color: var(--acc) !important; }
[class*="st-key-nav_"][class*="_on"] [data-testid="stPageLink"] p { font-weight: 600; }
%NAVICONS%
/* navigazione tra blocchi */
.st-key-blocknav [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: 8px !important; }
.st-key-blocknav [data-testid="stColumn"] { min-width: 0 !important; width: auto !important; }
.st-key-blocknav [data-testid="stColumn"]:nth-child(1), .st-key-blocknav [data-testid="stColumn"]:nth-child(3) { flex: 1 1 0 !important; }
.st-key-blocknav [data-testid="stColumn"]:nth-child(2) { flex: 0 0 48px !important; }
.st-key-blocknav button { min-height: 54px !important; }
/* niente salto orizzontale */
html, body, [data-testid="stAppViewContainer"] { overflow-x: hidden; }
[data-testid="stIFrame"], iframe { border: 0 !important; }
[data-testid="stVideo"] iframe, .stVideo { border-radius: 16px; }
</style>
"""


def _css() -> str:
    rules = "\n".join(f'[class*="st-key-nav_{p}"] {{ --ico: {_mask(i)}; }}' for p, i in NAV_ICONS.items())
    return CSS.replace("%NAVICONS%", rules)


def inject_css() -> None:
    st.html(_css())


def html_block(markup: str) -> None:
    """HTML con SVG inline (st.html li toglie): passa da st.markdown, su una riga sola."""
    st.markdown(markup.replace("\n", " "), unsafe_allow_html=True)


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def pill(text: str, kind: str = "") -> str:
    return f'<span class="pill {kind}">{esc(text)}</span>'


def card(inner_html: str) -> None:
    html_block(f'<div class="card">{inner_html}</div>')


def page_title(text: str, ico: str) -> None:
    html_block(f'<div class="pg-h">{icon(ico, 28)}<span>{esc(text)}</span></div>')


def msg(text_html: str, kind: str = "info", ico: str | None = None) -> None:
    """Messaggio in stile Studio con icona Linea (al posto di st.info/st.warning con emoji)."""
    ico = ico or {"warn": "alert", "err": "alert", "ok": "check"}.get(kind, "info")
    html_block(f'<div class="msg {kind}">{icon(ico, 20)}<div>{text_html}</div></div>')


def ring(done: int, total: int, size: int = 52, stroke: int = 5) -> str:
    r = (size - stroke * 2) / 2 + 1
    c = 2 * 3.14159 * r
    off = c * (1 - (done / total if total else 0))
    return (f'<div class="ring"><svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" aria-hidden="true">'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{r:.1f}" fill="none" stroke="{CHIP}" stroke-width="{stroke}"/>'
            f'<circle cx="{size / 2}" cy="{size / 2}" r="{r:.1f}" fill="none" stroke="{ACCENT}" stroke-width="{stroke}" '
            f'stroke-linecap="round" stroke-dasharray="{c:.1f}" stroke-dashoffset="{off:.1f}"/></svg>'
            f'<div>{done}/{total}</div></div>')


def _short_rest(rest: str | None) -> str | None:
    """"60-90'' → A2" → "60-90″" (il "poi …" lo dice già il timer)."""
    if not rest or rest.strip() in ("-", ""):
        return None
    r = rest.split("→")[0].strip()
    return r.replace("''", "″").replace("\"", "″").replace("'", "′") or None


def presc_compact(presc: dict, ex_def: dict | None = None) -> str:
    """Prescrizione su una riga: "4 × 3-6 · RIR 2 · rec 60-90″ · tempo 2-1-1-0" (HTML)."""
    ex_def = ex_def or {}
    parts = []
    if presc.get("setsTarget") and presc.get("repsMin") is not None:
        rmin, rmax = presc.get("repsMin"), presc.get("repsMax")
        reps = f"{rmin}" if rmin == rmax or rmax is None else f"{rmin}-{rmax}"
        unit = (presc.get("repsUnit") or "rip").strip()
        parts.append(f"<b>{presc['setsTarget']} × {esc(reps)}</b>" + (f" {esc(unit)}" if unit != "rip" else ""))
    elif ex_def.get("setsText"):
        parts.append(f"<b>{esc(ex_def['setsText'])}</b>")
    if presc.get("rir") and presc["rir"] != "-":
        parts.append(f"RIR <b>{esc(presc['rir'])}</b>")
    rest = _short_rest(presc.get("rest"))
    if rest:
        parts.append(f"rec {esc(rest)}")
    if presc.get("tempo") and presc["tempo"] != "-":
        parts.append(f"tempo {esc(presc['tempo'])}")
    return " · ".join(parts)


def exercise_title(ex_def: dict, presc: dict, *, sub: str | None = None, muted: bool = False) -> str:
    code = ex_def.get("code") or ""
    tile = f'<div class="tile{" off" if muted else ""}">{esc(code)}</div>' if code else ""
    return (f'<div class="ex-h">{tile}<div class="nm"><div class="ex-name">{esc(ex_def["name"])}</div>'
            f'<div class="ex-presc">{sub if sub is not None else presc_compact(presc, ex_def)}</div></div></div>')


def exercise_cue(ex_def: dict, *, used_alt: bool = False) -> None:
    if used_alt:
        html_block(f'<div class="ex-cue alt">Alternativa in uso: {esc(ex_def.get("alternative"))}</div>')
    elif ex_def.get("cue"):
        html_block(f'<div class="ex-cue">{esc(ex_def["cue"])}</div>')


def exercise_header(ex_def: dict, presc: dict, *, used_alt: bool = False, compact: bool = False) -> None:
    """Intestazione dell'esercizio. compact=True: tessera, nome, prescrizione e cue;
    altrimenti (pagina Piano) anche le note complete."""
    html_block(exercise_title(ex_def, presc))
    exercise_cue(ex_def, used_alt=used_alt)
    if not compact and ex_def.get("notes"):
        html_block(f'<div class="ex-det">{esc(ex_def["notes"])}</div>')


def exercise_details(ex_def: dict, presc: dict | None = None) -> None:
    """Testo completo (note, carico, alternativa) per il riquadro "Dettagli"."""
    presc = presc or {}
    lines = []
    if ex_def.get("notes"):
        lines.append(esc(ex_def["notes"]))
    load = []
    if ex_def.get("loadFrom") == "giubbotto":
        load.append("peso = giubbotto della seduta")
    elif ex_def.get("startingLoadKg") is not None and not ex_def.get("bodyweight"):
        load.append(f"carico iniziale {L.fmt_kg(ex_def['startingLoadKg'])} kg")
    if presc.get("phase"):
        load.append(f"fase {esc(presc['phase'])}")
    if ex_def.get("setsFromProgression"):
        load.append("serie dalla tabella trazioni")
    if ex_def.get("startingLoadKg") is not None or ex_def.get("bodyweight") or ex_def.get("loadFrom"):
        load.append(f"passo ±{L.fmt_kg(L.kg_step(ex_def))} kg")
    if load:
        lines.append("<b>Carico:</b> " + " · ".join(load))
    if presc.get("rest") and presc["rest"] != "-":
        lines.append(f"<b>Recupero:</b> {esc(presc['rest'])}")
    if ex_def.get("alternative") and ex_def["alternative"] != "-":
        lines.append(f"<b>Alternativa:</b> {esc(ex_def['alternative'])}")
    if lines:
        html_block('<div class="ex-det">' + "<br>".join(lines) + "</div>")


def show_video(v: dict) -> None:
    """Video già risolto: parte da solo (autoplay senza audio: Chrome Android blocca l'autoplay con
    l'audio; si attiva dal player), con il link "Apri su YouTube"."""
    if v["embed"]:
        st.video(v["embed"], autoplay=True, muted=True)
        meta = " · ".join(x for x in [v.get("title"), v.get("channel"), (v.get("lang") or "").upper()] if x)
        st.caption(f"{meta}  \n[Apri su YouTube]({v['url']}) · [Cerca altri video]({v['search']})")
    else:
        st.caption(f"Nessun video scelto per questo esercizio. [Cerca su YouTube]({v['search']})")


def video_toggle(ex_def: dict, videos: dict, key: str, alternative: bool = False) -> None:
    """Video incorporato solo su richiesta (un iframe alla volta, pagina leggera)."""
    v = P.resolve_video(ex_def, videos, alternative=alternative)
    label = ":material/smart_display: Tutorial" + (" (alternativa)" if alternative else "")
    if st.toggle(label, key=key):
        show_video(v)


def sync_badge(draft: dict, synced_rev: int, error: str | None) -> str:
    pend = L.pending_count(draft, synced_rev)
    unsynced = int(draft.get("rev", 0)) > synced_rev
    if not unsynced:
        return pill("sincronizzato", "ok")
    txt = f"{pend} serie in attesa" if pend else "modifiche in attesa"
    if error:
        return pill(txt + " · offline", "err")
    return pill(txt, "warn")


def fmt_presc_short(presc: dict) -> str:
    rmin, rmax = presc.get("repsMin"), presc.get("repsMax")
    reps = f"{rmin}" if rmin == rmax else f"{rmin}-{rmax}"
    return f"{presc.get('setsTarget')}×{reps}"


SHORT = {"Allenamento": "Allena", "Progressi": "Progressi", "Storico": "Storico", "Piano": "Piano",
         "Impostazioni": "Impost."}


def nav_bar(pages, current) -> None:
    """Barra di navigazione fissa in basso: icona "Linea" (maschera CSS) ed etichetta, voce attiva in azzurro."""
    with st.container(key="navbar"):
        cols = st.columns(len(pages), gap="small", wrap=False)
        for c, p in zip(cols, pages):
            with c:
                active = getattr(current, "title", None) == p.title
                slug = NAV_KEYS.get(p.title, p.url_path or "home")
                with st.container(key=f"nav_{slug}" + ("_on" if active else "")):
                    st.page_link(p, label=SHORT.get(p.title, p.title), width="stretch", help=p.title)

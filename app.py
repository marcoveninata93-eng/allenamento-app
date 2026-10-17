"""Allenamento — app Streamlit mobile-first per un piano di allenamento in sedute A/B/C."""
import streamlit as st

st.set_page_config(page_title="Allenamento", page_icon="🏋️", layout="centered", initial_sidebar_state="collapsed")

from lib import services as S  # noqa: E402
from lib import ui as U  # noqa: E402

U.inject_css()

pages = [
    st.Page("views/allenamento.py", title="Allenamento", icon="🏋️", url_path="allenamento", default=True),
    st.Page("views/progressi.py", title="Progressi", icon="📈", url_path="progressi"),
    st.Page("views/storico.py", title="Storico", icon="📚", url_path="storico"),
    st.Page("views/piano.py", title="Piano", icon="📋", url_path="piano"),
    st.Page("views/impostazioni.py", title="Impostazioni", icon="⚙️", url_path="impostazioni"),
]
# la navigazione va dichiarata prima del login: così, dopo l'accesso, si resta sulla pagina richiesta
nav = st.navigation(pages, position="hidden")
S.require_login()
S.bootstrap()
U.nav_bar(pages, nav)
nav.run()

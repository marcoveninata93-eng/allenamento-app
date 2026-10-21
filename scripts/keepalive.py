"""Apre l'app su Streamlit Community Cloud e la risveglia se è in pausa.

Eseguito ogni 3 ore dal workflow .github/workflows/keepalive.yml: una visita con un
browser vero (la sola richiesta HTTP non basta) tiene l'app sveglia.
"""
import os
import re
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL", "https://allenamento-marco.streamlit.app/")
WAKE = re.compile(r"get this app back up", re.I)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        page = browser.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
        page.wait_for_timeout(15_000)
        button = page.get_by_role("button", name=WAKE)
        if button.count():
            print("App in pausa: la risveglio")
            button.first.click()
            page.wait_for_timeout(90_000)
            asleep = page.get_by_role("button", name=WAKE).count() > 0
        else:
            asleep = False
            print("App già sveglia")
        # Resta qualche secondo collegata, come una visita vera.
        page.wait_for_timeout(20_000)
        browser.close()
    if asleep:
        print("L'app risulta ancora in pausa", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

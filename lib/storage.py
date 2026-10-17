"""Persistenza: interfaccia astratta + backend locale (file) e GitHub (Contents API su un repo dati privato).

Il livello basso (`Storage`) legge/scrive file JSON con SHA; il livello alto (`DataStore`)
conosce la struttura dei dati (logs/, drafts/, plans/, settings.json, bodyweight.json).
Nessuna dipendenza da Streamlit: testabile con pytest.
"""
from __future__ import annotations

import base64
import json
import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Callable

import requests

from . import logic as L
from . import plan as P

DRAFT_PATH = "drafts/current.json"
SETTINGS_PATH = "settings.json"
BODYWEIGHT_PATH = "bodyweight.json"

DEFAULT_SETTINGS = {
    "cycleStartDate": "2026-10-19",
    "cycleWeeks": 8,
    "activePlanVersion": 1,
    "timezone": "Europe/Rome",
    "sound": True,
    "vibrate": True,
    "wakeLock": True,
}


class StorageError(Exception):
    """Errore con messaggio leggibile dall'utente."""


class ConflictError(StorageError):
    pass


# ============================================================ interfaccia
class Storage(ABC):
    kind = "abstract"

    @abstractmethod
    def read(self, path: str) -> tuple[Any, str | None]:
        """Ritorna (dati, sha). (None, None) se il file non esiste."""

    @abstractmethod
    def write(self, path: str, data: Any, sha: str | None = None, message: str = "") -> str:
        """Scrive il file. Con sha=None su file esistente → ConflictError. Ritorna il nuovo sha."""

    @abstractmethod
    def delete(self, path: str, sha: str | None = None, message: str = "") -> None: ...

    @abstractmethod
    def list(self, directory: str) -> list[dict]:
        """[{name, path, sha}] dei file .json nella cartella (vuoto se non esiste)."""

    def status(self) -> dict:
        return {"kind": self.kind}

    def ensure_ready(self) -> None:
        pass


def _dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=1, sort_keys=False)


# ============================================================ locale
class LocalStorage(Storage):
    kind = "local"

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, path: str) -> Path:
        p = (self.root / path).resolve()
        if self.root.resolve() not in p.parents and p != self.root.resolve():
            raise StorageError(f"Percorso non valido: {path}")
        return p

    @staticmethod
    def _sha(text: str) -> str:
        import hashlib
        return hashlib.sha1(text.encode("utf-8")).hexdigest()

    def read(self, path):
        p = self._p(path)
        if not p.exists():
            return None, None
        text = p.read_text(encoding="utf-8")
        try:
            return json.loads(text), self._sha(text)
        except json.JSONDecodeError as exc:
            raise StorageError(f"File {path} corrotto: {exc}") from exc

    def write(self, path, data, sha=None, message=""):
        p = self._p(path)
        if p.exists():
            cur = self._sha(p.read_text(encoding="utf-8"))
            if sha != cur:
                raise ConflictError(f"Il file {path} è stato modificato nel frattempo.")
        elif sha is not None:
            raise ConflictError(f"Il file {path} è stato eliminato nel frattempo.")
        p.parent.mkdir(parents=True, exist_ok=True)
        text = _dumps(data)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, p)  # scrittura atomica
        return self._sha(text)

    def delete(self, path, sha=None, message=""):
        p = self._p(path)
        if p.exists():
            p.unlink()

    def list(self, directory):
        d = self._p(directory)
        if not d.is_dir():
            return []
        out = []
        for f in sorted(d.glob("*.json")):
            text = f.read_text(encoding="utf-8")
            out.append({"name": f.name, "path": f"{directory}/{f.name}", "sha": self._sha(text)})
        return out

    def status(self):
        return {"kind": "local", "root": str(self.root), "ok": True}


# ============================================================ GitHub
class GitHubStorage(Storage):
    """GitHub Contents API su un repo DATI privato e separato dal codice (default branch `main`):
    i salvataggi non toccano il repo dell'app e non la fanno ripartire."""

    kind = "github"
    API = "https://api.github.com"

    def __init__(self, token: str, repo: str, branch: str = "main", session: Any = None,
                 retries: int = 1, backoff: float = 0.5, timeout: float = 8.0,
                 sleep: Callable[[float], None] = time.sleep):
        if not token or not repo or "/" not in repo:
            raise StorageError("Configurazione GitHub incompleta: servono GITHUB_TOKEN e GITHUB_REPO (formato owner/repo).")
        self.token, self.repo, self.branch = token, repo, branch
        self.s = session or requests.Session()
        self.retries, self.backoff, self.timeout, self.sleep = retries, backoff, timeout, sleep
        self._cache: dict[str, tuple[str, Any]] = {}   # path → (sha, dati): evita di riscaricare file invariati
        self._ready = False
        self._empty = False
        self.private = None
        self.last_rate: dict = {}

    # ---------------------------------------------------------- http
    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "allenamento-app"}

    def _req(self, method: str, url: str, ok=(200, 201), allow=(), **kw):
        last_exc = None
        for attempt in range(self.retries + 1):
            try:
                r = self.s.request(method, url, headers=self._headers(), timeout=self.timeout, **kw)
            except requests.RequestException as exc:  # rete assente / timeout
                last_exc = exc
                if attempt < self.retries:
                    self.sleep(self.backoff * (2 ** attempt))
                    continue
                raise StorageError(f"Rete non disponibile o GitHub non raggiungibile ({type(exc).__name__}). "
                                   "I dati restano sul telefono e verranno inviati appena torna la connessione.") from exc
            hdr = getattr(r, "headers", {}) or {}
            if "X-RateLimit-Remaining" in hdr:
                self.last_rate = {"remaining": hdr.get("X-RateLimit-Remaining"), "limit": hdr.get("X-RateLimit-Limit")}
            if r.status_code in ok or r.status_code in allow:
                return r
            if r.status_code in (500, 502, 503, 504) and attempt < self.retries:
                self.sleep(self.backoff * (2 ** attempt))
                continue
            if r.status_code == 403 and str(hdr.get("X-RateLimit-Remaining", "1")) == "0" and attempt < self.retries:
                raise StorageError("Limite di richieste GitHub raggiunto: riprova tra qualche minuto.")
            self._raise_for(r)
        raise StorageError(f"Errore GitHub: {last_exc}")

    def _raise_for(self, r):
        try:
            msg = r.json().get("message", "")
        except Exception:
            msg = getattr(r, "text", "")[:200]
        code = r.status_code
        if code == 401:
            raise StorageError("Token GitHub non valido o scaduto (401). Rigeneralo e aggiorna i Secrets.")
        if code == 403:
            raise StorageError(f"Accesso negato da GitHub (403): il token deve avere 'Contents: Read and write' su {self.repo}. {msg}")
        if code == 404:
            raise StorageError(f"Non trovato su GitHub (404): controlla GITHUB_REPO={self.repo} e i permessi del token. {msg}")
        if code in (409, 422) and ("sha" in msg.lower() or code == 409):
            raise ConflictError(f"Conflitto di versione su GitHub ({code}): {msg}")
        raise StorageError(f"Errore GitHub {code}: {msg}")

    def _contents_url(self, path: str) -> str:
        return f"{self.API}/repos/{self.repo}/contents/{path}"

    # ---------------------------------------------------------- branch
    def ensure_ready(self) -> None:
        """Controlla il repo dati: deve essere PRIVATO (altrimenti rifiuta di leggere e scrivere).
        Se il branch manca lo crea dal branch predefinito; un repo vuoto (senza commit) va bene:
        la prima PUT della Contents API crea il primo commit."""
        if self._ready:
            return
        repo = self._req("GET", f"{self.API}/repos/{self.repo}").json()
        self.private = repo.get("private")
        if repo.get("private") is not True:
            raise StorageError(
                f"Il repo dati {self.repo} è PUBBLICO: per proteggere i tuoi allenamenti l'app non ci scrive. "
                "Controlla GITHUB_REPO nei Secrets: deve puntare al repo dati privato (es. allenamento-dati), "
                "non al repo del codice.")
        base = repo.get("default_branch") or "main"
        r = self._req("GET", f"{self.API}/repos/{self.repo}/branches/{self.branch}", allow=(404,))
        if r.status_code == 404:
            ref = self._req("GET", f"{self.API}/repos/{self.repo}/git/ref/heads/{base}", allow=(404, 409))
            if ref.status_code != 200:  # repo vuoto: nessun commit
                if self.branch != base:
                    raise StorageError(f"Il repo {self.repo} è vuoto: usa DATA_BRANCH = \"{base}\" "
                                       "(oppure crea il repo con un README).")
                self._empty = True
            else:
                sha = ref.json()["object"]["sha"]
                self._req("POST", f"{self.API}/repos/{self.repo}/git/refs", ok=(201,), allow=(422,),
                          json={"ref": f"refs/heads/{self.branch}", "sha": sha})
        self._ready = True

    # ---------------------------------------------------------- file
    def read(self, path):
        self.ensure_ready()
        if self._empty:
            return None, None
        r = self._req("GET", self._contents_url(path), params={"ref": self.branch}, allow=(404,))
        if r.status_code == 404:
            self._cache.pop(path, None)
            return None, None
        j = r.json()
        if isinstance(j, list):
            raise StorageError(f"{path} è una cartella, non un file")
        sha = j["sha"]
        cached = self._cache.get(path)
        if cached and cached[0] == sha:
            return cached[1], sha
        content = j.get("content")
        if not content and j.get("download_url"):  # file > 1 MB
            raw = self._req("GET", j["download_url"]).text
        else:
            raw = base64.b64decode(content or "").decode("utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise StorageError(f"File {path} su GitHub non è JSON valido: {exc}") from exc
        self._cache[path] = (sha, data)
        return data, sha

    def read_by_sha(self, path: str, sha: str):
        cached = self._cache.get(path)
        if cached and cached[0] == sha:
            return cached[1]
        data, _ = self.read(path)
        return data

    def write(self, path, data, sha=None, message=""):
        self.ensure_ready()
        body = {"message": message or f"Aggiorna {path}",
                "content": base64.b64encode(_dumps(data).encode("utf-8")).decode("ascii")}
        if not self._empty:  # repo vuoto: la PUT crea il primo commit sul branch predefinito
            body["branch"] = self.branch
        if sha:
            body["sha"] = sha
        r = self._req("PUT", self._contents_url(path), ok=(200, 201), json=body)
        new_sha = r.json()["content"]["sha"]
        self._empty = False
        self._cache[path] = (new_sha, json.loads(json.dumps(data)))
        return new_sha

    def delete(self, path, sha=None, message=""):
        self.ensure_ready()
        if sha is None:
            _, sha = self.read(path)
            if sha is None:
                return
        self._req("DELETE", self._contents_url(path), ok=(200,), allow=(404,),
                  json={"message": message or f"Elimina {path}", "sha": sha, "branch": self.branch})
        self._cache.pop(path, None)

    def list(self, directory):
        self.ensure_ready()
        if self._empty:
            return []
        r = self._req("GET", self._contents_url(directory), params={"ref": self.branch}, allow=(404,))
        if r.status_code == 404:
            return []
        j = r.json()
        if not isinstance(j, list):
            return []
        return [{"name": e["name"], "path": e["path"], "sha": e["sha"]}
                for e in j if e.get("type") == "file" and e["name"].endswith(".json")]

    def status(self):
        try:
            self.ensure_ready()
            r = self._req("GET", f"{self.API}/repos/{self.repo}")
            j = r.json()
            return {"kind": "github", "ok": True, "repo": self.repo, "branch": self.branch,
                    "private": j.get("private"), "rate": self.last_rate}
        except StorageError as exc:
            return {"kind": "github", "ok": False, "repo": self.repo, "branch": self.branch, "error": str(exc)}


# ============================================================ livello dati
class DataStore:
    def __init__(self, storage: Storage):
        self.st = storage
        self._shas: dict[str, str | None] = {}

    # ---------------------------------------------------------- generico con SHA
    def _read(self, path):
        data, sha = self.st.read(path)
        self._shas[path] = sha
        return data

    def _write(self, path, data, message="", merge: Callable[[Any, Any], Any] | None = None, attempts: int = 3):
        """Scrittura con gestione del conflitto: se lo SHA è cambiato rilegge, (eventualmente)
        unisce e riprova."""
        for i in range(attempts):
            sha = self._shas.get(path)
            if path not in self._shas:
                _, sha = self.st.read(path)
            try:
                new_sha = self.st.write(path, data, sha=sha, message=message)
                self._shas[path] = new_sha
                return data
            except ConflictError:
                remote, rsha = self.st.read(path)
                self._shas[path] = rsha
                if merge and remote is not None:
                    data = merge(data, remote)
                if i == attempts - 1:
                    raise
        return data

    def _delete(self, path, message=""):
        sha = self._shas.get(path)
        try:
            self.st.delete(path, sha=sha, message=message)
        except ConflictError:
            _, sha = self.st.read(path)
            if sha:
                self.st.delete(path, sha=sha, message=message)
        self._shas[path] = None

    # ---------------------------------------------------------- bootstrap
    def bootstrap(self, default_plan: dict | None = None) -> dict:
        """Primo avvio: crea settings.json e plans/plan_v1.json. NON importa lo storico del ciclo 1."""
        self.st.ensure_ready()
        settings = self._read(SETTINGS_PATH)
        created = False
        if settings is None:
            settings = dict(DEFAULT_SETTINGS)
            created = True
        else:
            for k, v in DEFAULT_SETTINGS.items():
                settings.setdefault(k, v)
        if not self.list_plan_versions():
            plan = P.strip_plan(default_plan or P.load_default_plan())
            plan["version"] = 1
            self.save_plan(plan, message="Piano v1 iniziale")
            settings["activePlanVersion"] = 1
            created = True
        if created:
            self.save_settings(settings)
        return settings

    # ---------------------------------------------------------- impostazioni
    def get_settings(self) -> dict:
        s = self._read(SETTINGS_PATH) or {}
        return {**DEFAULT_SETTINGS, **s}

    def save_settings(self, settings: dict) -> dict:
        return self._write(SETTINGS_PATH, settings, "Impostazioni")

    # ---------------------------------------------------------- piani
    def list_plan_versions(self) -> list[int]:
        out = []
        for f in self.st.list("plans"):
            n = f["name"]
            if n.startswith("plan_v") and n.endswith(".json"):
                try:
                    out.append(int(n[6:-5]))
                except ValueError:
                    pass
        return sorted(out)

    def get_plan(self, version: int) -> dict | None:
        return self._read(f"plans/plan_v{int(version)}.json")

    def save_plan(self, plan: dict, message: str = "") -> int:
        errs = P.validate_plan(plan)
        if errs:
            raise StorageError("Piano non valido: " + "; ".join(errs[:5]))
        v = int(plan["version"])
        path = f"plans/plan_v{v}.json"
        if path not in self._shas:
            self._read(path)
        self._write(path, plan, message or f"Piano v{v}")
        return v

    # ---------------------------------------------------------- bozza
    def get_draft(self) -> dict | None:
        return self._read(DRAFT_PATH)

    def save_draft(self, draft: dict) -> dict:
        """Scrive la bozza rileggendo SEMPRE lo SHA corrente: se sul server c'è la stessa bozza
        modificata da un'altra scheda/dispositivo, prima si uniscono le serie (vince il tap più
        recente), poi si scrive. Ritorna la bozza effettivamente salvata (eventualmente unita)."""
        remote, sha = self.st.read(DRAFT_PATH)
        self._shas[DRAFT_PATH] = sha
        if remote is not None and remote.get("id") == draft.get("id") and remote != draft:
            draft = L.merge_drafts(draft, remote)
        return self._write(DRAFT_PATH, draft, f"Bozza seduta {draft.get('sessionId')} rev {draft.get('rev')}",
                           merge=L.merge_drafts)

    def clear_draft(self) -> None:
        if DRAFT_PATH not in self._shas:
            self._read(DRAFT_PATH)
        if self._shas.get(DRAFT_PATH):
            self._delete(DRAFT_PATH, "Bozza chiusa")

    # ---------------------------------------------------------- log
    def list_log_files(self) -> list[dict]:
        return self.st.list("logs")

    def load_logs(self) -> list[dict]:
        logs = []
        for f in self.list_log_files():
            if isinstance(self.st, GitHubStorage):
                data = self.st.read_by_sha(f["path"], f["sha"])
            else:
                data, _ = self.st.read(f["path"])
            if isinstance(data, dict):
                data.setdefault("id", f["name"][:-5])
                logs.append(data)
        return L.sort_logs(logs)

    def find_log_by_draft(self, draft_id: str | None) -> dict | None:
        if not draft_id:
            return None
        for lg in self.load_logs():
            if lg.get("draftId") == draft_id:
                return lg
        return None

    def save_log(self, log: dict, overwrite: bool = False) -> str:
        """Salva una seduta. Idempotente sulla bozza: se esiste già un log con lo stesso draftId
        (es. un tentativo precedente riuscito ma con risposta persa) non ne crea un secondo."""
        errs = L.validate_log(log)
        if errs:
            raise StorageError("Seduta non valida: " + "; ".join(errs))
        path = L.log_path(log)
        existing, sha = self.st.read(path)
        if not overwrite and log.get("draftId"):
            if existing is not None and existing.get("draftId") == log["draftId"]:
                return path
            same = self.find_log_by_draft(log["draftId"])
            if same is not None:
                return L.log_path(same)
        if existing is not None and not overwrite:
            raise StorageError(f"Esiste già una seduta con id {log['id']}.")
        self._shas[path] = sha
        self._write(path, log, f"Seduta {log['sessionId']} del {log['date']}")
        return path

    def delete_log(self, log_id: str) -> None:
        path = f"logs/{log_id}.json"
        _, sha = self.st.read(path)
        self._shas[path] = sha
        if sha:
            self._delete(path, f"Elimina seduta {log_id}")

    # ---------------------------------------------------------- peso corporeo
    def get_bodyweight(self) -> list[dict]:
        d = self._read(BODYWEIGHT_PATH)
        return (d or {}).get("entries", [])

    def save_bodyweight(self, entries: list[dict]) -> None:
        def merge(local, remote):
            by = {e["date"]: e for e in remote.get("entries", [])}
            by.update({e["date"]: e for e in local.get("entries", [])})
            return {"entries": sorted(by.values(), key=lambda e: e["date"])}
        self._write(BODYWEIGHT_PATH, {"entries": entries}, "Peso corporeo", merge=merge)

    # ---------------------------------------------------------- backup
    def export_bundle(self) -> dict:
        plans = [p for v in self.list_plan_versions() if (p := self.get_plan(v))]
        return {"format": "allenamento-backup", "schema": L.SCHEMA, "exportedAt": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "settings": self.get_settings(), "bodyweight": self.get_bodyweight(), "plans": plans,
                "logs": self.load_logs(), "draft": self.get_draft()}

    def import_bundle(self, bundle: dict, overwrite: bool = False, include_settings: bool = False) -> dict:
        if not isinstance(bundle, dict) or bundle.get("format") != "allenamento-backup":
            raise StorageError("Il file non è un backup di questa app (manca format=allenamento-backup).")
        report = {"logs_added": 0, "logs_skipped": 0, "logs_overwritten": 0, "plans_added": 0, "bodyweight": 0, "errors": []}
        existing = {f["name"][:-5] for f in self.list_log_files()}
        for log in bundle.get("logs", []):
            errs = L.validate_log(log)
            if errs:
                report["errors"].append(f"{log.get('id')}: {'; '.join(errs)}")
                continue
            if log["id"] in existing and not overwrite:
                report["logs_skipped"] += 1
                continue
            self.save_log(log, overwrite=True)
            report["logs_overwritten" if log["id"] in existing else "logs_added"] += 1
        versions = set(self.list_plan_versions())
        for plan in bundle.get("plans", []):
            if int(plan.get("version", 0)) not in versions and not P.validate_plan(plan):
                self.save_plan(plan, "Piano importato da backup")
                report["plans_added"] += 1
        bw = bundle.get("bodyweight") or []
        if bw:
            cur = {e["date"]: e for e in self.get_bodyweight()}
            for e in bw:
                if overwrite or e["date"] not in cur:
                    cur[e["date"]] = e
                    report["bodyweight"] += 1
            self.save_bodyweight(sorted(cur.values(), key=lambda e: e["date"]))
        if include_settings and bundle.get("settings"):
            self.save_settings({**self.get_settings(), **bundle["settings"]})
        return report

    def import_logs(self, logs: list[dict], overwrite: bool = False) -> dict:
        return self.import_bundle({"format": "allenamento-backup", "logs": logs}, overwrite=overwrite)


# ============================================================ factory
def make_storage(secrets: dict | None, local_dir: str | Path) -> tuple[Storage, str | None]:
    """Sceglie il backend. Ritorna (storage, errore_configurazione)."""
    secrets = secrets or {}
    token = secrets.get("GITHUB_TOKEN")
    repo = secrets.get("GITHUB_REPO")
    if token and repo:
        return GitHubStorage(token, repo, secrets.get("DATA_BRANCH") or "main"), None
    if token or repo:
        return LocalStorage(local_dir), "Secrets incompleti: servono sia GITHUB_TOKEN sia GITHUB_REPO. Uso la modalità locale."
    return LocalStorage(local_dir), None

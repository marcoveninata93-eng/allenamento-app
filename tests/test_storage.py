import base64
import json
from datetime import date, datetime

import pytest
import requests

from lib import logic as L
from lib import plan as P
from lib.storage import (ConflictError, DataStore, GitHubStorage, LocalStorage, StorageError, make_storage)

T0 = 1_760_000_000_000


# ------------------------------------------------------------------ finto GitHub
class Resp:
    def __init__(self, code, data=None, headers=None):
        self.status_code = code
        self._data = data
        self.headers = headers or {"X-RateLimit-Remaining": "4999", "X-RateLimit-Limit": "5000"}
        self.text = json.dumps(data) if data is not None else ""

    def json(self):
        return self._data


class FakeGitHub:
    """Simula la Contents API (file, sha, branch, conflitti) in memoria."""

    def __init__(self, repo="utente/allenamento-dati", has_data_branch=False, fail_times=0, private=True, empty=False):
        self.repo = repo
        self.private = private
        self.branches = {} if empty else {"main": "c0ffee"}
        if has_data_branch:
            self.branches["data"] = "c0ffee"
        self.files = {}  # (branch, path) -> (sha, text)
        self.calls = []
        self.fail_times = fail_times
        self.n = 0

    def _sha(self):
        self.n += 1
        return f"sha{self.n}"

    def request(self, method, url, headers=None, timeout=None, params=None, json=None):
        self.calls.append((method, url))
        assert headers["Authorization"] == "Bearer TOKEN"
        if self.fail_times:
            self.fail_times -= 1
            return Resp(502, {"message": "bad gateway"})
        base = f"https://api.github.com/repos/{self.repo}"
        if not url.startswith(base):
            return Resp(404, {"message": "Not Found"})
        rest = url[len(base):]
        if rest == "" and method == "GET":
            return Resp(200, {"default_branch": "main", "private": self.private, "size": 0 if not self.branches else 1})
        if rest.startswith("/branches/"):
            b = rest.split("/")[-1]
            return Resp(200, {"name": b}) if b in self.branches else Resp(404, {"message": "Branch not found"})
        if rest.startswith("/git/ref/heads/"):
            b = rest.split("/")[-1]
            return Resp(200, {"object": {"sha": self.branches[b]}}) if b in self.branches else Resp(404, {})
        if rest == "/git/refs" and method == "POST":
            b = json["ref"].split("/")[-1]
            self.branches[b] = json["sha"]
            return Resp(201, {"ref": json["ref"]})
        if rest.startswith("/contents/"):
            path = rest[len("/contents/"):]
            branch = (params or {}).get("ref") or (json or {}).get("branch")
            if method == "PUT" and branch is None:
                branch = "main"
                if not self.branches:  # repo vuoto: la PUT crea il primo commit
                    self.branches["main"] = "first"
            if not self.branches:
                return Resp(404, {"message": "This repository is empty."})
            if branch not in self.branches:
                return Resp(404, {"message": "No commit found for the ref"})
            key = (branch, path)
            if method == "GET":
                if key in self.files:
                    sha, text = self.files[key]
                    return Resp(200, {"sha": sha, "content": base64.b64encode(text.encode()).decode(), "type": "file"})
                prefix = path.rstrip("/") + "/"
                entries = [{"name": p[len(prefix):], "path": p, "sha": s, "type": "file"}
                           for (b, p), (s, _) in self.files.items() if b == branch and p.startswith(prefix) and "/" not in p[len(prefix):]]
                return Resp(200, entries) if entries else Resp(404, {"message": "Not Found"})
            if method == "PUT":
                cur = self.files.get(key)
                if cur and json.get("sha") != cur[0]:
                    if json.get("sha") is None:
                        return Resp(422, {"message": "Invalid request.\n\n\"sha\" wasn't supplied."})
                    return Resp(409, {"message": f"{path} does not match {json.get('sha')}"})
                if not cur and json.get("sha"):
                    return Resp(404, {"message": "Not Found"})
                sha = self._sha()
                self.files[key] = (sha, base64.b64decode(json["content"]).decode())
                return Resp(201 if not cur else 200, {"content": {"sha": sha, "path": path}})
            if method == "DELETE":
                cur = self.files.get(key)
                if not cur:
                    return Resp(404, {"message": "Not Found"})
                if json.get("sha") != cur[0]:
                    return Resp(409, {"message": "sha mismatch"})
                del self.files[key]
                return Resp(200, {})
        return Resp(404, {"message": "Not Found"})


def gh(fake=None, branch="main", **kw):
    fake = fake or FakeGitHub(**kw)
    return GitHubStorage("TOKEN", fake.repo, branch, session=fake, sleep=lambda s: None), fake


@pytest.fixture(params=["local", "github"])
def storage(request, tmp_path):
    if request.param == "local":
        return LocalStorage(tmp_path / "data")
    return gh()[0]


# ------------------------------------------------------------------ backend generico
def test_read_write_conflict_delete(storage):
    assert storage.read("settings.json") == (None, None)
    sha = storage.write("settings.json", {"a": 1})
    data, sha2 = storage.read("settings.json")
    assert data == {"a": 1} and sha2 == sha
    with pytest.raises(ConflictError):
        storage.write("settings.json", {"a": 2}, sha=None)
    with pytest.raises(ConflictError):
        storage.write("settings.json", {"a": 2}, sha="vecchio")
    sha3 = storage.write("settings.json", {"a": 2}, sha=sha)
    assert storage.read("settings.json")[0] == {"a": 2}
    storage.write("logs/x.json", {"id": "x"})
    storage.write("logs/y.json", {"id": "y"})
    assert sorted(f["name"] for f in storage.list("logs")) == ["x.json", "y.json"]
    assert storage.list("nessuna") == []
    storage.delete("logs/x.json", sha=storage.read("logs/x.json")[1])
    assert [f["name"] for f in storage.list("logs")] == ["y.json"]


def test_datastore_bootstrap_no_history(storage, plan):
    ds = DataStore(storage)
    s = ds.bootstrap(plan)
    assert s["cycleStartDate"] == "2026-10-19" and s["activePlanVersion"] == 1
    assert ds.list_plan_versions() == [1]
    assert ds.load_logs() == []  # lo storico del ciclo 1 NON viene importato
    assert "history" not in ds.get_plan(1)
    ds.bootstrap(plan)  # idempotente
    assert ds.list_plan_versions() == [1]


def test_datastore_draft_cycle(storage, plan):
    ds = DataStore(storage)
    ds.bootstrap(plan)
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    ds.save_draft(d)
    key = "A-superset-a:back-squat"
    L.apply_events(d, [{"id": "1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 100, "reps": 6, "done": True, "t": T0 + 1}], T0)
    ds.save_draft(d)
    assert L.find_ex(ds.get_draft(), key)["sets"][0]["done"]
    log = L.finalize(d, datetime(2026, 10, 19, 18, 0, 0))
    path = ds.save_log(log)
    assert path == L.log_path(log)
    assert ds.save_log(log) == path  # stesso draftId → idempotente, nessun duplicato
    other = dict(log, draftId="altra-bozza")
    with pytest.raises(StorageError):
        ds.save_log(other)  # id uguale ma bozza diversa: niente sovrascritture accidentali
    ds.clear_draft()
    assert ds.get_draft() is None
    logs = ds.load_logs()
    assert len(logs) == 1 and logs[0]["id"] == log["id"]
    ds.delete_log(log["id"])
    assert ds.load_logs() == []


def test_draft_conflict_is_merged(storage, plan):
    """Due dispositivi (o un rerun con SHA vecchio) scrivono la stessa bozza: le serie si uniscono."""
    ds1, ds2 = DataStore(storage), DataStore(storage)
    ds1.bootstrap(plan)
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    ds1.save_draft(d)
    import copy
    d2 = copy.deepcopy(ds2.get_draft())
    key = "A-superset-a:back-squat"
    L.apply_events(d, [{"id": "1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 100, "reps": 6, "done": True, "t": T0 + 1}], T0)
    ds1.save_draft(d)
    L.apply_events(d2, [{"id": "2", "draftId": d["id"], "exKey": key, "type": "set", "n": 2, "kg": 100, "reps": 5, "done": True, "t": T0 + 2}], T0)
    saved = ds2.save_draft(d2)  # SHA vecchio → conflitto → merge per serie
    sets = L.find_ex(saved, key)["sets"]
    assert sets[0]["done"] and sets[1]["done"]
    remote = ds1.get_draft()
    assert [s["done"] for s in L.find_ex(remote, key)["sets"][:2]] == [True, True]


def test_bodyweight_and_plan_versions(storage, plan):
    ds = DataStore(storage)
    ds.bootstrap(plan)
    ds.save_bodyweight(L.upsert_bodyweight([], "2026-10-19", 75.5))
    assert ds.get_bodyweight() == [{"date": "2026-10-19", "kg": 75.5}]
    p2 = P.new_version(P.update_exercise(plan, "A", "A-superset-a", "back-squat", {"sets": 5}), ds.list_plan_versions())
    ds.save_plan(p2)
    assert ds.list_plan_versions() == [1, 2]
    bad = dict(p2, sessions=[])
    with pytest.raises(StorageError):
        ds.save_plan(bad)


def test_export_import_bundle(storage, plan, tmp_path):
    ds = DataStore(storage)
    ds.bootstrap(plan)
    d = L.new_draft(plan, "B", [], week=1, day=date(2026, 10, 21), now_ms=T0)
    key = "B-superset-a:stacco-da-terra"
    L.apply_events(d, [{"id": "1", "draftId": d["id"], "exKey": key, "type": "set", "n": 1, "kg": 110, "reps": 6, "done": True, "t": T0 + 1}], T0)
    ds.save_log(L.finalize(d, datetime(2026, 10, 21, 19, 0, 0)))
    ds.save_bodyweight([{"date": "2026-10-21", "kg": 75.0}])
    bundle = json.loads(json.dumps(ds.export_bundle()))
    other = DataStore(LocalStorage(tmp_path / "altro"))
    other.bootstrap(plan)
    rep = other.import_bundle(bundle)
    assert rep["logs_added"] == 1 and rep["bodyweight"] == 1
    assert other.import_bundle(bundle)["logs_skipped"] == 1
    assert other.import_bundle(bundle, overwrite=True)["logs_overwritten"] == 1
    with pytest.raises(StorageError):
        other.import_bundle({"logs": []})
    rep = other.import_logs(L.csv_to_logs(L.logs_to_csv(bundle["logs"])), overwrite=True)
    assert rep["logs_overwritten"] == 1


# ------------------------------------------------------------------ specifici GitHub
def test_github_default_branch_main_in_data_repo():
    st, fake = gh()
    st.write("settings.json", {"x": 1})
    assert ("main", "settings.json") in fake.files and set(fake.branches) == {"main"}
    assert not any(m == "POST" for m, _ in fake.calls)  # nessun branch creato


def test_github_creates_missing_custom_branch():
    st, fake = gh(branch="data")
    st.write("settings.json", {"x": 1})
    assert fake.branches["data"] == fake.branches["main"]
    assert ("data", "settings.json") in fake.files and ("main", "settings.json") not in fake.files


def test_github_refuses_public_repo():
    """GITHUB_REPO puntato per errore al repo pubblico del codice: niente letture né scritture."""
    st, fake = gh(private=False)
    with pytest.raises(StorageError, match="PUBBLICO"):
        st.write("settings.json", {"x": 1})
    with pytest.raises(StorageError, match="PUBBLICO"):
        st.read("settings.json")
    assert not fake.files
    assert st.status()["ok"] is False


def test_github_empty_repo_first_put_creates_commit(plan):
    st, fake = gh(empty=True)
    ds = DataStore(st)
    assert ds.load_logs() == [] and ds.get_draft() is None
    ds.bootstrap(plan)  # prima PUT senza 'branch' → crea main
    assert "main" in fake.branches and ("main", "settings.json") in fake.files
    assert ds.list_plan_versions() == [1]


def test_github_empty_repo_with_other_branch_is_explained():
    st, fake = gh(empty=True, branch="data")
    with pytest.raises(StorageError, match="vuoto"):
        st.read("x.json")


def test_github_retries_on_5xx():
    st, fake = gh(fail_times=1)
    st.write("a.json", {"ok": True})
    assert st.read("a.json")[0] == {"ok": True}


def test_github_gives_up_quickly():
    """Timeout brevi e un solo nuovo tentativo: la coda sul telefono protegge i dati."""
    st, fake = gh(fail_times=5)
    assert st.timeout <= 8 and st.retries == 1
    with pytest.raises(StorageError):
        st.write("a.json", {"ok": True})


def test_github_network_error_message():
    class Down:
        def request(self, *a, **k):
            raise requests.ConnectionError("no route")
    st = GitHubStorage("TOKEN", "a/b", session=Down(), sleep=lambda s: None, retries=1)
    with pytest.raises(StorageError, match="Rete non disponibile"):
        st.read("x.json")


@pytest.mark.parametrize("code,msg", [(401, "Token GitHub non valido"), (403, "Contents: Read and write"), (404, "GITHUB_REPO")])
def test_github_error_messages(code, msg):
    class Err:
        def request(self, *a, **k):
            return Resp(code, {"message": "boom"})
    st = GitHubStorage("TOKEN", "a/b", session=Err(), sleep=lambda s: None)
    with pytest.raises(StorageError, match=msg):
        st.ensure_ready()


def test_github_caches_unchanged_files():
    st, fake = gh()
    ds = DataStore(st)
    for i in range(3):
        st.write(f"logs/2026-10-1{i}_A_000000.json", {"id": f"2026-10-1{i}_A_000000", "date": f"2026-10-1{i}", "sessionId": "A", "exercises": []})
    st._cache.clear()
    assert len(ds.load_logs()) == 3
    n_get = sum(1 for m, u in fake.calls if m == "GET" and "/contents/logs/" in u)
    ds.load_logs()  # seconda lettura: solo la lista, nessun file riscaricato
    n_get2 = sum(1 for m, u in fake.calls if m == "GET" and "/contents/logs/" in u)
    assert n_get == 3 and n_get2 == 3


def test_github_rejects_bad_config():
    with pytest.raises(StorageError):
        GitHubStorage("", "a/b")
    with pytest.raises(StorageError):
        GitHubStorage("t", "noslash")


def test_make_storage(tmp_path):
    st, err = make_storage({}, tmp_path)
    assert st.kind == "local" and err is None
    st, err = make_storage({"GITHUB_TOKEN": "x"}, tmp_path)
    assert st.kind == "local" and "incompleti" in err
    st, err = make_storage({"GITHUB_TOKEN": "x", "GITHUB_REPO": "a/b"}, tmp_path)
    assert st.kind == "github" and st.branch == "main"


def test_local_path_traversal(tmp_path):
    st = LocalStorage(tmp_path / "d")
    with pytest.raises(StorageError):
        st.read("../../etc/passwd")


def test_save_log_idempotent_after_lost_response(storage, plan):
    """Bug 1: PUT riuscita ma risposta/cancellazione bozza fallita → al nuovo 'Termina e salva'
    non deve nascere un secondo file, anche se l'id calcolato fosse diverso."""
    ds = DataStore(storage)
    ds.bootstrap(plan)
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    first = L.finalize(d, datetime(2026, 10, 19, 19, 0, 0))
    ds.save_log(first)
    retry = dict(first, id="2026-10-19_A_235959")  # es. log prodotto da una versione vecchia
    assert ds.save_log(retry) == L.log_path(first)
    assert len(ds.load_logs()) == 1
    assert ds.find_log_by_draft(d["id"])["id"] == first["id"]


def test_two_sessions_shared_datastore_keep_all_sets(storage, plan):
    """Bug 2: due schede/dispositivi con lo stesso DataStore (SHA condiviso) si sovrascrivevano.
    Ogni scrittura della bozza rilegge lo SHA e unisce le serie."""
    import copy
    ds = DataStore(storage)
    ds.bootstrap(plan)
    d = L.new_draft(plan, "A", [], week=1, day=date(2026, 10, 19), now_ms=T0)
    ds.save_draft(d)
    tab1, tab2 = copy.deepcopy(d), copy.deepcopy(d)
    key = "A-superset-a:back-squat"
    ev = lambda n, t: {"id": str(n), "draftId": d["id"], "exKey": key, "type": "set", "n": n, "kg": 100, "reps": 5, "done": True, "t": t}
    L.apply_events(tab1, [ev(1, T0 + 1)], T0)
    tab1 = ds.save_draft(tab1)
    L.apply_events(tab2, [ev(2, T0 + 2)], T0)
    tab2 = ds.save_draft(tab2)           # stesso DataStore: SHA aggiornato da tab1
    L.apply_events(tab1, [ev(3, T0 + 3)], T0)
    tab1 = ds.save_draft(tab1)
    remote = ds.get_draft()
    assert [s["done"] for s in L.find_ex(remote, key)["sets"]] == [True, True, True, False]
    assert [s["done"] for s in L.find_ex(tab1, key)["sets"][:3]] == [True, True, True]


def test_two_sessions_separate_datastores_concurrent(storage, plan):
    import copy
    a, b = DataStore(storage), DataStore(storage)
    a.bootstrap(plan)
    d = L.new_draft(plan, "C", [], week=1, day=date(2026, 10, 23), now_ms=T0)
    a.save_draft(d)
    da, db = copy.deepcopy(b.get_draft()), copy.deepcopy(a.get_draft())
    key = "C-vest:push-up-zavorrati"
    for i in range(1, 5):
        target, store = (da, a) if i % 2 else (db, b)
        L.apply_events(target, [{"id": str(i), "draftId": d["id"], "exKey": key, "type": "set", "n": i, "kg": 8, "reps": 12, "done": True, "t": T0 + i}], T0)
        saved = store.save_draft(target)
        target.clear(); target.update(saved)
    assert all(s["done"] for s in L.find_ex(a.get_draft(), key)["sets"])

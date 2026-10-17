from lib import auth as A


def test_device_token_roundtrip_and_revoke():
    token, rec = A.new_device("Telefono", "2026-10-19")
    assert token not in str(rec) and rec["hash"] == A.token_hash(token)  # in settings solo l'hash
    devs = [rec]
    assert A.verify_token(token, devs)["id"] == rec["id"]
    assert A.verify_token("sbagliato", devs) is None
    assert A.verify_token(None, devs) is None and A.verify_token(token, None) is None
    assert A.verify_token(token, A.revoke(devs, rec["id"])) is None


def test_tokens_are_random():
    t1, _ = A.new_device("a", "x")
    t2, _ = A.new_device("a", "x")
    assert t1 != t2 and len(t1) >= 40


def test_check_password():
    assert A.check_password("abc", "abc")
    assert not A.check_password("abd", "abc")
    assert not A.check_password("", "")


def test_rate_limiter():
    now = [1000.0]
    rl = A.RateLimiter(max_fails=5, window=600, clock=lambda: now[0])
    for _ in range(4):
        rl.fail()
    assert rl.locked_for() == 0
    rl.fail()
    assert rl.locked_for() == 600
    now[0] += 300
    assert rl.locked_for() == 300
    now[0] += 301
    assert rl.locked_for() == 0
    rl.fail(); rl.success()
    assert rl.fails == []

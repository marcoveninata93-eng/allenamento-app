/* Codice condiviso dai componenti: protocollo Streamlit (senza librerie), outbox in
 * localStorage e timer di recupero installato nella pagina principale (stessa origine). */
(function () {
  "use strict";
  const W = window;
  const S = (W.AllenLib = W.AllenLib || {});
  const OUTBOX = "allen_outbox_v1";

  // ------------------------------------------------------------- protocollo Streamlit
  S.send = function (type, data) {
    W.parent.postMessage(Object.assign({ isStreamlitMessage: true, type: type }, data || {}), "*");
  };
  S.setValue = function (value) {
    S.send("streamlit:setComponentValue", { value: value, dataType: "json" });
  };
  S.setHeight = function (h) {
    const height = h === undefined ? Math.ceil(document.documentElement.scrollHeight) : h;
    if (height !== S._lastH) {
      S._lastH = height;
      S.send("streamlit:setFrameHeight", { height: height });
    }
  };
  S.onRender = function (fn) {
    W.addEventListener("message", function (ev) {
      const d = ev.data;
      if (d && d.type === "streamlit:render") fn(d.args || {}, d);
    });
    S.send("streamlit:componentReady", { apiVersion: 1 });
  };

  // ------------------------------------------------------------- storage locale
  S.lsGet = function (k, dflt) {
    try {
      const v = W.localStorage.getItem(k);
      return v === null ? dflt : JSON.parse(v);
    } catch (e) {
      return dflt;
    }
  };
  S.lsSet = function (k, v) {
    try {
      W.localStorage.setItem(k, JSON.stringify(v));
      return true;
    } catch (e) {
      return false;
    }
  };
  S.lsDel = function (k) {
    try { W.localStorage.removeItem(k); } catch (e) {}
  };
  S.outbox = function () { return S.lsGet(OUTBOX, []) || []; };
  S.saveOutbox = function (list) { return S.lsSet(OUTBOX, list); };
  S.pushEvent = function (ev) {
    const list = S.outbox().filter(function (e) { return e.id !== ev.id; });
    list.push(ev);
    return S.saveOutbox(list);
  };

  // ------------------------------------------------------------- timer nella pagina principale
  const TIMER_CODE = function () {
    if (window.__allenRest) return;
    const K = "allen_rest";
    const R = (window.__allenRest = { caps: {} });
    let ctx = null, wakeLock = null, box = null;
    const AC = window.AudioContext || window.webkitAudioContext;
    R.caps = { vibrate: "vibrate" in navigator, wakeLock: "wakeLock" in navigator, audio: !!AC };
    function get() { try { return JSON.parse(localStorage.getItem(K) || "null"); } catch (e) { return null; } }
    function put(v) { try { if (v) localStorage.setItem(K, JSON.stringify(v)); else localStorage.removeItem(K); } catch (e) {} }
    R.unlock = function () {
      try {
        if (!ctx && AC) ctx = new AC();
        if (ctx && ctx.state === "suspended") ctx.resume();
        R.caps.audioState = ctx ? ctx.state : "none";
      } catch (e) { R.caps.audioError = String(e); }
    };
    document.addEventListener("pointerdown", R.unlock, true);
    function beep(times) {
      try {
        if (!ctx) return;
        for (let i = 0; i < times; i++) {
          const o = ctx.createOscillator(), g = ctx.createGain();
          o.type = "sine"; o.frequency.value = 880;
          const t0 = ctx.currentTime + i * 0.35;
          g.gain.setValueAtTime(0.0001, t0);
          g.gain.exponentialRampToValueAtTime(0.6, t0 + 0.02);
          g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.25);
          o.connect(g); g.connect(ctx.destination); o.start(t0); o.stop(t0 + 0.3);
        }
      } catch (e) {}
    }
    R.beep = beep;
    function flash() {
      const f = document.createElement("div");
      f.style.cssText = "position:fixed;inset:0;z-index:100000;pointer-events:none;background:#22c55e;opacity:0;transition:opacity .15s";
      document.body.appendChild(f);
      let n = 0;
      const iv = setInterval(function () {
        f.style.opacity = n % 2 ? "0" : "0.55"; n++;
        if (n > 6) { clearInterval(iv); f.remove(); }
      }, 220);
    }
    R.wake = function () {
      try {
        if (!("wakeLock" in navigator) || wakeLock) return;
        navigator.wakeLock.request("screen").then(function (l) {
          wakeLock = l; R.caps.wakeLockActive = true;
          l.addEventListener("release", function () { wakeLock = null; R.caps.wakeLockActive = false; });
        }).catch(function (e) { R.caps.wakeLockError = String(e && e.name || e); });
      } catch (e) { R.caps.wakeLockError = String(e); }
    };
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible" && R.keepAwake) R.wake();
    });
    function fmt(s) { const m = Math.floor(s / 60), r = s % 60; return m + ":" + (r < 10 ? "0" : "") + r; }
    function ensureBox() {
      if (box && document.body.contains(box)) return box;
      box = document.createElement("div");
      box.id = "allen-rest";
      box.innerHTML =
        '<div class="ar-in"><div class="ar-l"><div class="ar-lab"></div><div class="ar-t"></div></div>' +
        '<button data-a="-15">−15</button><button data-a="15">+15</button><button data-a="x" aria-label="Chiudi">✕</button></div>' +
        '<div class="ar-bar"><div class="ar-fill"></div></div>';
      const st = document.createElement("style");
      st.textContent =
        "#allen-rest{position:fixed;left:8px;right:8px;bottom:10px;z-index:99999;background:#1b1f2a;border:1px solid #FF7A1A;border-radius:14px;box-shadow:0 6px 24px rgba(0,0,0,.5);font-family:system-ui,sans-serif;color:#fff;display:none;max-width:560px;margin:0 auto}" +
        "#allen-rest .ar-in{display:flex;align-items:center;gap:6px;padding:8px 10px}" +
        "#allen-rest .ar-l{flex:1;min-width:0}#allen-rest .ar-lab{font-size:13px;opacity:.8;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
        "#allen-rest .ar-t{font-size:30px;font-weight:800;font-variant-numeric:tabular-nums;line-height:1.1}" +
        "#allen-rest button{min-width:52px;height:48px;border-radius:10px;border:1px solid #3a4152;background:#262c3a;color:#fff;font-size:17px;font-weight:700}" +
        "#allen-rest.done{border-color:#22c55e;background:#12301f}#allen-rest .ar-bar{height:4px;background:#2a3040;border-radius:0 0 14px 14px;overflow:hidden}" +
        "#allen-rest .ar-fill{height:100%;background:#FF7A1A;width:0}";
      document.head.appendChild(st);
      document.body.appendChild(box);
      box.addEventListener("click", function (e) {
        const a = e.target && e.target.getAttribute && e.target.getAttribute("data-a");
        if (!a) return;
        R.unlock();
        const v = get();
        if (!v) return;
        if (a === "x") { put(null); render(); return; }
        v.end += parseInt(a, 10) * 1000; v.dur = Math.max(1, v.dur + parseInt(a, 10));
        if (v.end > Date.now()) v.fired = false;
        put(v); render();
      });
      return box;
    }
    function render() {
      const v = get();
      const b = ensureBox();
      if (!v) { b.style.display = "none"; return; }
      const now = Date.now();
      const rem = Math.ceil((v.end - now) / 1000);
      b.style.display = "block";
      b.querySelector(".ar-lab").textContent = (rem > 0 ? "Recupero" : "Recupero finito") + (v.label ? " · " + v.label : "");
      b.querySelector(".ar-fill").style.width = Math.max(0, Math.min(100, 100 * (1 - (v.end - now) / (v.dur * 1000)))) + "%";
      if (rem > 0) {
        b.classList.remove("done");
        b.querySelector(".ar-t").textContent = fmt(rem);
      } else {
        b.classList.add("done");
        b.querySelector(".ar-t").textContent = "VIA! 💪";
        if (!v.fired) {
          v.fired = true; put(v);
          if (v.vibrate !== false) { try { R.caps.vibrateResult = navigator.vibrate([350, 120, 350, 120, 350]); } catch (e) {} }
          if (v.sound !== false) beep(3);
          flash();
        }
        if (now - v.end > 12000) { put(null); b.style.display = "none"; }
      }
    }
    R.render = render;
    R.start = function (sec, label, opts) {
      opts = opts || {};
      R.unlock();
      R.keepAwake = opts.wakeLock !== false;
      if (R.keepAwake) R.wake();
      put({ end: Date.now() + sec * 1000, dur: sec, label: label || "", fired: false, sound: opts.sound, vibrate: opts.vibrate });
      render();
    };
    setInterval(render, 250);
    render();
  };

  S.installTimer = function () {
    try {
      const P = W.parent;
      if (P.__allenRest) return P.__allenRest;
      const sc = P.document.createElement("script");
      sc.textContent = "(" + TIMER_CODE.toString() + ")();";
      P.document.head.appendChild(sc);
      return P.__allenRest;
    } catch (e) {
      return null;
    }
  };
  S.startRest = function (sec, label, opts) {
    const R = S.installTimer();
    if (R) R.start(sec, label, opts);
    // feedback immediato anche se il timer non è disponibile
    try { if (opts && opts.vibrate !== false && navigator.vibrate) navigator.vibrate(40); } catch (e) {}
  };
})();

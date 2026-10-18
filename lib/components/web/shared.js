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
      f.style.cssText = "position:fixed;inset:0;z-index:100000;pointer-events:none;background:#5AB8FF;opacity:0;transition:opacity .15s";
      document.body.appendChild(f);
      let n = 0;
      const iv = setInterval(function () {
        f.style.opacity = n % 2 ? "0" : "0.45"; n++;
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
    function fmt(s) { s = Math.max(0, s); const m = Math.floor(s / 60), r = s % 60; return m + ":" + (r < 10 ? "0" : "") + r; }
    function esc(t) { return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
    const RING = 2 * Math.PI * 96;
    const ICO_T = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/></svg>';
    // Pannello "Recupero" dal basso (stile Studio): anello che si svuota, −15″/+15″/Salta, "Poi: …".
    // Si riduce a una barra trascinandolo in basso o toccando la maniglia; si riapre toccando la barra.
    function ensureBox() {
      if (box && document.body.contains(box)) return box;
      box = document.createElement("div");
      box.id = "allen-rest";
      box.innerHTML =
        '<div class="ar-dim" data-a="min"></div>' +
        '<div class="ar-sheet" role="dialog" aria-label="Recupero">' +
        '<button class="ar-handle" data-a="toggle" aria-label="Riduci o apri il pannello del recupero"><i></i></button>' +
        '<div class="ar-full">' +
        '<div class="ar-lab">' + ICO_T + '<span></span></div>' +
        '<div class="ar-ring"><svg width="220" height="220" viewBox="0 0 220 220" aria-hidden="true"><circle cx="110" cy="110" r="96" fill="none" stroke="#24305A" stroke-width="12"/>' +
        '<circle class="ar-arc" cx="110" cy="110" r="96" fill="none" stroke="#5AB8FF" stroke-width="12" stroke-linecap="round" stroke-dasharray="' + RING.toFixed(1) + '" stroke-dashoffset="0"/></svg>' +
        '<div class="ar-c"><div class="ar-t">0:00</div><div class="ar-of"></div></div></div>' +
        '<div class="ar-btns"><button data-a="-15">−15″</button><button data-a="15">+15″</button><button class="ar-skip" data-a="x">Salta</button></div>' +
        '<div class="ar-next"><div><div class="ar-nk">Poi</div><div class="ar-nn"></div></div><div class="ar-nr"></div></div>' +
        '<div class="ar-foot"></div></div>' +
        '<div class="ar-mini" data-a="open"><div class="ar-mt"></div><div class="ar-ml"></div>' +
        '<button data-a="-15">−15</button><button data-a="15">+15</button><button data-a="x" aria-label="Salta">Salta</button></div>' +
        '<div class="ar-bar"><div class="ar-fill"></div></div></div>';
      const st = document.createElement("style");
      st.textContent =
        "#allen-rest{display:none;font-family:'Outfit',system-ui,sans-serif;color:#EEF2FF}" +
        "#allen-rest .ar-dim{position:fixed;inset:0;z-index:99998;background:rgba(8,12,28,.62);transition:opacity .2s}" +
        "#allen-rest .ar-sheet{position:fixed;left:0;right:0;bottom:0;z-index:99999;max-width:560px;margin:0 auto;background:#18223F;border:1px solid #2C3A6A;border-bottom:0;" +
        "border-radius:28px 28px 0 0;box-shadow:0 -12px 40px rgba(0,0,0,.5);padding:6px 24px calc(22px + env(safe-area-inset-bottom));transition:transform .22s ease;touch-action:none}" +
        "#allen-rest .ar-handle{display:block;margin:0 auto;width:84px;height:24px;border:0;background:transparent;padding:0}" +
        "#allen-rest .ar-handle i{display:block;margin:8px auto;width:44px;height:5px;border-radius:3px;background:#3B4A7E}" +
        "#allen-rest .ar-full{display:flex;flex-direction:column;align-items:center;gap:16px}" +
        "#allen-rest .ar-lab{display:flex;align-items:center;gap:8px;font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#5AB8FF;font-weight:600}" +
        "#allen-rest .ar-ring{position:relative;width:220px;height:220px}#allen-rest .ar-ring svg{position:absolute;inset:0;transform:rotate(-90deg)}" +
        "#allen-rest .ar-arc{transition:stroke-dashoffset .25s linear}" +
        "#allen-rest .ar-c{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px}" +
        "#allen-rest .ar-t{font-size:64px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.02em;line-height:1}" +
        "#allen-rest .ar-of{font-size:14px;color:#9DAAD0}" +
        "#allen-rest .ar-btns{width:100%;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}" +
        "#allen-rest button{font-family:inherit;cursor:pointer;touch-action:manipulation}" +
        "#allen-rest .ar-btns button{height:52px;border-radius:14px;border:0;background:#24305A;color:#EEF2FF;font-size:17px;font-weight:600}" +
        "#allen-rest .ar-btns .ar-skip{background:transparent;border:1px solid #5AB8FF;color:#5AB8FF}" +
        "#allen-rest .ar-next{width:100%;box-sizing:border-box;background:#0F1730;border-radius:16px;padding:14px 16px;display:flex;justify-content:space-between;align-items:center;gap:10px}" +
        "#allen-rest .ar-next>div:first-child{min-width:0}" +
        "#allen-rest .ar-nk{font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#9DAAD0}" +
        "#allen-rest .ar-nn{font-size:17px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}#allen-rest .ar-nn b{color:#5AB8FF}" +
        "#allen-rest .ar-nr{font-size:15px;color:#9DAAD0;white-space:nowrap}" +
        "#allen-rest .ar-foot{font-size:13px;color:#9DAAD0;text-align:center}" +
        "#allen-rest .ar-mini{display:none;align-items:center;gap:6px;padding:2px 0 4px}" +
        "#allen-rest .ar-mt{font-size:30px;font-weight:700;font-variant-numeric:tabular-nums;min-width:78px}" +
        "#allen-rest .ar-ml{flex:1;min-width:0;font-size:13px;color:#9DAAD0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}" +
        "#allen-rest .ar-mini button{min-width:52px;height:46px;border-radius:14px;border:0;background:#24305A;color:#EEF2FF;font-size:16px;font-weight:600;padding:0 8px}" +
        "#allen-rest .ar-bar{display:none;height:4px;background:#24305A;border-radius:2px;overflow:hidden;margin-top:6px}#allen-rest .ar-fill{height:100%;background:#5AB8FF;width:0}" +
        "#allen-rest.min .ar-dim{display:none}#allen-rest.min .ar-full{display:none}#allen-rest.min .ar-mini{display:flex}#allen-rest.min .ar-bar{display:block}" +
        "#allen-rest.min .ar-sheet{padding:0 14px calc(10px + env(safe-area-inset-bottom));border-radius:22px 22px 0 0}" +
        "#allen-rest.min .ar-handle{height:18px}#allen-rest.min .ar-handle i{margin:6px auto}" +
        "#allen-rest.done .ar-t,#allen-rest.done .ar-mt{color:#5AB8FF}";
      document.head.appendChild(st);
      document.body.appendChild(box);
      box.addEventListener("click", function (e) {
        const el = e.target && e.target.closest ? e.target.closest("[data-a]") : null;
        if (!el) return;
        if (Date.now() - (R.dragEnd || 0) < 350) return;  // il tap che chiude un trascinamento
        const a = el.getAttribute("data-a");
        R.unlock();
        const v = get();
        if (!v) return;
        if (a === "min") { v.min = true; put(v); render(); return; }
        if (a === "toggle") { v.min = !v.min; put(v); render(); return; }
        if (a === "open") { v.min = false; put(v); render(); return; }
        if (a === "x") { put(null); render(); return; }
        const d = parseInt(a, 10);
        if (isNaN(d)) return;
        e.stopPropagation();
        v.end += d * 1000; v.dur = Math.max(1, v.dur + d);
        if (v.end > Date.now()) v.fired = false;
        if (v.end - Date.now() > 10000) v.warned = false;
        put(v); render();
      });
      // trascinare il pannello in basso lo riduce a barra (verso l'alto lo riapre)
      const sheet = box.querySelector(".ar-sheet");
      let y0 = null, dy = 0;
      sheet.addEventListener("pointerdown", function (e) {
        if (e.target.closest("button:not(.ar-handle)")) return;
        y0 = e.clientY; dy = 0; sheet.style.transition = "none";
      });
      window.addEventListener("pointermove", function (e) {
        if (y0 === null) return;
        dy = e.clientY - y0;
        const v = get();
        if (v && !v.min && dy > 0) sheet.style.transform = "translateY(" + dy + "px)";
      });
      function endDrag() {
        if (y0 === null) return;
        sheet.style.transition = ""; sheet.style.transform = "";
        const v = get();
        if (v && Math.abs(dy) > 40) { v.min = dy > 0; put(v); render(); R.dragEnd = Date.now(); }
        y0 = null;
      }
      window.addEventListener("pointerup", endDrag);
      window.addEventListener("pointercancel", endDrag);
      return box;
    }
    function render() {
      const v = get();
      const b = ensureBox();
      if (!v) { b.style.display = "none"; return; }
      const now = Date.now();
      const rem = Math.ceil((v.end - now) / 1000);
      const frac = Math.max(0, Math.min(1, (v.end - now) / (v.dur * 1000)));
      b.style.display = "block";
      b.classList.toggle("min", !!v.min);
      const nx = v.next || {};
      const nName = nx.name ? ((nx.code ? "<b>" + esc(nx.code) + "</b> " : "") + esc(nx.name)) : esc(v.label || "Fine blocco");
      b.querySelector(".ar-nn").innerHTML = nName;
      b.querySelector(".ar-nr").textContent = (nx.set ? "serie " + nx.set + " " : "") + (nx.reps || "");
      b.querySelector(".ar-ml").innerHTML = (rem > 0 ? "Recupero" : "Recupero finito") + (nx.name ? " · poi " + nName : "");
      const foot = [];
      if (v.vibrate !== false) foot.push("Vibrazione a −10″ e allo zero");
      else if (v.sound !== false) foot.push("Beep allo zero");
      if (R.keepAwake) foot.push("schermo sempre acceso");
      b.querySelector(".ar-foot").textContent = foot.join(" · ");
      b.querySelector(".ar-of").textContent = "di " + fmt(v.dur);
      b.querySelector(".ar-arc").setAttribute("stroke-dashoffset", (RING * (1 - frac)).toFixed(1));
      b.querySelector(".ar-fill").style.width = (100 * (1 - frac)) + "%";
      if (rem > 0) {
        b.classList.remove("done");
        b.querySelector(".ar-lab span").textContent = v.started === false ? "Recupero" : "Recupero · partito da solo";
        b.querySelector(".ar-t").textContent = fmt(rem);
        b.querySelector(".ar-mt").textContent = fmt(rem);
        if (rem <= 10 && !v.warned) {
          v.warned = true; put(v);
          if (v.vibrate !== false && v.dur > 12) { try { navigator.vibrate(200); } catch (e) {} }
        }
      } else {
        b.classList.add("done");
        b.querySelector(".ar-lab span").textContent = "Recupero finito";
        b.querySelector(".ar-t").textContent = "Via!";
        b.querySelector(".ar-mt").textContent = "Via!";
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
      put({ end: Date.now() + sec * 1000, dur: sec, label: label || "", fired: false, warned: false, min: false,
            next: opts.next || null, sound: opts.sound, vibrate: opts.vibrate });
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

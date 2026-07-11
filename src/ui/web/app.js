/* A.T.L.A.S. FUI controller — vanilla JS, no frameworks.
   Signature element: the "Seismic Voiceline" — a HiDPI <canvas> readout line.
   Receives batched events from Python via window.atlas.push([...]); calls back
   through pywebview.api. The bridge surface is unchanged so the backend needs
   no edits; window.atlas.onAmplitude(cb) is an additive hook. */
"use strict";

const $ = (id) => document.getElementById(id);
const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const clamp01 = (v) => Math.max(0, Math.min(1, v));

const els = {
  boot: $("boot"), bootScope: $("bootScope"), bootWord: $("bootWord"), bootSub: $("bootSub"),
  hud: $("hud"), ver: $("ver"), stateLabel: $("stateLabel"), ticker: $("ticker"),
  scope: $("scope"), stream: $("stream"), entry: $("entry"), mic: $("micBtn"),
  provVal: $("provVal"), tokVal: $("tokVal"), cpuVal: $("cpuVal"), ramVal: $("ramVal"),
  readouts: $("readouts"), tabBtn: $("tabBtn"),
  progress: $("progress"), progLabel: $("progLabel"), progFill: $("progFill"),
  updateBanner: $("updateBanner"), updateText: $("updateText"), updateBtn: $("updateBtn"),
  scrim: $("scrim"), mTitle: $("mTitle"), mDetail: $("mDetail"), allow: $("allowBtn"), deny: $("denyBtn"),
  keyBtn: $("keyBtn"), keybar: $("keybar"), keyInput: $("keyInput"), keySave: $("keySave"),
  keyRow: $("keyRow"), keyDone: $("keyDone"), keyRestart: $("keyRestart"), keyModel: $("keyModel"),
};

/* ---------------- amplitude bridge ---------------- */
let extAmp = null, extAmpTs = 0;
const ampSubs = [];
function setAmplitude(v) { extAmp = clamp01(+v || 0); extAmpTs = performance.now(); }

/* ---------------- seismic voiceline (HiDPI canvas) ---------------- */
const scope = (() => {
  const cv = els.scope, ctx = cv.getContext("2d");
  const N = 200;                    // samples across the width
  const buf = new Float32Array(N);  // one geometry source of truth
  let W = 0, H = 0, MID = 0, AMP = 0;
  let state = "idle", env = 0.05, envTarget = 0.05, amber = 0, amberTarget = 0, reveal = 1;
  const BASE = { idle: 0.05, listening: 0.55, thinking: 0.30, tool: 0.85, speaking: 0.72, boot: 0.4 };
  const VIOLET = [168, 85, 247], AMBER = [255, 179, 71], HOT = "#d8b4fe";

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);   // render at up to 2x
    const r = cv.getBoundingClientRect();
    cv.width = Math.max(1, Math.round(r.width * dpr));
    cv.height = Math.max(1, Math.round(r.height * dpr));
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);                   // draw in CSS px, sharp
    W = r.width; H = r.height; MID = H / 2; AMP = H * 0.34;   // radius/amp constant
  }
  window.addEventListener("resize", resize);

  function setState(s) {
    state = s;
    envTarget = BASE[s] != null ? BASE[s] : 0.12;
    amberTarget = s === "tool" ? 1 : 0;
    els.stateLabel.textContent = s.toUpperCase();
    els.stateLabel.classList.toggle("tool", s === "tool");
    if (s !== "tool") els.ticker.textContent = "";
  }
  function revealFrom(v) { reveal = v; }

  function amplitude(t) {
    let a;
    if (extAmp != null && performance.now() - extAmpTs < 250) a = extAmp;
    else if (state === "listening") a = 0.35 + 0.3 * Math.abs(Math.sin(t * 7)) + 0.12 * Math.random();
    else if (state === "speaking") a = 0.4 + 0.45 * Math.abs(Math.sin(t * 11)) * (0.6 + 0.4 * Math.sin(t * 2.3));
    else a = 0.25;
    a = clamp01(a);
    for (const cb of ampSubs) { try { cb(a); } catch (e) { /* ignore */ } }
    return a;
  }

  function nextSample(t) {
    const e = env;
    switch (state) {
      case "idle":       return e * (0.5 * Math.sin(t * 1.6) + 0.12 * (Math.random() - 0.5));
      case "listening":  return e * amplitude(t) * (Math.random() < 0.5 ? 1 : -1) * (0.6 + 0.5 * Math.random());
      case "thinking": { // scanning base + sparse sharp EKG blip, speed varies
        const blip = Math.sin(t * 3.1) > 0.985 ? (Math.random() < 0.5 ? 1 : -1) * 1.4 : 0;
        return e * (0.18 * Math.sin(t * (2.0 + 0.6 * Math.sin(t * 0.5))) + blip);
      }
      case "tool":       return e * (Math.random() - 0.5) * 1.7;   // amber burst
      case "speaking":   return e * amplitude(t) * Math.sin(t * 20) * (0.7 + 0.3 * Math.sin(t * 3));
      default:           return e * 0.3 * Math.sin(t * 4);
    }
  }

  function strokeColor() {
    const c = VIOLET.map((x, i) => Math.round(x + (AMBER[i] - x) * amber));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }

  let last = 0;
  function frame(ms) {
    const t = ms / 1000;
    // smooth (non-linear) easing toward targets, frame-rate tolerant
    const k = reduce ? 1 : 0.09;
    env += (envTarget - env) * k;
    amber += (amberTarget - amber) * k;
    reveal += (1 - reveal) * (reduce ? 1 : 0.12);

    // advance the line
    for (let i = 0; i < N - 1; i++) buf[i] = buf[i + 1];
    buf[N - 1] = nextSample(t);

    if (!els.hud.hidden) {
      if (W === 0) resize();
      ctx.clearRect(0, 0, W, H);
      // thin baseline + ticks (structure, low light)
      ctx.strokeStyle = "rgba(168,85,247,.12)"; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(0, MID); ctx.lineTo(W, MID); ctx.stroke();
      for (let gx = 0; gx <= W; gx += 40) {
        ctx.beginPath(); ctx.moveTo(gx, MID - 4); ctx.lineTo(gx, MID + 4); ctx.stroke();
      }
      // scan bar while thinking
      if (state === "thinking") {
        const sx = ((t * 0.35) % 1) * W;
        ctx.strokeStyle = "rgba(168,85,247,.22)"; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(sx, 6); ctx.lineTo(sx, H - 6); ctx.stroke();
      }
      // the voiceline
      const col = strokeColor();
      const drawN = Math.max(2, Math.floor(N * reveal));
      const step = W / (N - 1);
      ctx.strokeStyle = col; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.lineCap = "round";
      ctx.shadowColor = col; ctx.shadowBlur = 8;
      ctx.beginPath();
      for (let i = 0; i < drawN; i++) {
        const x = i * step, y = MID - buf[N - drawN + i] * AMP;
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      }
      ctx.stroke(); ctx.shadowBlur = 0;
      // hot core node riding the leading edge
      const cx = (drawN - 1) * step, cy = MID - buf[N - 1] * AMP;
      ctx.fillStyle = amber > 0.5 ? "#ffb347" : HOT;
      ctx.beginPath(); ctx.arc(Math.min(W - 2, cx), cy, 2.6, 0, 7); ctx.fill();
    }
    last = ms;
    requestAnimationFrame(frame);
  }

  resize();
  requestAnimationFrame(frame);
  return { setState, resize, revealFrom };
})();

/* ---------------- streaming typewriter ---------------- */
const typer = (() => {
  let q = [], caret = null;
  function ensureCaret() {
    if (!caret) { caret = document.createElement("span"); caret.className = "caret"; caret.textContent = "▍"; els.stream.appendChild(caret); }
  }
  function push(text) { for (const ch of text) q.push([ch, ""]); }
  function line(text, cls) { for (const ch of ("\n" + text + "\n")) q.push([ch, cls || ""]); }
  function tick() {
    if (q.length) {
      ensureCaret();
      const n = Math.min(q.length, reduce ? 60 : 4);
      for (let i = 0; i < n; i++) {
        const [ch, cls] = q.shift();
        if (cls) { const s = document.createElement("span"); s.className = cls; s.textContent = ch; els.stream.insertBefore(s, caret); }
        else els.stream.insertBefore(document.createTextNode(ch), caret);
      }
      els.stream.scrollTop = els.stream.scrollHeight;
    }
    setTimeout(tick, 33);
  }
  tick();
  return { push, line };
})();

/* ---------------- event handling ---------------- */
function handle(kind, payload) {
  switch (kind) {
    case "boot": runBoot(payload); break;
    case "state": scope.setState(payload); break;
    case "stream": typer.push(payload); break;
    case "tool": scope.setState("tool"); els.ticker.textContent = payload; typer.line("[" + payload + "]", "tool"); break;
    case "notify": typer.line(payload, "dim"); break;
    case "speak": break;                       // TTS in Python; 'speaking' arrives via state
    case "amplitude": setAmplitude(payload); break;
    case "provider": els.provVal.textContent = String(payload).toUpperCase(); break;
    case "stat": {
      const [cpu, ram, tokens, prov] = payload;
      els.cpuVal.textContent = cpu + "%"; els.ramVal.textContent = ram + "%";
      els.tokVal.textContent = tokens; if (prov) els.provVal.textContent = String(prov).toUpperCase();
      break;
    }
    case "progress": {
      const [label, pct] = payload;
      els.progress.hidden = false; els.progLabel.textContent = label; els.progFill.style.width = pct + "%";
      if (pct >= 100) setTimeout(() => { els.progress.hidden = true; }, 1500);
      break;
    }
    case "mic": els.mic.classList.toggle("muted", !!payload); els.mic.title = payload ? "Microphone muted" : "Mute microphone"; break;
    case "update": { const [ver, url] = payload; els.updateBanner.hidden = false; els.updateText.textContent = "UPDATE AVAILABLE — " + ver; els.updateBanner.dataset.url = url; break; }
    case "confirm": showModal(payload); break;
    case "focus_input": els.entry.focus(); break;
  }
}
window.atlas = {
  push: (events) => { for (const e of events) handle(e.kind, e.payload); },
  setAmplitude,
  onAmplitude: (cb) => { if (typeof cb === "function") ampSubs.push(cb); },
};

/* ---------------- boot: line draws in, wordmark resolves (≤1.5s) ---------------- */
let booted = false;
function runBoot() {
  if (booted) return; booted = true;
  const cv = els.bootScope, ctx = cv.getContext("2d");
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const r = cv.getBoundingClientRect();
  cv.width = r.width * dpr; cv.height = r.height * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const W = r.width, H = r.height, MID = H / 2;
  const t0 = performance.now(), DUR = reduce ? 1 : 1050;
  function step(now) {
    const p = clamp01((now - t0) / DUR);
    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(168,85,247,.15)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(0, MID); ctx.lineTo(W, MID); ctx.stroke();
    ctx.strokeStyle = "#a855f7"; ctx.lineWidth = 2; ctx.lineCap = "round";
    ctx.shadowColor = "#a855f7"; ctx.shadowBlur = 8; ctx.beginPath();
    const drawTo = W * p;
    for (let x = 0; x <= drawTo; x += 3) {
      const y = MID - Math.sin(x * 0.06 + now * 0.006) * (H * 0.28) * Math.sin(p * Math.PI);
      x ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    }
    ctx.stroke(); ctx.shadowBlur = 0;
    if (p < 1 && booted) requestAnimationFrame(step); else finishBoot();
  }
  requestAnimationFrame(step);
}
function finishBoot() {
  if (els.boot.classList.contains("hide")) return;
  els.boot.classList.add("hide");
  els.hud.hidden = false;
  scope.resize(); scope.revealFrom(0);          // main line draws in
  setTimeout(() => { els.boot.remove(); els.entry.focus(); }, 420);
}

/* ---------------- confirmation modal ---------------- */
let currentConfirm = null;
function showModal({ id, title, detail }) {
  currentConfirm = id;
  els.mTitle.textContent = title; els.mDetail.textContent = detail || "(no arguments)";
  els.scrim.hidden = false; els.allow.focus();
}
function answer(ok) {
  if (currentConfirm != null) callApi("confirm", currentConfirm, ok);
  currentConfirm = null; els.scrim.hidden = true; els.entry.focus();
}

/* ---------------- pywebview bridge ---------------- */
function callApi(name, ...args) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api[name]) return window.pywebview.api[name](...args);
  return null;
}

/* ---------------- API key panel ---------------- */
function toggleKeybar(force) {
  const show = force != null ? force : els.keybar.hidden;
  els.keybar.hidden = !show;
  if (show) els.keyInput.focus();
}
function saveKey() {
  const k = els.keyInput.value.trim();
  const model = els.keyModel ? els.keyModel.value : "";
  if (!k && !model) { els.keyInput.focus(); return; }
  // a gsk_ key is Groq; otherwise Gemini (the model box only applies to Gemini)
  const prov = /^gsk_/.test(k) ? "groq" : "gemini";
  Promise.resolve(callApi("save_api_key", k, prov, prov === "gemini" ? model : "")).then((ok) => {
    if (ok !== false) { els.keyRow.hidden = true; els.keyDone.hidden = false; els.keyInput.value = ""; }
  });
}

/* ---------------- input wiring ---------------- */
els.entry.addEventListener("keydown", (e) => {
  if (e.key === "Enter") { const v = els.entry.value.trim(); if (v) { typer.line("❯ " + v, "dim"); callApi("submit", v); els.entry.value = ""; } }
  else if (e.key === "Escape") { callApi("toggle"); }
});
els.mic.addEventListener("click", () => callApi("mic_toggle"));
els.allow.addEventListener("click", () => answer(true));
els.deny.addEventListener("click", () => answer(false));
els.updateBtn.addEventListener("click", () => callApi("install_update"));
els.keyBtn.addEventListener("click", () => toggleKeybar());
els.keySave.addEventListener("click", saveKey);
els.keyInput.addEventListener("keydown", (e) => { if (e.key === "Enter") saveKey(); });
els.keyRestart.addEventListener("click", () => callApi("restart_app"));
els.tabBtn.addEventListener("click", () => { els.readouts.hidden = !els.readouts.hidden; });

document.addEventListener("keydown", (e) => {
  // any key skips the boot sequence while its overlay is still on screen
  if (els.boot && document.body.contains(els.boot) && !els.boot.classList.contains("hide")) {
    finishBoot(); return;
  }
  if (!els.scrim.hidden) { if (e.key === "Escape") answer(false); if (e.key === "Enter") answer(true); return; }
  if (e.key === "Tab") { e.preventDefault(); els.readouts.hidden = !els.readouts.hidden; }
});
/* click neutral chrome re-focuses the command input so typing always lands */
document.addEventListener("mousedown", (e) => {
  const t = e.target;
  if (t.tagName === "INPUT" || t.tagName === "BUTTON" || t.tagName === "A") return;
  if (!els.scrim.hidden || !els.keybar.hidden) return;
  setTimeout(() => els.entry.focus(), 0);
});

/* ---------------- ready handshake ---------------- */
let readySignalled = false;
function signalReady() {
  if (readySignalled) return; readySignalled = true;
  Promise.resolve(callApi("ready")).then((d) => {
    if (!d) return;
    if (d.version) els.ver.textContent = "v" + d.version;
    if (d.has_key === false) { toggleKeybar(true); typer.line("No API key yet — paste one above to activate A.T.L.A.S.", "dim"); }
    else els.entry.focus();
  });
}
window.addEventListener("pywebviewready", signalReady);
if (window.pywebview && window.pywebview.api) signalReady();

/* safety: reveal the HUD even if the Python boot event never arrives */
setTimeout(() => runBoot(), 12000);

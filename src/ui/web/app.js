/* A.T.L.A.S. FUI controller — vanilla JS, no frameworks.
   Receives batched events from Python via window.atlas.push([...]) and drives
   the orb, streaming text, panels, modal, progress and update banner. Calls
   back into Python through pywebview.api. */
"use strict";

const $ = (id) => document.getElementById(id);
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

const els = {
  boot: $("boot"), bootSub: $("bootSub"), bootFill: $("bootFill"),
  hud: $("hud"), ver: $("ver"), stateLabel: $("stateLabel"),
  stream: $("stream"), entry: $("entry"), mic: $("micBtn"),
  cpuBar: $("cpuBar"), cpuVal: $("cpuVal"), ramBar: $("ramBar"), ramVal: $("ramVal"),
  provVal: $("provVal"), tokVal: $("tokVal"),
  progress: $("progress"), progLabel: $("progLabel"), progFill: $("progFill"),
  updateBanner: $("updateBanner"), updateText: $("updateText"), updateBtn: $("updateBtn"),
  scrim: $("scrim"), mTitle: $("mTitle"), mDetail: $("mDetail"),
  allow: $("allowBtn"), deny: $("denyBtn"),
};

/* ---------------- orb ---------------- */
const orb = (() => {
  const c = els.hud ? $("orb") : null;
  const ctx = c.getContext("2d");
  const CX = c.width / 2, CY = c.height / 2, BASE = c.width / 2 - 18;
  const VIOLET = "#a855f7", HOT = "#d8b4fe", DIM = "#6d28d9", AMBER = "#ffb347";
  let state = "idle", phase = 0, ripples = [];

  function set(s) { state = s; }
  function spawnRipple(r) { if (ripples.length < 6) ripples.push(r); }

  function draw() {
    phase += reduceMotion ? 0.03 : 0.09;
    ctx.clearRect(0, 0, c.width, c.height);
    let r;
    if (state === "listening") r = BASE * (0.72 + 0.14 * Math.sin(phase * 2.4));
    else if (state === "speaking") { r = BASE * 0.7; if (Math.floor(phase * 10) % 6 === 0) spawnRipple(r); }
    else r = BASE * (0.7 + 0.05 * Math.sin(phase * 0.7));

    ripples = ripples.filter((rp) => rp < BASE * 1.15).map((rp) => rp + 2.2);
    ripples.forEach((rp) => ring(rp, "rgba(168,85,247,.25)", 1));

    ring(r, DIM, 1);
    ring(r * 0.55, VIOLET, 2);
    disc(r * 0.18, HOT);

    const busy = state === "thinking" || state === "tool";
    const speed = busy ? 9 : 1.2;
    const col = state === "tool" ? AMBER : VIOLET;
    const ang = (phase * speed * 20) % 360;
    for (let i = 0; i < 3; i++) arc(r * 0.85, ang + i * 120, 70, col);
    requestAnimationFrame(draw);
  }
  const rad = (d) => (d * Math.PI) / 180;
  function ring(r, color, w) { ctx.beginPath(); ctx.arc(CX, CY, r, 0, 2 * Math.PI); ctx.strokeStyle = color; ctx.lineWidth = w; ctx.stroke(); }
  function disc(r, color) { ctx.beginPath(); ctx.arc(CX, CY, r, 0, 2 * Math.PI); ctx.fillStyle = color; ctx.shadowColor = color; ctx.shadowBlur = 12; ctx.fill(); ctx.shadowBlur = 0; }
  function arc(r, start, extent, color) { ctx.beginPath(); ctx.arc(CX, CY, r, rad(start), rad(start + extent)); ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.stroke(); }
  requestAnimationFrame(draw);
  return { set };
})();

/* ---------------- streaming typewriter ---------------- */
const typer = (() => {
  let queue = [], caret = null;
  function ensureCaret() {
    if (!caret) { caret = document.createElement("span"); caret.className = "caret"; caret.textContent = "▍"; els.stream.appendChild(caret); }
  }
  function push(text, cls) { for (const ch of text) queue.push([ch, cls || ""]); }
  function line(text, cls) { push("\n" + text + "\n", cls); }
  function tick() {
    if (queue.length) {
      ensureCaret();
      const n = Math.min(queue.length, reduceMotion ? 40 : 4);
      for (let i = 0; i < n; i++) {
        const [ch, cls] = queue.shift();
        const node = document.createTextNode(ch);
        if (cls) { const s = document.createElement("span"); s.className = cls; s.appendChild(node); els.stream.insertBefore(s, caret); }
        else els.stream.insertBefore(node, caret);
      }
      els.stream.scrollTop = els.stream.scrollHeight;
    }
    setTimeout(tick, 33);
  }
  tick();
  return { push, line };
})();

/* ---------------- event handling ---------------- */
function setState(s) {
  orb.set(s);
  els.stateLabel.textContent = s.toUpperCase();
  els.stateLabel.classList.toggle("tool", s === "tool");
}

function handle(kind, payload) {
  switch (kind) {
    case "boot": runBoot(payload); break;
    case "state": setState(payload); break;
    case "stream": typer.push(payload); break;
    case "tool": setState("tool"); typer.line("[" + payload + "]", "tool"); break;
    case "notify": typer.line(payload, "dim"); break;
    case "speak": break; // TTS handled in Python; orb 'speaking' arrives via state
    case "provider": els.provVal.textContent = String(payload).toUpperCase(); break;
    case "stat": {
      const [cpu, ram, tokens, prov] = payload;
      els.cpuBar.style.width = cpu + "%"; els.cpuVal.textContent = cpu + "%";
      els.ramBar.style.width = ram + "%"; els.ramVal.textContent = ram + "%";
      els.tokVal.textContent = tokens; if (prov) els.provVal.textContent = String(prov).toUpperCase();
      break;
    }
    case "progress": {
      const [label, pct] = payload;
      els.progress.hidden = false; els.progLabel.textContent = label;
      els.progFill.style.width = pct + "%";
      if (pct >= 100) setTimeout(() => { els.progress.hidden = true; }, 1500);
      break;
    }
    case "mic": els.mic.classList.toggle("muted", !!payload); els.mic.title = payload ? "Microphone muted" : "Mute microphone"; break;
    case "update": {
      const [ver, url] = payload; els.updateBanner.hidden = false;
      els.updateText.textContent = "UPDATE AVAILABLE — " + ver; els.updateBanner.dataset.url = url; break;
    }
    case "confirm": showModal(payload); break;
    case "focus_input": els.entry.focus(); break;
  }
}

window.atlas = { push: (events) => { for (const e of events) handle(e.kind, e.payload); } };

/* ---------------- boot animation ---------------- */
let booted = false;
function runBoot(text) {
  if (booted) return; booted = true;
  els.bootSub.textContent = text || "ONLINE";
  let p = 0; const iv = setInterval(() => {
    p = Math.min(100, p + 8); els.bootFill.style.width = p + "%";
    if (p >= 100) {
      clearInterval(iv);
      els.boot.classList.add("hide");
      els.hud.hidden = false;
      setTimeout(() => { els.boot.remove(); els.entry.focus(); }, 500);
    }
  }, reduceMotion ? 10 : 60);
}

/* ---------------- confirmation modal ---------------- */
let currentConfirm = null;
function showModal({ id, title, detail }) {
  currentConfirm = id;
  els.mTitle.textContent = title; els.mDetail.textContent = detail || "(no arguments)";
  els.scrim.hidden = false; els.allow.focus();
}
function answer(ok) {
  // Always dismiss the panel, even if no request is pending (a stray/stale
  // overlay must never be able to trap the UI).
  if (currentConfirm != null) callApi("confirm", currentConfirm, ok);
  currentConfirm = null; els.scrim.hidden = true; els.entry.focus();
}

/* ---------------- pywebview bridge helpers ---------------- */
function callApi(name, ...args) {
  if (window.pywebview && window.pywebview.api && window.pywebview.api[name]) {
    return window.pywebview.api[name](...args);
  }
  return null;
}

/* ---------------- input wiring ---------------- */
els.entry.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const t = els.entry.value.trim();
    if (t) { typer.line("❯ " + t, "dim"); callApi("submit", t); els.entry.value = ""; }
  } else if (e.key === "Escape") { callApi("toggle"); }
});
els.mic.addEventListener("click", () => callApi("mic_toggle"));
els.allow.addEventListener("click", () => answer(true));
els.deny.addEventListener("click", () => answer(false));
els.updateBtn.addEventListener("click", () => callApi("install_update"));
document.addEventListener("keydown", (e) => {
  if (!els.scrim.hidden) { if (e.key === "Escape") answer(false); if (e.key === "Enter") answer(true); }
});

/* signal readiness so Python can start pushing events */
window.addEventListener("pywebviewready", () => {
  const info = callApi("ready");
  Promise.resolve(info).then((d) => { if (d && d.version) els.ver.textContent = "· v" + d.version; });
});

import {
  REPLY_QUIET_MS,
  addBuyerLine,
  addSellerText,
  base64ToArrayBuffer,
  createDemoSession,
  hasPendingSeller,
  historyBeforeLastSeller,
  takeSellerTurn,
} from '../lib/demo-session.js';

const PROD_API = 'https://api.getvocify.com/api/v1';
const SCENARIO_KEY = 'vocify_demo_scenario';
const ECHO_GUARD_MS = 1200;

const $ = (id) => document.getElementById(id);
const desktop = () => window.vocifyDesktop;

let scenario = null;
let session = createDemoSession();
let ctx = null;
let current = null;
let playing = false;
let playedUntil = 0;
let replyTimer = null;
let turnToken = 0;
const buffers = new Map();

function setStatus(text, isError = false) {
  const el = $('demo-status');
  el.textContent = text;
  el.style.color = isError ? 'hsl(var(--destructive, 0 70% 45%))' : '';
}

function apiBase() {
  return (localStorage.getItem('vocify_api_base') || PROD_API).trim().replace(/\/+$/, '');
}

async function api(path, body) {
  const token = localStorage.getItem('vocify_access');
  if (!token) throw new Error('Inicia sesión en Vocify primero');
  const result = await desktop().saas.request({
    base: apiBase(),
    path,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body,
  });
  if (!result.ok) {
    const detail = typeof result.data?.detail === 'string' ? result.data.detail : result.error;
    throw new Error(result.status === 403 ? 'Solo owner o admin pueden usar el Demo buyer' : detail || 'Error');
  }
  return result.data;
}

function audioContext() {
  if (!ctx) ctx = new AudioContext();
  return ctx;
}

async function decode(id, b64) {
  buffers.set(id, await audioContext().decodeAudioData(base64ToArrayBuffer(b64)));
}

function stopAudio() {
  if (current) {
    current.onended = null;
    try { current.stop(); } catch { /* already stopped */ }
    current = null;
  }
  if (playing) playedUntil = Date.now();
  playing = false;
}

function play(id) {
  const buffer = buffers.get(id);
  if (!buffer) return;
  stopAudio();
  const ac = audioContext();
  if (ac.state === 'suspended') void ac.resume();
  const src = ac.createBufferSource();
  src.buffer = buffer;
  src.connect(ac.destination);
  src.onended = () => {
    playing = false;
    playedUntil = Date.now();
    current = null;
  };
  playing = true;
  current = src;
  src.start();
}

function logLine(role, text) {
  const p = document.createElement('p');
  p.className = role;
  p.textContent = `${role === 'buyer' ? scenario.persona.name : 'Tú'}: ${text}`;
  $('log').append(p);
  $('log').scrollTop = $('log').scrollHeight;
}

function flushSeller() {
  const text = takeSellerTurn(session);
  if (text) logLine('seller', text);
  return text;
}

function playClip(clip, button) {
  turnToken += 1;
  clearTimeout(replyTimer);
  flushSeller();
  addBuyerLine(session, clip.line);
  logLine('buyer', clip.line);
  play(clip.id);
  button?.classList.add('played');
}

async function replyNow() {
  clearTimeout(replyTimer);
  if (!scenario || playing) return;
  const seller = flushSeller();
  if (!seller) return;
  const token = (turnToken += 1);
  setStatus('El comprador está pensando…');
  try {
    const out = await api('/demo/reply', {
      persona: scenario.persona,
      language: scenario.language,
      voice: scenario.voice,
      history: historyBeforeLastSeller(session),
      seller_text: seller,
    });
    if (token !== turnToken) return;
    await decode(`reply-${token}`, out.audio_b64);
    if (token !== turnToken) return;
    addBuyerLine(session, out.line);
    logLine('buyer', out.line);
    play(`reply-${token}`);
    setStatus('');
  } catch (err) {
    setStatus(err.message, true);
  }
}

function onSellerText(text) {
  if (!scenario) return;
  if (playing || Date.now() - playedUntil < ECHO_GUARD_MS) return;
  addSellerText(session, text);
  clearTimeout(replyTimer);
  if ($('free-toggle').checked && hasPendingSeller(session)) {
    replyTimer = setTimeout(() => void replyNow(), REPLY_QUIET_MS);
  }
}

function renderScenario() {
  const { persona, opening, objections } = scenario;
  $('demo-title').textContent = persona.name;
  $('persona').replaceChildren();
  const strong = document.createElement('strong');
  strong.textContent = `${persona.role} · ${persona.company}`;
  const bg = document.createElement('span');
  bg.textContent = persona.background;
  $('persona').append(strong, bg);
  $('clips').replaceChildren();
  for (const clip of [opening, ...objections]) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'demo-clip';
    const label = document.createElement('span');
    label.textContent = clip.label;
    const line = document.createElement('small');
    line.textContent = clip.line;
    b.append(label, line);
    b.addEventListener('click', () => playClip(clip, b));
    $('clips').append(b);
  }
  $('demo-form').hidden = true;
  $('demo-live').hidden = false;
  setStatus('');
}

async function load(next) {
  scenario = next;
  session = createDemoSession();
  buffers.clear();
  await Promise.all([scenario.opening, ...scenario.objections].map((c) => decode(c.id, c.audio_b64)));
  renderScenario();
}

$('demo-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('btn-prepare').disabled = true;
  setStatus('Generando al comprador y sus voces… (unos 15 s)');
  try {
    const next = await api('/demo/scenario', {
      offer: $('f-offer').value.trim(),
      niche: $('f-niche').value.trim(),
      company: $('f-company').value.trim() || null,
      prospect_name: $('f-name').value.trim() || null,
      language: $('f-lang').value,
      voice: $('f-voice').value.trim() || null,
    });
    try { localStorage.setItem(SCENARIO_KEY, JSON.stringify(next)); } catch { /* too large: prepare again next time */ }
    await load(next);
  } catch (err) {
    setStatus(err.message, true);
  } finally {
    $('btn-prepare').disabled = false;
  }
});

$('btn-listen').addEventListener('click', () => desktop()?.shell?.command('listen'));
$('btn-stop-audio').addEventListener('click', () => {
  turnToken += 1;
  clearTimeout(replyTimer);
  stopAudio();
});
$('btn-reply-now').addEventListener('click', () => void replyNow());
$('btn-reset').addEventListener('click', () => {
  stopAudio();
  scenario = null;
  try { localStorage.removeItem(SCENARIO_KEY); } catch { /* ignore */ }
  $('demo-live').hidden = true;
  $('demo-form').hidden = false;
  $('log').replaceChildren();
  $('demo-title').textContent = 'Prepara al comprador';
});

desktop()?.demo?.onSellerText(onSellerText);

try {
  const saved = localStorage.getItem(SCENARIO_KEY);
  if (saved) void load(JSON.parse(saved)).catch(() => setStatus('El escenario guardado no se pudo cargar; prepara uno nuevo.', true));
} catch { /* no saved scenario */ }

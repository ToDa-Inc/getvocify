#!/usr/bin/env node
// Synthesizes the Vocify launch-reel music bed and SFX kit on an exact 128 BPM grid.
// No network, no paid calls: everything is deterministic DSP (seeded noise).
//
//   node scripts/synth-audio.mjs            -> assets/audio/music-bed.wav + assets/audio/sfx/*.wav
//
// Arrangement (beats, P = 0.46875 s, 106 beats = 49.69 s): 0-8 intro · 8-37.5 groove (capture) with
// build 32-37.5 · 37.5-38 gap · 38-54 drop (automate) · 54-76 groove (assist) · 76-89.5 drop B (learn) ·
// 89.5-90 dip · 90-94 flurry · 94 final hit, tail to the end.
import { writeFileSync, mkdirSync } from 'node:fs';

const SR = 48000, P = 60 / 128, LEN = 106 * 60 / 128, N = Math.round(SR * LEN);
const OUT = 'assets/audio';
mkdirSync(`${OUT}/sfx`, { recursive: true });

// ---------- primitives ----------
let seed = 1337;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
const noise = () => rnd() * 2 - 1;
const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);
const B = (n) => n * P;
const clamp = (x, a, b) => Math.min(b, Math.max(a, x));

function svf() { // TPT state-variable filter
  let ic1 = 0, ic2 = 0;
  return (x, fc, q, mode = 'lp') => {
    fc = clamp(fc, 20, SR * 0.45);
    const g = Math.tan(Math.PI * fc / SR), k = 1 / q;
    const a1 = 1 / (1 + g * (g + k)), a2 = g * a1, a3 = g * a2;
    const v3 = x - ic2, v1 = a1 * ic1 + a2 * v3, v2 = ic2 + a2 * ic1 + a3 * v3;
    ic1 = 2 * v1 - ic1; ic2 = 2 * v2 - ic2;
    return mode === 'lp' ? v2 : mode === 'bp' ? v1 : x - k * v1 - v2;
  };
}
const blep = (t, dt) => {
  if (t < dt) { t /= dt; return t + t - t * t - 1; }
  if (t > 1 - dt) { t = (t - 1) / dt; return t * t + t + t + 1; }
  return 0;
};
function sawOsc(freq, phase0 = rnd()) {
  let ph = phase0;
  return () => { const dt = freq / SR; const s = 2 * ph - 1 - blep(ph, dt); ph += dt; if (ph >= 1) ph -= 1; return s; };
}

function buf(n = N) { return [new Float32Array(n), new Float32Array(n)]; }
const add = (dst, i, l, r) => { if (i >= 0 && i < dst[0].length) { dst[0][i] += l; dst[1][i] += r; } };

// ---------- bus buffers ----------
const dry = buf(), send = buf();

// sidechain: duck everything melodic after each kick
const kicks = [];
let scArr = null; // built once, after every groove kick is placed
const scAt = (t) => {
  if (!scArr) {
    scArr = new Float32Array(N).fill(1);
    for (const k of kicks) { const i0 = Math.round(k * SR); for (let i = 0; i < 0.35 * SR && i0 + i < N; i++) scArr[i0 + i] = Math.min(scArr[i0 + i], 1 - 0.72 * Math.exp(-(i / SR) / 0.085)); }
  }
  return scArr[Math.min(N - 1, Math.max(0, Math.round(t * SR)))];
};

// ---------- instruments ----------
function kick(t0, gain = 0.95, target = dry) {
  kicks.push(t0);
  const n = Math.round(0.5 * SR), i0 = Math.round(t0 * SR);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const f = 44 + 120 * Math.exp(-t / 0.032) + 40 * Math.exp(-t / 0.006);
    ph += 2 * Math.PI * f / SR;
    const amp = Math.exp(-t / 0.3) * Math.min(1, t / 0.0015);
    let s = Math.sin(ph) * amp + noise() * Math.exp(-t / 0.0025) * 0.35;
    s = Math.tanh(s * 1.6) * gain;
    add(target, i0 + i, s, s);
  }
}
function clap(t0, gain = 0.4, tone = 1300) {
  const f = svf(), n = Math.round(0.35 * SR), i0 = Math.round(t0 * SR);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    let env = 0;
    for (const o of [0, 0.011, 0.023]) if (t >= o) env = Math.max(env, Math.exp(-(t - o) / 0.0045));
    env = Math.max(env, 0.55 * Math.exp(-t / 0.11) * (t > 0.023 ? 1 : 0));
    const s = f(noise(), tone, 0.9, 'bp') * env * gain * 2.2;
    add(dry, i0 + i, s * 0.95, s);
    add(send, i0 + i, s * 0.35, s * 0.35);
  }
}
function hat(t0, decay = 0.035, gain = 0.12, pan = 0.15) {
  const f = svf(), n = Math.round((decay * 6) * SR), i0 = Math.round(t0 * SR);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const s = f(noise(), 8200, 0.7, 'hp') * Math.exp(-t / decay) * gain;
    add(dry, i0 + i, s * (1 - pan), s * (1 + pan));
  }
}
function tone(t0, dur, midi, { gain = 0.2, cutoff = 2000, cutEnv = 0, cutDecay = 0.1, q = 0.9, att = 0.003, rel = 0.08, voices = 1, detune = 0, sc = true, rev = 0.2, pan = 0, sub = 0, width = 0.6 } = {}) {
  const n = Math.round((dur + rel) * SR), i0 = Math.round(t0 * SR);
  const oscs = [], pans = [];
  for (let v = 0; v < voices; v++) {
    const c = voices === 1 ? 0 : (v / (voices - 1) - 0.5) * 2 * detune;
    oscs.push(sawOsc(mtof(midi) * Math.pow(2, c / 1200)));
    pans.push(voices === 1 ? pan : (v / (voices - 1) - 0.5) * 2 * width);
  }
  const fl = svf(), fr = svf();
  let sph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR, abs = t0 + t;
    const env = Math.min(1, t / att) * (t > dur ? Math.exp(-(t - dur) / (rel / 3)) : 1);
    let l = 0, r = 0;
    for (let v = 0; v < voices; v++) { const s = oscs[v](); l += s * (1 - pans[v]); r += s * (1 + pans[v]); }
    l /= voices; r /= voices;
    if (sub) { sph += 2 * Math.PI * mtof(midi - 12) / SR; const s = Math.sin(sph) * sub; l += s; r += s; }
    const fc = cutoff + cutEnv * Math.exp(-t / cutDecay);
    l = fl(l, fc, q); r = fr(r, fc, q);
    const g = env * gain * (sc ? scAt(abs) : 1);
    add(dry, i0 + i, l * g, r * g);
    if (rev) add(send, i0 + i, l * g * rev, r * g * rev);
  }
}
function riser(t0, t1, gain = 0.22) {
  const f = svf(), n = Math.round((t1 - t0) * SR), i0 = Math.round(t0 * SR);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const u = i / n, fc = 300 * Math.pow(9000 / 300, u * u);
    const s = f(noise(), fc, 2.5, 'bp') * u * u * gain * 2;
    ph += 2 * Math.PI * (180 + 900 * u * u) / SR;
    const w = Math.sin(ph) * u * u * gain * 0.25;
    add(dry, i0 + i, s + w, s * 0.8 + w);
    add(send, i0 + i, s * 0.3, s * 0.3);
  }
}
function boom(t0, gain = 0.9, dur = 1.8) {
  const n = Math.round(dur * SR), i0 = Math.round(t0 * SR);
  let ph = 0;
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    ph += 2 * Math.PI * (32 + 50 * Math.exp(-t / 0.15)) / SR;
    const s = Math.sin(ph) * Math.exp(-t / (dur / 3.2)) * gain * Math.min(1, t / 0.002);
    add(dry, i0 + i, s, s);
  }
}
function crash(t0, gain = 0.16, dur = 1.6) {
  const f = svf(), n = Math.round(dur * SR), i0 = Math.round(t0 * SR);
  for (let i = 0; i < n; i++) {
    const t = i / SR;
    const s = f(noise(), 5200, 0.6, 'hp') * Math.exp(-t / (dur / 4)) * gain;
    add(dry, i0 + i, s, s * 0.9);
    add(send, i0 + i, s * 0.4, s * 0.4);
  }
}

// ---------- harmony (F minor: i VI III VII) ----------
const PROG = [
  { bass: 41, chord: [56, 60, 65] }, // Fm
  { bass: 37, chord: [56, 61, 65] }, // Db
  { bass: 44, chord: [56, 60, 63] }, // Ab
  { bass: 39, chord: [55, 58, 63] }, // Eb
];
const chordAt = (beat) => PROG[Math.floor(beat / 4) % 4];
const inRange = (b, a, z) => b >= a && b < z;

// ---------- arrangement ----------
// Sections (beats). The visual beat sheet in index.html uses the same numbers.
const S = { intro: 8, capEnd: 37.5, drop1: [38, 54], groove2: [54, 76], drop2: [76, 89.5], flurry: [90, 94], hit: 94, end: 106 };
const GAPS = [[37.5, 38, 0], [89.5, 90, 0.12]];
const inGap = (b) => GAPS.some(([a, z]) => inRange(b, a, z));
const isDrop = (b) => inRange(b, ...S.drop1) || inRange(b, ...S.drop2) || inRange(b, ...S.flurry);

// intro pad (two bars) and quiet pads under the capture chapter
for (let bar = 0; bar < 10; bar++) {
  const c = PROG[bar % 4], t0 = B(bar * 4);
  for (const m of c.chord) tone(t0, B(4) - 0.05, m, { gain: bar < 2 ? 0.11 : 0.06, cutoff: 650 + Math.min(bar, 6) * 220, att: 0.25, rel: 0.5, voices: 3, detune: 12, sc: bar >= 2, rev: 0.6 });
}
// soft intro ticks (16ths) 0-4, then 8ths 4-8 climbing into the first kick
for (let s = 0; s < 16; s++) hat(B(s / 4), 0.012, s % 4 === 0 ? 0.05 : 0.025, 0.4);
for (let b = 4; b < 8; b += 0.5) hat(B(b), 0.02, 0.04 + (b - 4) * 0.012, b % 1 ? 0.3 : -0.3);
riser(B(6), B(8), 0.12);

const kickOn = (b) => inRange(b, S.intro, S.capEnd) || inRange(b, S.drop1[0], S.drop2[1]) || inRange(b, ...S.flurry);
for (let b = 0; b < S.hit; b++) {
  if (kickOn(b)) kick(B(b));
  if (inRange(b, 36, 37.5)) kick(B(b + 0.5), 0.7); // build
}
for (let b = S.intro; b < S.hit; b++) {
  if (inGap(b)) continue;
  const drop = isDrop(b);
  hat(B(b + 0.5), 0.06, drop ? 0.13 : 0.1, -0.15);
  if (b >= 12) for (const q of [0.25, 0.75]) hat(B(b + q), 0.018, 0.05, 0.3);
  if (b >= 16 && b % 2 === 1 && !inRange(b, 36, 38)) clap(B(b), drop ? 0.42 : 0.34);
}
// bass: off-beat 8ths in grooves, rolling 16ths in drops
for (let b = S.intro; b < S.hit; b++) {
  if (inGap(b)) continue;
  const c = chordAt(b), drop = isDrop(b);
  for (const q of drop ? [0.25, 0.5, 0.75] : [0.5]) tone(B(b + q), B(0.2), c.bass, { gain: 0.3, cutoff: 260, cutEnv: drop ? 1400 : 700, cutDecay: 0.06, q: 1.1, rel: 0.04, sub: 0.55, rev: 0 });
}
// chords: plucked stabs in grooves (filter opens through the capture chapter), supersaw in drops
for (let b = S.intro; b < S.flurry[0]; b++) {
  if (inGap(b)) continue;
  const c = chordAt(b);
  if (isDrop(b)) {
    if (b % 4 === 0) for (const m of c.chord) tone(B(b), B(4) - 0.03, m, { gain: 0.085, cutoff: 3200, att: 0.01, rel: 0.2, voices: 7, detune: 22, width: 0.85, rev: 0.25 });
    if (b % 4 === 0 && b < 88) for (const m of c.chord) tone(B(b), B(4) - 0.03, m + 12, { gain: 0.04, cutoff: 5000, att: 0.01, rel: 0.2, voices: 5, detune: 18, width: 0.9, rev: 0.3 });
  } else {
    const open = inRange(b, S.intro, 38) ? Math.min(28, b - S.intro) * 75 : 1700;
    for (const m of c.chord) tone(B(b + 0.5), B(0.22), m, { gain: 0.06, cutoff: 900 + open, cutEnv: 2400, cutDecay: 0.07, q: 1.4, rel: 0.12, voices: 3, detune: 10, rev: 0.4 });
  }
}
// lead arp (16ths) in the drops
const ARP = [0, 1, 2, 1, 2, 0, 2, 1];
for (const [a, z, oct] of [[S.drop1[0], S.drop1[1], 12], [S.drop2[0], S.drop2[1], 24]]) {
  for (let s = a * 4; s < z * 4; s++) {
    const b = s / 4, c = chordAt(b);
    tone(B(b), B(0.2), c.chord[ARP[s % 8]] + oct, { gain: 0.045, cutoff: 1800, cutEnv: 3500, cutDecay: 0.05, q: 1.6, rel: 0.1, voices: 2, detune: 6, pan: s % 2 ? 0.35 : -0.35, rev: 0.45 });
  }
}
// flurry: gated chord stutter (16ths, alternating up an octave)
for (let s = S.flurry[0] * 4; s < S.flurry[1] * 4; s++) {
  const b = s / 4, c = PROG[(s >> 2) % 2 ? 1 : 0];
  for (const m of c.chord) tone(B(b), B(0.16), m + (s % 2 ? 12 : 0), { gain: 0.06, cutoff: 4200, att: 0.002, rel: 0.03, voices: 5, detune: 20, width: 0.9, rev: 0.15 });
}
// builds
riser(B(32), B(37.5), 0.24);
for (let s = 0; s < 4; s++) clap(B(34 + s * 0.5), 0.1 + s * 0.02, 1800);
for (let s = 0; s < 6; s++) clap(B(36 + s * 0.25), 0.18 + s * 0.03, 1900);
riser(B(74), B(76), 0.16);
for (let s = 0; s < 8; s++) clap(B(74 + s * 0.25), 0.08 + s * 0.02, 1900);
riser(B(92), B(94), 0.14);
for (let s = 0; s < 8; s++) clap(B(92 + s * 0.25), 0.1 + s * 0.025, 2000);
// impacts
boom(B(8), 0.5, 1.2); crash(B(8), 0.12);
boom(B(38), 0.9); crash(B(38), 0.18);
crash(B(54), 0.12); crash(B(66), 0.1); crash(B(76), 0.14);
boom(B(90), 0.6, 1.0);
// final hit: big Ab-major chord, sub, crash, long tail to the end
boom(B(S.hit), 1.0, 3.2); crash(B(S.hit), 0.2, 3.5); kick(B(S.hit), 0.9);
for (const m of [44, 56, 60, 63, 68, 72]) tone(B(S.hit), LEN - B(S.hit) - 0.6, m, { gain: m < 50 ? 0.14 : 0.06, cutoff: 2600, cutEnv: 2500, cutDecay: 0.8, att: 0.005, rel: 0.5, voices: 7, detune: 16, width: 0.8, sc: false, rev: 0.6 });
// quiet ticking clock under the lockup (8ths)
for (let b = 96; b < 104; b += 0.5) hat(B(b), 0.01, 0.03, b % 1 ? 0.4 : -0.4);

// ---------- reverb (mono-in comb/allpass, decorrelated L/R) ----------
function reverb(input, combs, aps, fb = 0.84, damp = 0.25) {
  const out = new Float32Array(N);
  const cs = combs.map((d) => ({ b: new Float32Array(d), i: 0, f: 0 }));
  const as = aps.map((d) => ({ b: new Float32Array(d), i: 0 }));
  for (let n = 0; n < N; n++) {
    const x = input[n] * 0.4; let y = 0;
    for (const c of cs) { const o = c.b[c.i]; c.f = o * (1 - damp) + c.f * damp; c.b[c.i] = x + c.f * fb; c.i = (c.i + 1) % c.b.length; y += o; }
    for (const a of as) { const o = a.b[a.i]; const v = y + o * 0.5; a.b[a.i] = v; a.i = (a.i + 1) % a.b.length; y = o - v * 0.5; }
    out[n] = y;
  }
  return out;
}
const rl = reverb(send[0], [1687, 1601, 2053, 2251], [556, 441, 341]);
const rr = reverb(send[1], [1723, 1663, 1999, 2297], [579, 460, 353]);

// ---------- master: gaps, fade, saturation, normalize ----------
const gapGain = (t) => {
  const g = (a, z, floor) => (t >= a && t < z ? floor + (1 - floor) * Math.max(0, Math.min(1, (a + 0.006 - t) / 0.006, (t - z + 0.006) / 0.006)) : 1);
  return GAPS.reduce((acc, [a, z, f]) => acc * g(B(a), B(z), f), 1);
};
const L = new Float32Array(N), R = new Float32Array(N);
let peak = 0;
for (let n = 0; n < N; n++) {
  const t = n / SR;
  const fade = Math.min(1, (LEN - t) / 0.35, t / 0.004);
  const g = gapGain(t) * fade;
  L[n] = Math.tanh((dry[0][n] + rl[n] * 0.9) * 1.1) * g;
  R[n] = Math.tanh((dry[1][n] + rr[n] * 0.9) * 1.1) * g;
  peak = Math.max(peak, Math.abs(L[n]), Math.abs(R[n]));
}
const norm = 0.89 / peak;
for (let n = 0; n < N; n++) { L[n] *= norm; R[n] *= norm; }

function writeWav(path, l, r) {
  const n = l.length, data = Buffer.alloc(n * 4);
  for (let i = 0; i < n; i++) {
    data.writeInt16LE(Math.round(clamp(l[i], -1, 1) * 32767), i * 4);
    data.writeInt16LE(Math.round(clamp(r[i], -1, 1) * 32767), i * 4 + 2);
  }
  const h = Buffer.alloc(44);
  h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVE', 8); h.write('fmt ', 12);
  h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(2, 22); h.writeUInt32LE(SR, 24);
  h.writeUInt32LE(SR * 4, 28); h.writeUInt16LE(4, 32); h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(data.length, 40);
  writeFileSync(path, Buffer.concat([h, data]));
}
writeWav(`${OUT}/music-bed.wav`, L, R);
console.log('music-bed.wav', LEN + 's', 'peak norm', norm.toFixed(3));

// ---------- SFX kit ----------
function sfx(name, dur, fn) {
  const n = Math.round(dur * SR), l = new Float32Array(n), r = new Float32Array(n);
  fn(n, l, r);
  let pk = 0; for (let i = 0; i < n; i++) pk = Math.max(pk, Math.abs(l[i]), Math.abs(r[i]));
  const k = pk ? 0.9 / pk : 1;
  for (let i = 0; i < n; i++) { l[i] *= k; r[i] *= k; }
  const f = Math.round(0.004 * SR); for (let i = 0; i < f; i++) { l[n - 1 - i] *= i / f; r[n - 1 - i] *= i / f; }
  writeWav(`${OUT}/sfx/${name}.wav`, l, r);
}
const bell = (freqs, decay, t) => freqs.reduce((s, [f, a]) => s + Math.sin(2 * Math.PI * f * t) * a * Math.exp(-t / (decay * (1 - f / 20000))), 0);

sfx('pop', 0.22, (n, l, r) => { let ph = 0; for (let i = 0; i < n; i++) { const t = i / SR; ph += 2 * Math.PI * (320 + 900 * Math.exp(-t / 0.018)) / SR; const s = Math.sin(ph) * Math.exp(-t / 0.045) * Math.min(1, t / 0.001) + noise() * Math.exp(-t / 0.002) * 0.2; l[i] = r[i] = s; } });
sfx('pop_low', 0.3, (n, l, r) => { let ph = 0; for (let i = 0; i < n; i++) { const t = i / SR; ph += 2 * Math.PI * (160 + 520 * Math.exp(-t / 0.02)) / SR; const s = Math.sin(ph) * Math.exp(-t / 0.07) * Math.min(1, t / 0.001); l[i] = r[i] = s; } });
sfx('click', 0.08, (n, l, r) => { const f = svf(); for (let i = 0; i < n; i++) { const t = i / SR; const s = f(noise(), 3500, 1.2, 'bp') * Math.exp(-t / 0.004) + Math.sin(2 * Math.PI * 2200 * t) * Math.exp(-t / 0.008) * 0.5; l[i] = s; r[i] = s * 0.9; } });
sfx('tick', 0.05, (n, l, r) => { for (let i = 0; i < n; i++) { const t = i / SR; const s = Math.sin(2 * Math.PI * 4200 * t) * Math.exp(-t / 0.006); l[i] = r[i] = s; } });
sfx('typing', 0.7, (n, l, r) => { const f = svf(); let next = 0; const hits = []; while (next < 0.62) { hits.push(next); next += 0.045 + rnd() * 0.05; } for (let i = 0; i < n; i++) { const t = i / SR; let s = 0; for (const h of hits) if (t >= h && t < h + 0.03) s += Math.exp(-(t - h) / 0.004) * (0.6 + 0.4 * Math.sin(h * 999)); const x = f(noise() * s, 2800, 1.5, 'bp'); l[i] = x; r[i] = x * 0.85; } });
sfx('whoosh', 0.55, (n, l, r) => { const fl = svf(), fr = svf(); for (let i = 0; i < n; i++) { const u = i / n; const env = Math.sin(Math.PI * Math.pow(u, 0.7)) ** 2; const fc = 500 * Math.pow(10, Math.sin(Math.PI * u) * 0.9); const x = noise(); l[i] = fl(x, fc, 1.8, 'bp') * env * (1.2 - u); r[i] = fr(x, fc * 1.1, 1.8, 'bp') * env * (0.2 + u); } });
sfx('whoosh_up', 0.35, (n, l, r) => { const f = svf(); let ph = 0; for (let i = 0; i < n; i++) { const u = i / n; ph += 2 * Math.PI * (300 + 2200 * u * u) / SR; const env = Math.min(1, u * 4) * (1 - u) ** 0.5; const s = (f(noise(), 600 + 6000 * u, 2, 'bp') * 0.8 + Math.sin(ph) * 0.25) * env; l[i] = r[i] = s; } });
sfx('ding', 1.0, (n, l, r) => { for (let i = 0; i < n; i++) { const t = i / SR; const s = bell([[1318.5, 1], [2637, 0.35], [1975.5, 0.5]], 0.35, t) * Math.min(1, t / 0.002); l[i] = s; r[i] = s * 0.95; } });
sfx('success', 1.1, (n, l, r) => { for (let i = 0; i < n; i++) { const t = i / SR; let s = bell([[1046.5, 1], [2093, 0.3]], 0.3, t); if (t > 0.085) s += bell([[1568, 1], [3136, 0.3]], 0.4, t - 0.085); l[i] = s * 0.9; r[i] = s; } });
sfx('sub_boom', 2.2, (n, l, r) => { let ph = 0; const f = svf(); for (let i = 0; i < n; i++) { const t = i / SR; ph += 2 * Math.PI * (30 + 60 * Math.exp(-t / 0.12)) / SR; const s = Math.sin(ph) * Math.exp(-t / 0.6) + f(noise(), 180, 0.8) * Math.exp(-t / 0.05) * 0.8; l[i] = r[i] = Math.tanh(s * 1.4); } });
sfx('glitch', 0.32, (n, l, r) => { let ph = 0, hold = 0, held = 0; for (let i = 0; i < n; i++) { const t = i / SR; const seg = Math.floor(t / 0.028); const f = [880, 220, 1760, 440, 3520, 660, 110, 1320, 2640, 330, 990, 4400][seg % 12]; ph += f / SR; if (hold-- <= 0) { held = (ph % 1 < 0.5 ? 1 : -1) * (seg % 3 ? 0.7 : 1) + noise() * 0.25; hold = 6 + (seg % 4) * 5; } l[i] = held * (seg % 2 ? 1 : 0.6); r[i] = held * (seg % 2 ? 0.6 : 1); } });
sfx('shimmer', 1.4, (n, l, r) => { for (let i = 0; i < n; i++) { const t = i / SR; const env = Math.min(1, t / 0.5) * Math.exp(-Math.max(0, t - 0.5) / 0.35); let s = 0; [2093, 2637, 3136, 4186, 5274].forEach((f, k) => { s += Math.sin(2 * Math.PI * f * t + k) * (0.5 + 0.5 * Math.sin(t * (9 + k * 3))) / (k + 1.5); }); l[i] = s * env; r[i] = s * env * (0.8 + 0.2 * Math.sin(t * 7)); } });
sfx('swish', 0.25, (n, l, r) => { const f = svf(); for (let i = 0; i < n; i++) { const u = i / n; const env = Math.sin(Math.PI * u) ** 2; const s = f(noise(), 2500 + 5000 * u, 1.2, 'bp') * env; l[i] = s * (1 - u); r[i] = s * u; } });
sfx('final_hit', 3.0, (n, l, r) => { let ph = 0; const f = svf(); for (let i = 0; i < n; i++) { const t = i / SR; ph += 2 * Math.PI * (38 + 90 * Math.exp(-t / 0.05)) / SR; let s = Math.sin(ph) * Math.exp(-t / 0.7) * 0.9 + f(noise(), 4500, 0.5, 'hp') * Math.exp(-t / 0.5) * 0.25 + bell([[880, 0.4], [1318.5, 0.3], [1760, 0.2], [2637, 0.12]], 1.1, t); l[i] = Math.tanh(s); r[i] = Math.tanh(s * 0.97); } });
console.log('sfx kit written');

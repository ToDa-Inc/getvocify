import { interpolate, spring, Easing } from 'remotion';

// ─── Spring presets ─────────────────────────────────────────────────────────

// Instant snap pop — for titles and punchy reveals
export const snapIn = (frame: number, fps: number, delay = 0) =>
  spring({ frame: frame - delay, fps, config: { stiffness: 320, damping: 12, mass: 0.45 }, from: 0, to: 1 });

// Slightly bouncier card entry
export const springIn = (frame: number, fps: number, delay = 0) =>
  spring({ frame: frame - delay, fps, config: { stiffness: 200, damping: 14, mass: 0.6 }, from: 0, to: 1 });

// Smooth glide — for subtitles, secondary elements
export const glideIn = (frame: number, fps: number, delay = 0) =>
  spring({ frame: frame - delay, fps, config: { stiffness: 130, damping: 20, mass: 0.8 }, from: 0, to: 1 });

// ─── Transform helpers ───────────────────────────────────────────────────────

export const snapUp = (frame: number, fps: number, delay = 0, dist = 60) => {
  const p = snapIn(frame, fps, delay);
  return `translateY(${(1 - p) * dist}px)`;
};

export const snapLeft = (frame: number, fps: number, delay = 0, dist = 100) => {
  const p = snapIn(frame, fps, delay);
  return `translateX(${-(1 - p) * dist}px)`;
};

export const snapRight = (frame: number, fps: number, delay = 0, dist = 100) => {
  const p = snapIn(frame, fps, delay);
  return `translateX(${(1 - p) * dist}px)`;
};

// ─── Slam entry — rotation + scale + translate combo ─────────────────────────

export const slamEntry = (frame: number, fps: number, delay = 0) => {
  const p = spring({ frame: frame - delay, fps, config: { stiffness: 280, damping: 10, mass: 0.5 }, from: 0, to: 1 });
  const opacity = Math.min(1, p * 3);
  const scale = 0.6 + 0.4 * p;
  const rotate = (1 - p) * 6;
  const ty = (1 - p) * 50;
  return {
    opacity,
    transform: `rotate(${rotate}deg) scale(${scale}) translateY(${ty}px)`,
  };
};

// ─── Fade ────────────────────────────────────────────────────────────────────

export const fadeIn = (frame: number, delay = 0, duration = 8) =>
  interpolate(frame, [delay, delay + duration], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.quad),
  });

// ─── Word-by-word reveal ──────────────────────────────────────────────────────

// Returns index of last visible word (0-based). Use to conditionally render words.
export const wordRevealCount = (frame: number, fps: number, delay = 0, wordsPerSecond = 8) => {
  const elapsed = Math.max(0, frame - delay);
  return Math.floor(elapsed / (fps / wordsPerSecond));
};

// ─── Counter animation ────────────────────────────────────────────────────────

export const countUp = (frame: number, fps: number, target: number, duration = 1.5, delay = 0) =>
  Math.floor(
    interpolate(frame, [delay, delay + duration * fps], [0, target], {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.out(Easing.cubic),
    })
  );

// ─── Animated waveform bar height ────────────────────────────────────────────

export const waveBar = (frame: number, index: number, base: number, amplitude = 0.7) =>
  base + Math.sin(frame * 0.22 + index * 0.75) * base * amplitude;

// ─── Pulse scale (for recording dot etc.) ────────────────────────────────────

export const pulseScale = (frame: number, period = 30, min = 0.9, max = 1.1) =>
  min + (max - min) * (0.5 + 0.5 * Math.sin((frame / period) * Math.PI * 2));

// ─── Stagger card entry ───────────────────────────────────────────────────────

export const cardEntry = (frame: number, fps: number, delay = 0) => {
  const p = springIn(frame, fps, delay);
  const opacity = Math.min(1, p * 2.5);
  const scale = 0.82 + 0.18 * p;
  const ty = (1 - p) * 44;
  return { opacity, transform: `translateY(${ty}px) scale(${scale})` };
};

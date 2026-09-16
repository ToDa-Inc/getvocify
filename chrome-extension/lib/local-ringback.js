const DEFAULT_SRC =
  (globalThis.chrome?.runtime?.getURL?.('call-ringback.wav')) || 'call-ringback.wav';

export function startLocalRingback({
  src = DEFAULT_SRC,
  maxMs = 35_000,
  createAudio = (url) => new Audio(url),
} = {}) {
  const audio = createAudio(src);
  audio.loop = true;
  const played = audio.play();
  if (played && typeof played.catch === 'function') {
    void played.catch((err) => {
      console.warn('vocify ringback play failed', err);
    });
  }
  let stopped = false;
  const stop = () => {
    if (stopped) return;
    stopped = true;
    clearTimeout(timer);
    audio.pause();
    audio.removeAttribute('src');
    audio.load();
  };
  const timer = setTimeout(stop, maxMs);
  return stop;
}

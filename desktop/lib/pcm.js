export function floatTo16BitPcm(float32) {
  const samples = float32 || new Float32Array(0);
  const int16 = new Int16Array(samples.length);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return int16.buffer;
}

export function downsampleTo16k(float32, inputRate) {
  const rate = Number(inputRate) || 16000;
  if (rate === 16000) return float32;
  const ratio = rate / 16000;
  const length = Math.max(0, Math.floor(float32.length / ratio));
  const out = new Float32Array(length);
  for (let i = 0; i < length; i++) {
    out[i] = float32[Math.floor(i * ratio)] || 0;
  }
  return out;
}

export function pcmFromAudioBuffer(float32, inputRate) {
  return floatTo16BitPcm(downsampleTo16k(float32, inputRate));
}

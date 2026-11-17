/**
 * Base64 of an audio frame, written straight into one reused buffer. The live socket sends 20 frames a second (100 ms
 * of each side): building the string a character at a time for `btoa` made ~135 MB of garbage a minute on the page,
 * for the whole call, and kept its garbage collector busy under everything else. The same text as `btoa`.
 */
const ALPHABET = new TextEncoder().encode("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/");
const PAD = 61; // "="
// The output is ASCII only, which every single-byte decoder reads the same.
const ascii = new TextDecoder("latin1");
let out = new Uint8Array(0);

export function base64Of(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  const n = bytes.length;
  const size = Math.ceil(n / 3) * 4;
  if (out.length < size) out = new Uint8Array(size);
  let o = 0;
  let i = 0;
  for (; i + 2 < n; i += 3) {
    const v = (bytes[i] << 16) | (bytes[i + 1] << 8) | bytes[i + 2];
    out[o++] = ALPHABET[v >> 18];
    out[o++] = ALPHABET[(v >> 12) & 63];
    out[o++] = ALPHABET[(v >> 6) & 63];
    out[o++] = ALPHABET[v & 63];
  }
  if (i < n) {
    const two = i + 1 < n;
    const v = (bytes[i] << 16) | ((two ? bytes[i + 1] : 0) << 8);
    out[o++] = ALPHABET[v >> 18];
    out[o++] = ALPHABET[(v >> 12) & 63];
    out[o++] = two ? ALPHABET[(v >> 6) & 63] : PAD;
    out[o++] = PAD;
  }
  return ascii.decode(out.subarray(0, o));
}

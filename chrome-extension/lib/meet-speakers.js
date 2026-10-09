/**
 * Who Google Meet shows speaking, read from the Meet page. The Vocify Mac app puts these
 * names on the other side's sentences while it records the call.
 *
 * Meet marks a speaking tile with obfuscated classes; these are the ones two independent
 * readers use today (Vexa gmeet-speakers.ts, Seashell's Meet reader). Meet can rename them
 * in any release: then nobody reads as speaking and lines stay "Them", never a wrong name.
 */
export const SPEAKING_CLASSES = ['Oaajhc', 'HX2H7', 'wEsLMd', 'OgVli'];
export const MEET_SPEAKERS = 'MEET_SPEAKERS';

const JUNK_NAME = /^Google Participant \(|spaces\/|devices\//;

/** A call's address looks like meet.google.com/abc-defg-hij. */
export function isMeetCallPath(pathname) {
  return /^\/[a-z]{3}-[a-z]{4}-[a-z]{3}$/.test(pathname || '');
}

/** The tile's display name, or null for placeholders and device rows. */
export function cleanName(text) {
  const name = (text || '').replace(/\s+/g, ' ').trim();
  if (name.length < 2 || name.length > 80 || JUNK_NAME.test(name)) return null;
  return name;
}

/** Every participant tile on the page: { name, self, speaking }. */
export function readMeetTiles(root) {
  const tiles = [];
  const seen = new Set();
  for (const el of root.querySelectorAll('[data-participant-id]')) {
    const id = el.getAttribute('data-participant-id');
    if (!id || seen.has(id)) continue;
    seen.add(id);
    tiles.push({
      name: cleanName(el.querySelector('span.notranslate')?.textContent),
      // Meet marks your own tile with data-self-name; your voice is the mic side, not "Them".
      self: el.hasAttribute('data-self-name') || Boolean(el.querySelector('[data-self-name]')),
      speaking: SPEAKING_CLASSES.some((cls) => el.classList.contains(cls) || Boolean(el.querySelector(`.${cls}`))),
    });
  }
  return tiles;
}

/** The other people shown speaking right now, sorted, each once. */
export function speakingNames(tiles) {
  return [...new Set(tiles.filter((t) => t.speaking && !t.self && t.name).map((t) => t.name))].sort();
}

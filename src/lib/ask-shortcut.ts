type KeyChord = {
  key?: string;
  metaKey: boolean;
  ctrlKey: boolean;
  shiftKey: boolean;
  altKey: boolean;
  isComposing?: boolean;
};

/** Cmd+K / Ctrl+K opens Ask. Only the plain chord: Shift or Alt belong to something else, and autofill fires keydowns with no key. */
export function isAskShortcut(e: KeyChord): boolean {
  if (e.isComposing || e.shiftKey || e.altKey) return false;
  return e.key?.toLowerCase() === "k" && (e.metaKey || e.ctrlKey);
}

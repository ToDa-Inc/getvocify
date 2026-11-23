/**
 * Who is on the rep's side in a meeting besides the rep: a colleague in the call is heard with the other side's audio, but
 * what they say is the seller's side speaking. Their lines go to the live help as the rep's side (never answered, never
 * read as the prospect's question or objection) and are drawn on the rep's side (2026-11-23: Toni asked the prospect
 * «¿crees que esta es la llamada con más peso?» and the island showed the rep an answer to it).
 *
 * The team is the company's members and the colleagues invited to the meeting. A voice is a colleague by the name it has:
 * the one the meeting app showed, or the one the rep gave it, so naming a voice as a colleague moves it to the rep's side.
 *
 * No `@/` imports: this file runs under node --test.
 */

export type TeamSide = {
  /** Changes when the team or the guests change: what is built from it is built again. */
  key: string;
  /** The team's names, as offered to name a voice with (the rep left out). */
  names: string[];
  /** Whether a voice called `name` is one of the team. */
  has(name: string | null | undefined): boolean;
};

/** Lower case, no accents or punctuation: «TONI», «Toni» and «Tóni» are one name. */
function words(name: string): string[] {
  return name
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .split(" ")
    .filter(Boolean);
}

/**
 * The rep's side from the team's names and the meeting's guests. A voice is a colleague when its name is a colleague's
 * whole name, or the start of it («Toni Mora» for «Toni Mora Botella»), or their first name alone («TONI» as Meet shows
 * it); a colleague whose profile has only a first name («Toni») is any voice with that first name («Toni Mora»). A first
 * name a guest shares is not enough, and a guest's own name is always the guest's.
 */
export function teamSide(team: readonly string[], /** The meeting's people from outside the company. */ guests: readonly string[] = [], rep: string | null = null): TeamSide {
  const repKey = rep ? words(rep).join(" ") : "";
  const names: string[] = [];
  const seen = new Set<string>();
  for (const raw of team) {
    const name = raw.trim();
    const key = words(name).join(" ");
    if (!key || seen.has(key)) continue;
    seen.add(key);
    if (key !== repKey) names.push(name);
  }
  const members = [...seen].map((key) => key.split(" "));
  const guestFirsts = new Set(guests.map((guest) => words(guest)[0]).filter((first): first is string => Boolean(first)));
  const guestNames = new Set(guests.map((guest) => words(guest).join(" ")).filter(Boolean));
  const memo = new Map<string, boolean>();
  const has = (name: string | null | undefined): boolean => {
    const said = name ? words(name) : [];
    if (!said.length) return false;
    const key = said.join(" ");
    const known = memo.get(key);
    if (known !== undefined) return known;
    const yes =
      !guestNames.has(key) &&
      members.some((member) =>
        said.length > 1 && said.length <= member.length
          ? said.every((word, i) => member[i] === word)
          : // A first name: said alone, or all a one-word profile has. Never one a guest shares.
            member[0] === said[0] && (said.length === 1 || member.length === 1) && !guestFirsts.has(said[0]),
      );
    memo.set(key, yes);
    return yes;
  };
  return { key: `${[...seen].sort().join("|")}#${[...guestNames].sort().join("|")}`, names, has };
}

/** Nobody on the rep's side but the rep: what a recording has before the team is known. */
export const NO_TEAM: TeamSide = { key: "", names: [], has: () => false };

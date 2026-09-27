export const HOY_LANES = ["calls", "meetings"] as const;
export type HoyLane = (typeof HOY_LANES)[number];

export function visibleLanes(salesRole: string | null | undefined, permission: string): HoyLane[] {
  if (permission === "owner" || permission === "admin") return ["calls", "meetings"];
  if (salesRole === "sdr") return ["calls"];
  if (salesRole === "ae") return ["meetings"];
  return ["calls", "meetings"];
}

export function motionsFor(salesRole: string | null | undefined, permission: string): string[] {
  if (permission === "owner" || permission === "admin" || (salesRole !== "sdr" && salesRole !== "ae")) {
    return ["discovery", "qualification", "closing"];
  }
  if (salesRole === "sdr") return ["discovery", "qualification"];
  return ["closing"];
}

export function splitByLane<T extends { lane?: string | null }>(items: T[]): { calls: T[]; meetings: T[] } {
  const calls: T[] = [];
  const meetings: T[] = [];
  for (const item of items) {
    if (item.lane === "meetings") meetings.push(item);
    else if (item.lane === "calls") calls.push(item);
    else calls.push(item);
  }
  return { calls, meetings };
}

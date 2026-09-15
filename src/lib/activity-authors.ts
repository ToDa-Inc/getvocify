export type ActivityAuthor = {
  userId: string;
  label: string;
  email?: string;
};

export function canViewCompanyActivity(role?: string | null): boolean {
  return role === "owner" || role === "admin";
}

export function authorDisplayName(
  fullName?: string | null,
  email?: string | null,
): string {
  const name = (fullName || "").trim();
  if (name) return name;
  const addr = (email || "").trim();
  if (addr) return addr.split("@")[0];
  return "Teammate";
}

export function authorChipLabel(
  authorName?: string | null,
  authorUserId?: string | null,
  currentUserId?: string | null,
): string | null {
  if (authorUserId && currentUserId && authorUserId === currentUserId) {
    return "You";
  }
  return authorName?.trim() || null;
}

export function filterByAuthor<T>(
  items: T[],
  authorUserId: string | null,
  getUserId: (item: T) => string | null | undefined,
): T[] {
  if (!authorUserId) return items;
  return items.filter((item) => getUserId(item) === authorUserId);
}

/** Owners/admins start on Mine only when the author filter is on screen. */
export function shouldShowActivityAuthorFilter(
  canViewCompany: boolean,
  userId?: string | null,
): boolean {
  return Boolean(canViewCompany && userId);
}

export function defaultActivityAuthorId(
  canViewCompany: boolean,
  userId?: string | null,
  teammateCount = 0,
): string | null {
  if (canViewCompany && userId && teammateCount > 1) return userId;
  return null;
}

export function activityFilterChips(
  authors: ActivityAuthor[],
  currentUserId?: string | null,
): { id: string | null; label: string }[] {
  const chips: { id: string | null; label: string }[] = [];
  if (currentUserId) chips.push({ id: currentUserId, label: "Mine" });
  chips.push({ id: null, label: "All" });
  for (const author of authors) {
    if (author.userId === currentUserId) continue;
    chips.push({ id: author.userId, label: author.label });
  }
  return chips;
}

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

export function canViewCompanyActivity(user) {
  const role = user?.company?.role || user?.company_role;
  return role === 'owner' || role === 'admin';
}

export function authorDisplayName(fullName, email) {
  const name = String(fullName || '').trim();
  if (name) return name;
  const addr = String(email || '').trim();
  if (addr) return addr.split('@')[0];
  return 'Teammate';
}

export function authorChipLabel(item, currentUserId) {
  if (!item || typeof item !== 'object') return null;
  const uid = item.authorUserId || item.author_user_id || item.userId || item.user_id;
  const name = item.authorName || item.author_name;
  if (uid && currentUserId && String(uid) === String(currentUserId)) return 'You';
  return name ? String(name) : null;
}

export function activityItemAuthorId(item) {
  if (!item) return '';
  if (item.kind === 'call') {
    return String(item.recording?.author_user_id || item.recording?.authorUserId || '');
  }
  if (item.kind === 'outbound') {
    return String(
      item.outbound?.authorUserId
      || item.outbound?.author_user_id
      || item.outbound?.userId
      || '',
    );
  }
  return String(item.memo?.userId || item.memo?.user_id || '');
}

export function filterActivityByAuthor(items, authorUserId) {
  if (!authorUserId) return items || [];
  return (items || []).filter((item) => activityItemAuthorId(item) === String(authorUserId));
}

export function authorsFromMembers(members) {
  return (members || [])
    .filter((member) => member && (member.status || 'active') === 'active')
    .map((member) => ({
      userId: String(member.userId || member.user_id || ''),
      label: authorDisplayName(member.fullName || member.full_name, member.email),
    }))
    .filter((author) => author.userId);
}

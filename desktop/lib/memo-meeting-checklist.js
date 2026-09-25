/** Pure show/hide and row model for memo review checklist (no invented steps). */

export function memoMeetingChecklistView(checklist, copy) {
  if (!checklist || typeof checklist !== 'object') return null;
  const applicable = Number(checklist.applicable);
  if (!Number.isFinite(applicable) || applicable <= 0) return null;

  const observedRaw = Number(checklist.observed);
  const observed = Number.isFinite(observedRaw) ? observedRaw : 0;
  const progress = String(copy.progressTemplate ?? '')
    .replace('{met}', String(observed))
    .replace('{applicable}', String(applicable));

  const doneLabel = String(copy.doneLabel ?? '');
  const steps = [];
  for (const step of Array.isArray(checklist.steps) ? checklist.steps : []) {
    const label = String(step?.label ?? '').trim();
    if (!label) continue;
    if (step?.status === 'met') {
      steps.push({ kind: 'met', label, doneLabel });
    } else {
      steps.push({ kind: 'pending', label });
    }
  }

  return { progress, steps };
}

/**
 * Compact Apple-like month grid for task / CRM dates.
 */

const WEEKDAYS = ['S', 'M', 'T', 'W', 'T', 'F', 'S'];

function isoDay(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function parseIso(value) {
  const s = String(value || '').slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
  const d = new Date(`${s}T12:00:00`);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function calendarMonth({ year, month, selected = '', today = '' } = {}) {
  const first = new Date(year, month, 1);
  const startWeekday = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const selectedIso = String(selected || '').slice(0, 10);
  const todayIso = String(today || '').slice(0, 10);
  const cells = [];
  for (let i = 0; i < startWeekday; i += 1) {
    const d = new Date(year, month, i - startWeekday + 1);
    cells.push({ iso: isoDay(d), day: d.getDate(), inMonth: false, selected: false, today: isoDay(d) === todayIso });
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const d = new Date(year, month, day);
    const iso = isoDay(d);
    cells.push({
      iso,
      day,
      inMonth: true,
      selected: iso === selectedIso,
      today: iso === todayIso,
    });
  }
  while (cells.length % 7 !== 0) {
    const extra = cells.length - startWeekday - daysInMonth + 1;
    const d = new Date(year, month + 1, extra);
    cells.push({ iso: isoDay(d), day: d.getDate(), inMonth: false, selected: false, today: isoDay(d) === todayIso });
  }
  const weeks = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  const label = first.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });
  return { year, month, label, weekdays: WEEKDAYS, weeks };
}

export function shiftCalendarMonth(year, month, delta) {
  const d = new Date(year, month + delta, 1);
  return { year: d.getFullYear(), month: d.getMonth() };
}

export function calendarFromIso(iso, { today = '' } = {}) {
  const d = parseIso(iso) || parseIso(today) || new Date();
  return calendarMonth({
    year: d.getFullYear(),
    month: d.getMonth(),
    selected: iso,
    today,
  });
}

import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { calendarMonth, shiftCalendarMonth } from './date-chip.js';

describe('calendarMonth', () => {
  it('builds a Sunday-start grid with today and selected marked', () => {
    const cal = calendarMonth({
      year: 2026,
      month: 7,
      selected: '2026-08-20',
      today: '2026-08-18',
    });
    assert.equal(cal.label, 'August 2026');
    assert.deepEqual(cal.weekdays, ['S', 'M', 'T', 'W', 'T', 'F', 'S']);
    const days = cal.weeks.flat();
    const selected = days.find((d) => d.iso === '2026-08-20');
    const today = days.find((d) => d.iso === '2026-08-18');
    assert.equal(selected.inMonth, true);
    assert.equal(selected.selected, true);
    assert.equal(today.today, true);
    assert.equal(days[0].iso, '2026-07-26');
    assert.equal(days[0].inMonth, false);
  });
});

describe('shiftCalendarMonth', () => {
  it('wraps from January to December of the previous year', () => {
    assert.deepEqual(shiftCalendarMonth(2026, 0, -1), { year: 2025, month: 11 });
  });
});

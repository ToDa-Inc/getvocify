import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { formatCopilotSayThisLine } from './copilot-say-this.js';

describe('formatCopilotSayThisLine', () => {
  it('collapses whitespace and caps at 90 characters', () => {
    assert.equal(formatCopilotSayThisLine('  hola\nmundo  '), 'hola mundo');
    const long = 'a'.repeat(100);
    assert.equal(formatCopilotSayThisLine(long).length, 90);
    assert.ok(formatCopilotSayThisLine(long).endsWith('…'));
  });
});

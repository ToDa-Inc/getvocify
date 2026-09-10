import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  activityItemAuthorId,
  authorChipLabel,
  authorsFromMembers,
  canViewCompanyActivity,
  filterActivityByAuthor,
} from './activity-authors.js';

describe('activity authors', () => {
  it('lets owners and admins see company activity', () => {
    assert.equal(canViewCompanyActivity({ company: { role: 'owner' } }), true);
    assert.equal(canViewCompanyActivity({ company: { role: 'admin' } }), true);
    assert.equal(canViewCompanyActivity({ company: { role: 'member' } }), false);
  });

  it('labels the current user as You', () => {
    assert.equal(authorChipLabel({ authorName: 'Ada', userId: 'u1' }, 'u1'), 'You');
    assert.equal(authorChipLabel({ author_name: 'Ada', author_user_id: 'u2' }, 'u1'), 'Ada');
  });

  it('filters merged activity by author', () => {
    const items = [
      { kind: 'call', recording: { author_user_id: 'u1' } },
      { kind: 'memo', memo: { userId: 'u2' } },
    ];
    assert.equal(activityItemAuthorId(items[1]), 'u2');
    assert.equal(filterActivityByAuthor(items, 'u2').length, 1);
    assert.equal(filterActivityByAuthor(items, null).length, 2);
  });

  it('maps company members to filter chips', () => {
    const authors = authorsFromMembers([
      { user_id: 'u1', full_name: 'Ada', email: 'ada@acme.com', status: 'active' },
      { userId: 'u2', full_name: '', email: 'bob@acme.com', status: 'active' },
    ]);
    assert.deepEqual(authors.map((a) => a.label), ['Ada', 'bob']);
  });
});

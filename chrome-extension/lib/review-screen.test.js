import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { isAuthFailure } from './auth-session.js';
import { resolveReviewPresentation, sameMemoId } from './review-screen.js';

describe('sameMemoId', () => {
  it('treats uuid string and the same value as equal', () => {
    const id = '6f1c2a8e-1111-2222-3333-444444444444';
    assert.equal(sameMemoId(id, id), true);
    assert.equal(sameMemoId(id, String(id)), true);
  });

  it('does not match a missing id', () => {
    assert.equal(sameMemoId('memo-1', null), false);
    assert.equal(sameMemoId(null, 'memo-1'), false);
    assert.equal(sameMemoId('', 'memo-1'), false);
  });
});

describe('resolveReviewPresentation', () => {
  it('keeps transcribing/extracting on the processing screen instead of a blank review', () => {
    assert.equal(resolveReviewPresentation({ memo: { status: 'transcribing' } }).mode, 'processing');
    assert.equal(resolveReviewPresentation({ memo: { status: 'extracting' } }).mode, 'processing');
    assert.equal(resolveReviewPresentation({ memo: { status: 'uploading' } }).mode, 'processing');
  });

  it('shows transcript review while pending_transcript', () => {
    assert.equal(
      resolveReviewPresentation({ memo: { status: 'pending_transcript' } }).mode,
      'pending_transcript',
    );
  });

  it('shows proposed changes (and transcript) while pending_review', () => {
    assert.equal(
      resolveReviewPresentation({ memo: { status: 'pending_review' } }).mode,
      'pending_review',
    );
  });

  it('goes to login on 401 / missing authorization instead of an empty review', () => {
    const err = {
      status: 401,
      data: { detail: 'Missing authorization header. Please sign in to get an access token.' },
    };
    assert.equal(
      resolveReviewPresentation({ error: err, isAuthFailure }).mode,
      'login',
    );
  });

  it('shows a visible error for other getMemo failures', () => {
    const out = resolveReviewPresentation({
      error: { status: 500, message: 'Server error' },
      isAuthFailure,
    });
    assert.equal(out.mode, 'error');
    assert.match(out.message, /Server error/);
  });

  it('shows transcript review with an error banner when extraction failed', () => {
    const out = resolveReviewPresentation({
      memo: { status: 'failed', errorMessage: 'Speechmatics timed out' },
    });
    assert.equal(out.mode, 'pending_transcript');
    assert.equal(out.failed, true);
    assert.match(out.message, /timed out/);
  });

  it('does not leave an unknown/empty memo as a blank confirm screen', () => {
    const out = resolveReviewPresentation({ memo: {} });
    assert.equal(out.mode, 'error');
  });
});

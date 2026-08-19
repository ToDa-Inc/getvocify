import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { isAuthFailure } from './auth-session.js';
import {
  dealMatchSubtitle,
  dealPickerVisibility,
  dealTargetCardCopy,
  resolveReviewPresentation,
  sameMemoId,
  shouldReloadReviewPreview,
} from './review-screen.js';

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

describe('shouldReloadReviewPreview', () => {
  it('reloads when the HubSpot record changes even if the memo is the same', () => {
    assert.equal(
      shouldReloadReviewPreview({
        memoId: 'm1',
        loadedMemoId: 'm1',
        pageKey: 'deal:B',
        loadedPageKey: 'deal:A',
      }),
      true,
    );
  });

  it('reloads when the deal is closed and the page is no longer a record', () => {
    assert.equal(
      shouldReloadReviewPreview({
        memoId: 'm1',
        loadedMemoId: 'm1',
        pageKey: null,
        loadedPageKey: 'deal:A',
      }),
      true,
    );
  });

  it('keeps the preview only for the same memo on the same record', () => {
    assert.equal(
      shouldReloadReviewPreview({
        memoId: 'm1',
        loadedMemoId: 'm1',
        pageKey: 'deal:A',
        loadedPageKey: 'deal:A',
      }),
      false,
    );
  });

  it('does not follow a tab change once Review & sync is locked', () => {
    assert.equal(
      shouldReloadReviewPreview({
        memoId: 'm1',
        loadedMemoId: 'm1',
        pageKey: 'deal:B',
        loadedPageKey: 'contact:C',
        sessionLocked: true,
      }),
      false,
    );
  });

  it('still reloads when a new memo starts even if a session was locked', () => {
    assert.equal(
      shouldReloadReviewPreview({
        memoId: 'm2',
        loadedMemoId: 'm1',
        pageKey: 'deal:B',
        loadedPageKey: 'contact:C',
        sessionLocked: true,
      }),
      true,
    );
  });
});

describe('deal picker', () => {
  it('stays collapsed so linked deals are not listed next to contact-only', () => {
    const ui = dealPickerVisibility({
      pickerOpen: false,
      needsConfirm: false,
      hasMatches: true,
      hasSelectedContact: true,
    });
    assert.equal(ui.showPicker, false);
    assert.equal(ui.showCard, true);
    assert.equal(ui.showContactOnlyRow, false);
  });

  it('opens a compact picker with contact-only plus linked deals', () => {
    const ui = dealPickerVisibility({
      pickerOpen: true,
      needsConfirm: false,
      hasMatches: true,
      hasSelectedContact: true,
    });
    assert.equal(ui.showPicker, true);
    assert.equal(ui.showCard, false);
    assert.equal(ui.showContactOnlyRow, true);
    assert.equal(ui.showSearch, false);
  });

  it('forces the picker open when a deal must be confirmed', () => {
    const ui = dealPickerVisibility({
      pickerOpen: false,
      needsConfirm: true,
      hasMatches: false,
      hasSelectedContact: false,
    });
    assert.equal(ui.showPicker, true);
    assert.equal(ui.showSearch, true);
    assert.equal(ui.showContactOnlyRow, false);
  });

  it('labels contact-only as the selected target, not a competing card', () => {
    const copy = dealTargetCardCopy({ skipDeal: true });
    assert.equal(copy.title, 'Contact only');
    assert.equal(copy.reason, 'No deal will be updated');
  });

  it('hides matcher jargon on linked deals', () => {
    assert.equal(dealMatchSubtitle('Linked to matched contact'), '');
    assert.equal(dealMatchSubtitle('Company association: Holcim'), 'Company association: Holcim');
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

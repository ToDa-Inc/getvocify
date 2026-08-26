import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { isAuthFailure } from './auth-session.js';
import {
  canPaintInsightsFromMemo,
  dealCardWhilePreviewLoads,
  dealMatchSubtitle,
  dealPickerVisibility,
  dealTargetCardCopy,
  resolveReviewPresentation,
  sameMemoId,
  shouldReloadReviewPreview,
  planReviewSessionLock,
  shouldShowReviewOpeningSpinner,
  slimReviewMemo,
  approveCtaLabel,
  approveCtaTitle,
  confirmTranscriptAlreadyFinished,
  confirmTranscriptErrorStatus,
  memoForReviewPresentation,
  reviewMemoIfCurrent,
  shouldWriteCallNote,
  shouldPollMemo,
  transcriptPolishSettled,
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

describe('reviewMemoIfCurrent', () => {
  it('keeps the payload only when it belongs to the open memo', () => {
    const memo = { id: 'm-esteban', extraction: { summary: 'Golf' } };
    assert.equal(reviewMemoIfCurrent(memo, 'm-esteban'), memo);
    assert.equal(reviewMemoIfCurrent(memo, 'm-david'), null);
    assert.equal(reviewMemoIfCurrent(null, 'm-david'), null);
  });
});

describe('shouldWriteCallNote', () => {
  it('replaces the note when switching to a different call', () => {
    assert.equal(
      shouldWriteCallNote({
        memoId: 'm-david',
        paintedMemoId: 'm-esteban',
        existingText: 'Esteban was playing golf',
        incomingText: 'David asked for a follow-up',
      }),
      true,
    );
  });

  it('replaces leftover text when the previous call is no longer the painted memo', () => {
    assert.equal(
      shouldWriteCallNote({
        memoId: 'm-david',
        paintedMemoId: null,
        existingText: 'Esteban was playing golf',
        incomingText: 'David asked for a follow-up',
      }),
      true,
    );
  });

  it('fills an empty box on first paint of this call', () => {
    assert.equal(
      shouldWriteCallNote({
        memoId: 'm-david',
        paintedMemoId: null,
        existingText: '',
        incomingText: 'David asked for a follow-up',
      }),
      true,
    );
  });

  it('keeps in-progress edits while the HubSpot tab or preview refreshes', () => {
    assert.equal(
      shouldWriteCallNote({
        memoId: 'm-david',
        paintedMemoId: 'm-david',
        existingText: 'David — user edited this',
        incomingText: 'David asked for a follow-up',
      }),
      false,
    );
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

describe('planReviewSessionLock', () => {
  it('locks immediately on the inbox so a later focused HubSpot row cannot steal the process', () => {
    const plan = planReviewSessionLock({ alreadyLocked: false, liveContext: null });
    assert.equal(plan.shouldLock, true);
    assert.deepEqual(plan.context, {});
  });

  it('does not adopt a later contact or deal once the process is locked', () => {
    const plan = planReviewSessionLock({
      alreadyLocked: true,
      liveContext: { objectType: 'deal', recordId: 'D-focused' },
    });
    assert.equal(plan.shouldLock, false);
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
  it('keeps transcribing/extracting/pending_transcript on the processing screen', () => {
    assert.equal(resolveReviewPresentation({ memo: { status: 'transcribing' } }).mode, 'processing');
    assert.equal(resolveReviewPresentation({ memo: { status: 'extracting' } }).mode, 'processing');
    assert.equal(resolveReviewPresentation({ memo: { status: 'uploading' } }).mode, 'processing');
    assert.equal(
      resolveReviewPresentation({ memo: { status: 'pending_transcript' } }).mode,
      'processing',
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

  it('shows a failed extraction banner instead of transcript review', () => {
    const out = resolveReviewPresentation({
      memo: { status: 'failed', errorMessage: 'Speechmatics timed out' },
    });
    assert.equal(out.mode, 'failed');
    assert.match(out.message, /timed out/);
  });

  it('does not leave an unknown/empty memo as a blank confirm screen', () => {
    const out = resolveReviewPresentation({ memo: {} });
    assert.equal(out.mode, 'error');
  });
});

describe('shouldShowReviewOpeningSpinner', () => {
  it('skips the extra Opening review screen once we already waited on processing', () => {
    assert.equal(shouldShowReviewOpeningSpinner({ fromProcessing: true, memoId: 'm1' }), false);
  });

  it('skips it when the memo payload is already in hand', () => {
    assert.equal(shouldShowReviewOpeningSpinner({ hasMemoPayload: true, memoId: 'm1' }), false);
  });

  it('skips it when the review body is already on screen', () => {
    assert.equal(shouldShowReviewOpeningSpinner({ reviewBodyVisible: true, memoId: 'm1' }), false);
  });

  it('never parks on Opening review when we already know which memo to show', () => {
    assert.equal(shouldShowReviewOpeningSpinner({ memoId: 'm1' }), false);
    assert.equal(shouldShowReviewOpeningSpinner({ memoId: null }), false);
  });
});

describe('dealCardWhilePreviewLoads', () => {
  it('never uses Loading... — HubSpot page deal name or the empty-deal copy', () => {
    assert.deepEqual(
      dealCardWhilePreviewLoads({ pageType: 'deal', pageDealName: 'ACME Renewal' }),
      { title: 'ACME Renewal', reason: 'This HubSpot deal', pending: false },
    );
    const fallback = dealCardWhilePreviewLoads({ pageType: 'contact' });
    assert.equal(fallback.title, 'No deal selected');
    assert.equal(fallback.pending, true);
    assert.doesNotMatch(fallback.title, /loading/i);
  });
});

describe('canPaintInsightsFromMemo', () => {
  it('is true when extraction already has the note or next steps', () => {
    assert.equal(canPaintInsightsFromMemo({ extraction: { summary: 'Budget confirmed' } }), true);
    assert.equal(canPaintInsightsFromMemo({ extraction: { nextSteps: ['Send proposal'] } }), true);
    assert.equal(canPaintInsightsFromMemo({ extraction: {} }), false);
    assert.equal(canPaintInsightsFromMemo(null), false);
  });
});

describe('slimReviewMemo', () => {
  it('keeps review-paint fields without requiring another getMemo', () => {
    const slim = slimReviewMemo({
      id: 'm1',
      status: 'pending_review',
      extraction: { summary: 'Hi' },
      transcript: 'S1: hello',
      hubspot_contact_id: 'C1',
      extra: 'drop me',
    });
    assert.equal(slim.id, 'm1');
    assert.equal(slim.status, 'pending_review');
    assert.equal(slim.extraction.summary, 'Hi');
    assert.equal(slim.hubspotContactId, 'C1');
    assert.equal(slim.extra, undefined);
  });
});

describe('approveCtaLabel', () => {
  it('names the object, not the record, so the button can stay centered', () => {
    assert.equal(approveCtaLabel({ hasDeal: true, hasContact: true }), 'Update deal');
    assert.equal(approveCtaLabel({ skipDeal: true, hasContact: true }), 'Update contact');
    assert.equal(approveCtaLabel({ isNewDeal: true, hasContact: true }), 'Create deal');
    assert.equal(approveCtaLabel({}), 'Update CRM');
  });
});

describe('approveCtaTitle', () => {
  it('keeps the record name on hover', () => {
    assert.equal(approveCtaTitle({ dealName: 'Turco Española' }), 'Turco Española');
    assert.equal(
      approveCtaTitle({ skipDeal: true, contactName: 'Rafael Vilaplana Dura' }),
      'Rafael Vilaplana Dura',
    );
  });
});

describe('confirmTranscriptAlreadyFinished', () => {
  it('treats a second Extract as done when the memo already left transcript review', () => {
    assert.equal(confirmTranscriptAlreadyFinished('pending_review'), true);
    assert.equal(confirmTranscriptAlreadyFinished('extracting'), true);
    assert.equal(confirmTranscriptAlreadyFinished('pending_transcript'), false);
    assert.equal(confirmTranscriptAlreadyFinished('failed'), false);
  });
});

describe('confirmTranscriptErrorStatus', () => {
  it('reads the live status from the 400 when Extract is clicked twice', () => {
    assert.equal(
      confirmTranscriptErrorStatus({
        status: 400,
        data: { detail: 'Memo is not awaiting transcript review. Status: pending_review' },
      }),
      'pending_review',
    );
  });
});

describe('memoForReviewPresentation', () => {
  it('does not keep showing transcript review from a stale cache after extract', () => {
    const cached = { id: 'm1', status: 'pending_transcript', extraction: {} };
    const fetched = { id: 'm1', status: 'pending_review', extraction: { summary: 'Done' } };
    assert.equal(memoForReviewPresentation({ cached, fetched }).status, 'pending_review');
    assert.equal(
      resolveReviewPresentation({ memo: memoForReviewPresentation({ cached, fetched }) }).mode,
      'pending_review',
    );
  });
});

describe('shouldPollMemo', () => {
  it('keeps polling pending_review until polish lands after extract', () => {
    const extracting = { status: 'extracting' };
    assert.equal(shouldPollMemo(extracting), true);
    const pending = {
      status: 'pending_review',
      processedAt: '2026-08-21T13:10:57.000Z',
      pipelineMeta: { stages: [{ name: 'extract', at: '2026-08-21T13:10:57.000Z' }] },
    };
    assert.equal(shouldPollMemo(pending, Date.parse('2026-08-21T13:11:05.000Z')), true);
    const polished = {
      ...pending,
      pipelineMeta: {
        stages: [
          { name: 'extract', at: '2026-08-21T13:10:57.000Z' },
          { name: 'sanitize', at: '2026-08-21T13:11:03.000Z' },
        ],
      },
    };
    assert.equal(transcriptPolishSettled(polished), true);
    assert.equal(shouldPollMemo(polished, Date.parse('2026-08-21T13:11:05.000Z')), false);
  });
});

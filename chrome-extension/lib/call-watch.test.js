import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { decideCallWatchAction, panelOpenState } from './call-watch.js';

describe('decideCallWatchAction', () => {
  it('does not hijack the UI when landing on a contact with an in-flight transcript', () => {
    const decision = decideCallWatchAction({
      status: 'transcribing',
      memoId: 'memo-stuck',
      baselineMemoId: undefined,
      ignoredIds: new Set(),
    });
    assert.equal(decision.autoOpen, false);
    assert.equal(decision.baselineMemoId, 'memo-stuck');
  });

  it('does not hijack for extracting or pending review memos already on the record', () => {
    for (const status of ['extracting', 'uploading', 'pending_transcript', 'pending_review']) {
      const decision = decideCallWatchAction({
        status,
        memoId: 'memo-old',
        baselineMemoId: undefined,
        ignoredIds: new Set(),
      });
      assert.equal(decision.autoOpen, false, status);
    }
  });

  it('does not auto-open a later memo either — the recordings list is the UI', () => {
    const decision = decideCallWatchAction({
      status: 'pending_transcript',
      memoId: 'memo-new',
      baselineMemoId: null,
      ignoredIds: new Set(),
    });
    assert.equal(decision.autoOpen, false);
  });

  it('primes an empty baseline when the record has no call memo yet', () => {
    const decision = decideCallWatchAction({
      status: 'waiting',
      memoId: null,
      baselineMemoId: undefined,
      ignoredIds: new Set(),
    });
    assert.equal(decision.autoOpen, false);
    assert.equal(decision.baselineMemoId, null);
  });
});

describe('panelOpenState', () => {
  it('drops leftover processing so opening the panel is not the converting screen', () => {
    const next = panelOpenState({
      status: 'processing',
      isRecording: false,
      processingSource: 'hubspot_call',
      currentMemoId: 'memo-1',
    });
    assert.equal(next.status, 'idle');
    assert.equal(next.isRecording, false);
    assert.equal(next.processingSource, null);
  });

  it('keeps a live microphone session', () => {
    const next = panelOpenState({
      status: 'recording',
      isRecording: true,
    });
    assert.equal(next.status, 'recording');
    assert.equal(next.isRecording, true);
  });

  it('keeps review — that is a screen the user already opened', () => {
    const next = panelOpenState({
      status: 'review',
      isRecording: false,
      currentMemoId: 'memo-1',
    });
    assert.equal(next.status, 'review');
  });
});

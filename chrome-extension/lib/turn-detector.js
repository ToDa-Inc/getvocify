/**
 * End-of-turn detector for live copilot.
 * Same rules as src/features/copilot/hooks/useTurnDetector.ts (settle + minWords + EOU).
 * Timers are injectable so Node tests can drive `tick()` without Chrome.
 */

export class TurnDetector {
  constructor({
    settleMs = 900,
    minWords = 6,
    speakerRole = 'unknown',
    now = () => Date.now(),
    onTurn,
    setTimer = null,
    clearTimer = null,
  } = {}) {
    this.settleMs = settleMs;
    this.minWords = minWords;
    this.now = now;
    this.onTurn = onTurn;
    this.speakerRole = speakerRole === 'prospect' || speakerRole === 'rep' ? speakerRole : 'unknown';
    this._setTimer = setTimer;
    this._clearTimer = clearTimer;
    this._enabled = false;
    this._lastSeenFinal = '';
    this._pendingTurn = '';
    this._interim = '';
    this._dueAt = null;
    this._timer = null;
  }

  setEnabled(enabled) {
    this._enabled = Boolean(enabled);
    if (!this._enabled) {
      this._pendingTurn = '';
      this._clearDue();
    }
  }

  reset() {
    this._lastSeenFinal = '';
    this._pendingTurn = '';
    this._interim = '';
    this._clearDue();
  }

  onFinalTranscript(fullFinal) {
    if (!this._enabled) return;
    const next = String(fullFinal || '').trim();
    const prev = this._lastSeenFinal;

    if (next.length < prev.length) {
      this._lastSeenFinal = next;
      this._pendingTurn = '';
      this._clearDue();
      return;
    }

    if (next.length > prev.length) {
      const delta = next.slice(prev.length).trim();
      if (delta) {
        this._pendingTurn = this._pendingTurn
          ? `${this._pendingTurn} ${delta}`.trim()
          : delta;
      }
      this._lastSeenFinal = next;
    }

    this._maybeArm();
  }

  onInterim(interim) {
    if (!this._enabled) return;
    this._interim = String(interim || '');
    this._maybeArm();
  }

  onEndOfUtterance() {
    if (!this._enabled) return;
    this._flush();
  }

  tick(nowMs) {
    if (this._dueAt != null && nowMs >= this._dueAt) {
      this._flush();
    }
  }

  _maybeArm() {
    this._clearDue();
    const pending = this._pendingTurn.trim();
    const interimEmpty = !this._interim.trim();
    if (!pending || !interimEmpty) return;
    this._dueAt = this.now() + this.settleMs;
    if (typeof this._setTimer === 'function') {
      this._timer = this._setTimer(() => this._flush(), this.settleMs);
    }
  }

  _clearDue() {
    this._dueAt = null;
    if (this._timer != null && typeof this._clearTimer === 'function') {
      this._clearTimer(this._timer);
    }
    this._timer = null;
  }

  _flush() {
    const turn = this._pendingTurn.trim();
    this._pendingTurn = '';
    this._clearDue();
    const words = turn.split(/\s+/).filter(Boolean).length;
    if (words < this.minWords) return;
    if (typeof this.onTurn === 'function') {
      this.onTurn(turn, this._lastSeenFinal, {
        speakerRole: this.speakerRole,
        dominantSpeaker: null,
      });
    }
  }
}

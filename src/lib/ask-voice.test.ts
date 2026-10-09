import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  cancelVoice,
  idleVoice,
  permissionDenied,
  startRecording,
  stopRecording,
  transcriptionReady,
} from "./ask-voice.ts";

describe("ask voice", () => {
  it("cancel or silence sends nothing and releases the microphone", () => {
    const recording = startRecording(idleVoice());
    const cancelled = cancelVoice(recording);
    assert.equal(cancelled.sent, false);
    assert.equal(cancelled.mic_released, true);
    assert.equal(cancelled.memo_id, null);
    assert.equal(cancelled.auto_send, false);
    const silent = cancelVoice(recording, { silence: true });
    assert.equal(silent.sent, false);
    assert.equal(silent.mic_released, true);
  });

  it("stopping the recording freezes the timer and then leaves editable text", () => {
    const recording = startRecording(idleVoice());
    assert.equal(recording.timer_running, true);
    const stopped = stopRecording(recording, 1200);
    assert.equal(stopped.composer_state, "transcribing");
    assert.equal(stopped.timer_running, false);
    assert.equal(stopped.elapsed_ms, 1200);
    assert.equal(stopped.sent, false);
    const ready = transcriptionReady(stopped, "¿Qué quedó pendiente con Marina?");
    assert.deepEqual(
      {
        composer_state: ready.composer_state,
        text: ready.text,
        auto_send: ready.auto_send,
      },
      {
        composer_state: "ready_to_send",
        text: "¿Qué quedó pendiente con Marina?",
        auto_send: false,
      },
    );
    assert.equal(ready.memo_id, null);
    assert.equal(ready.sent, false);
  });

  it("a permission error still lets the user type", () => {
    const denied = permissionDenied(startRecording(idleVoice()));
    assert.equal(denied.composer_state, "permission_denied");
    assert.equal(denied.panel_blocked, false);
    assert.equal(denied.mic_released, true);
    assert.equal(denied.sent, false);
    assert.equal(denied.memo_id, null);
  });
});

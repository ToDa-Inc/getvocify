import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  COPILOT_CHANNEL_MODE,
  encodeChannelAudio,
  isCoachableChannel,
  parseChannelLabels,
  applyChannelLabelsToLiveUrl,
} from './stt-channels.js';

describe('isCoachableChannel', () => {
  it('coaches on prospect and unlabeled (tab-only) audio', () => {
    assert.equal(isCoachableChannel('prospect'), true);
    assert.equal(isCoachableChannel(undefined), true);
    assert.equal(isCoachableChannel(null), true);
  });

  it('does not coach on the mic/rep channel', () => {
    assert.equal(isCoachableChannel('rep'), false);
  });
});

describe('parseChannelLabels', () => {
  it('defaults to prospect and rep', () => {
    assert.deepEqual(parseChannelLabels(''), ['prospect', 'rep']);
    assert.deepEqual(parseChannelLabels(null), ['prospect', 'rep']);
  });

  it('allows prospect-only when the mic is unavailable', () => {
    assert.deepEqual(parseChannelLabels('prospect'), ['prospect']);
  });

  it('drops unknown labels and caps at two', () => {
    assert.deepEqual(parseChannelLabels('prospect,rep,noise,rep'), ['prospect', 'rep']);
  });
});

describe('encodeChannelAudio', () => {
  it('emits Speechmatics-shaped AddChannelAudio JSON with base64 PCM', () => {
    const pcm = new Uint8Array([0x01, 0x00, 0xff, 0x7f]).buffer;
    const parsed = JSON.parse(encodeChannelAudio('prospect', pcm));
    assert.equal(parsed.type, 'AddChannelAudio');
    assert.equal(parsed.channel, 'prospect');
    assert.equal(parsed.data, Buffer.from([0x01, 0x00, 0xff, 0x7f]).toString('base64'));
  });
});

describe('COPILOT_CHANNEL_MODE', () => {
  it('is the live STT mode for tab+mic source labeling', () => {
    assert.equal(COPILOT_CHANNEL_MODE, 'copilot_channels');
  });
});

describe('applyChannelLabelsToLiveUrl', () => {
  it('sets copilot_channels and the labels that will be sent as AddChannelAudio', () => {
    const url = applyChannelLabelsToLiveUrl(
      'wss://api.getvocify.com/api/v1/transcription/live?language=multi&mode=copilot',
      ['prospect']
    );
    const parsed = new URL(url);
    assert.equal(parsed.searchParams.get('mode'), 'copilot_channels');
    assert.equal(parsed.searchParams.get('channel_labels'), 'prospect');
  });
});

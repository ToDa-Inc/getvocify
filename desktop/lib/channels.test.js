import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  applyChannelLabelsToLiveUrl,
  encodeChannelAudio,
  liveTranscriptionUrl,
  parseChannelLabels,
} from './channels.js';

describe('channels', () => {
  it('defaults to prospect + rep', () => {
    assert.deepEqual(parseChannelLabels(''), ['prospect', 'rep']);
  });

  it('encodes AddChannelAudio JSON', () => {
    const pcm = new Uint8Array([1, 2, 3]).buffer;
    const parsed = JSON.parse(encodeChannelAudio('prospect', pcm));
    assert.equal(parsed.type, 'AddChannelAudio');
    assert.equal(parsed.channel, 'prospect');
    assert.equal(typeof parsed.data, 'string');
  });

  it('sets copilot_channels on the live URL', () => {
    const url = applyChannelLabelsToLiveUrl(
      'wss://api.getvocify.com/api/v1/transcription/live?language=multi',
      ['prospect', 'rep'],
    );
    const parsed = new URL(url);
    assert.equal(parsed.searchParams.get('mode'), 'copilot_channels');
    assert.equal(parsed.searchParams.get('channel_labels'), 'prospect,rep');
  });

  it('builds a WS origin from an API base', () => {
    assert.equal(
      liveTranscriptionUrl('https://api.getvocify.com/api/v1'),
      'wss://api.getvocify.com/api/v1/transcription/live?language=multi',
    );
  });
});

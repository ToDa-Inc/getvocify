import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import {
  backendLabel,
  buildNativeLoopbackPlan,
  feedS16le,
  parsePactlDefaultSink,
  pulseMonitorName,
} from './system-audio.js';

describe('system-audio (anarlog-style loopback)', () => {
  it('turns the default Pulse sink into a .monitor source', () => {
    assert.equal(
      pulseMonitorName('alsa_output.pci-0000_00_1f.3.analog-stereo'),
      'alsa_output.pci-0000_00_1f.3.analog-stereo.monitor',
    );
    assert.equal(pulseMonitorName('sink.monitor'), 'sink.monitor');
    assert.equal(pulseMonitorName(''), null);
  });

  it('parses pactl info for the default sink', () => {
    assert.equal(
      parsePactlDefaultSink('Server Name: pulse\nDefault Sink: alsa_output.usb\nDefault Source: mic\n'),
      'alsa_output.usb',
    );
    assert.equal(parsePactlDefaultSink('no sink here'), null);
  });

  it('prefers PipeWire capture-sink like anarlog, then Pulse monitor, then ffmpeg', () => {
    const pw = buildNativeLoopbackPlan({
      platform: 'linux',
      bins: { pwRecord: '/usr/bin/pw-record' },
    });
    assert.equal(pw.backend, 'pipewire');
    assert.ok(pw.args.includes('{ stream.capture.sink = true }'));

    const pulse = buildNativeLoopbackPlan({
      platform: 'linux',
      bins: { parec: '/usr/bin/parec' },
      defaultSink: 'alsa_output.pci',
    });
    assert.equal(pulse.backend, 'pulse');
    assert.ok(pulse.args.some((a) => a.includes('alsa_output.pci.monitor')));

    const ffmpeg = buildNativeLoopbackPlan({
      platform: 'linux',
      bins: { ffmpeg: '/usr/bin/ffmpeg' },
      defaultSink: 'sink',
    });
    assert.equal(ffmpeg.backend, 'ffmpeg-pulse');
    assert.ok(ffmpeg.args.includes('sink.monitor'));

    assert.equal(buildNativeLoopbackPlan({ platform: 'darwin', bins: { pwRecord: '/usr/bin/pw-record' } }), null);
  });

  it('emits even s16le frames and keeps a leftover odd byte', () => {
    const frames = [];
    let leftover = Buffer.alloc(0);
    leftover = feedS16le(Buffer.from([0x01, 0x02, 0x03]), leftover, (pcm) => frames.push(Buffer.from(pcm)));
    leftover = feedS16le(Buffer.from([0x04, 0x05]), leftover, (pcm) => frames.push(Buffer.from(pcm)));
    assert.deepEqual(frames[0], Buffer.from([0x01, 0x02]));
    assert.deepEqual(frames[1], Buffer.from([0x03, 0x04]));
    assert.deepEqual(leftover, Buffer.from([0x05]));
  });

  it('labels backends for the listen status line', () => {
    assert.match(backendLabel('pipewire'), /PipeWire/i);
    assert.match(backendLabel('chromium'), /Chromium/i);
  });
});

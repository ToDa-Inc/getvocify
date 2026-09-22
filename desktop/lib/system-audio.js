import { spawnSync } from 'node:child_process';
import { backendLabel } from './capture-labels.js';

export { backendLabel };

export function pulseMonitorName(sink) {
  const name = typeof sink === 'string' ? sink.trim() : '';
  if (!name) return null;
  return name.endsWith('.monitor') ? name : `${name}.monitor`;
}

export function parsePactlDefaultSink(text) {
  const match = String(text || '').match(/Default Sink:\s*(\S+)/i);
  return match ? match[1] : null;
}

export function whichBin(name, { spawnSyncFn = spawnSync } = {}) {
  if (!name) return null;
  const result = spawnSyncFn('which', [name], { encoding: 'utf8' });
  if (result.status !== 0) return null;
  const path = String(result.stdout || '').trim();
  return path || null;
}

export function defaultPulseSink({ spawnSyncFn = spawnSync } = {}) {
  const pactl = whichBin('pactl', { spawnSyncFn });
  if (!pactl) return null;
  const direct = spawnSyncFn(pactl, ['get-default-sink'], { encoding: 'utf8' });
  if (direct.status === 0) {
    const sink = String(direct.stdout || '').trim();
    if (sink) return sink;
  }
  const info = spawnSyncFn(pactl, ['info'], { encoding: 'utf8' });
  return parsePactlDefaultSink(String(info.stdout || ''));
}

/**
 * Linux system-audio capture the way Anarlog does it:
 * PipeWire stream.capture.sink, then PulseAudio <default-sink>.monitor.
 * https://github.com/fastrepl/anarlog
 */
export function buildNativeLoopbackPlan({
  platform = process.platform,
  bins = {},
  defaultSink = null,
} = {}) {
  if (platform !== 'linux') return null;

  if (bins.pwRecord) {
    return {
      backend: 'pipewire',
      cmd: bins.pwRecord,
      args: [
        '--rate',
        '16000',
        '--channels',
        '1',
        '--format',
        's16',
        '--properties',
        '{ stream.capture.sink = true }',
        '-t',
        'raw',
        '-',
      ],
      sampleRate: 16000,
    };
  }

  const monitor = pulseMonitorName(defaultSink) || (bins.ffmpeg || bins.parec ? 'default.monitor' : null);

  if (bins.parec && monitor) {
    return {
      backend: 'pulse',
      cmd: bins.parec,
      args: ['--rate=16000', '--channels=1', '--format=s16le', '--raw', `--device=${monitor}`],
      sampleRate: 16000,
    };
  }

  if (bins.ffmpeg && monitor) {
    return {
      backend: 'ffmpeg-pulse',
      cmd: bins.ffmpeg,
      args: [
        '-hide_banner',
        '-loglevel',
        'error',
        '-f',
        'pulse',
        '-i',
        monitor,
        '-ac',
        '1',
        '-ar',
        '16000',
        '-f',
        's16le',
        'pipe:1',
      ],
      sampleRate: 16000,
    };
  }

  return null;
}

export function resolveNativeLoopbackPlan({
  platform = process.platform,
  spawnSyncFn = spawnSync,
  defaultSink,
} = {}) {
  const bins = {
    pwRecord: whichBin('pw-record', { spawnSyncFn }),
    parec: whichBin('parec', { spawnSyncFn }),
    ffmpeg: whichBin('ffmpeg', { spawnSyncFn }),
  };
  const sink = defaultSink === undefined ? defaultPulseSink({ spawnSyncFn }) : defaultSink;
  return buildNativeLoopbackPlan({ platform, bins, defaultSink: sink });
}

export function feedS16le(chunk, leftover, onFrame) {
  const buf = Buffer.concat([leftover || Buffer.alloc(0), Buffer.from(chunk || [])]);
  const even = buf.length - (buf.length % 2);
  if (even > 0 && typeof onFrame === 'function') onFrame(buf.subarray(0, even));
  return even < buf.length ? buf.subarray(even) : Buffer.alloc(0);
}

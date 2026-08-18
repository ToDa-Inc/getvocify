export function backendLabel(backend) {
  switch (backend) {
    case 'pipewire':
      return 'PipeWire loopback';
    case 'pulse':
      return 'PulseAudio monitor';
    case 'ffmpeg-pulse':
      return 'FFmpeg Pulse monitor';
    case 'chromium':
      return 'Chromium loopback';
    default:
      return 'system audio';
  }
}

export const PERMISSION = {
  microphone: 'microphone',
  systemAudio: 'systemAudio',
};

export function normalizeAccessStatus(raw) {
  const value = String(raw || '').toLowerCase();
  if (value === 'granted' || value === 'authorized') return 'authorized';
  if (value === 'denied' || value === 'restricted') return 'denied';
  return 'never_requested';
}

export function listenPermissionGate({ platform, microphone, systemAudio } = {}) {
  if (platform && platform !== 'darwin') return { ok: true };
  if (microphone !== 'authorized') return { ok: false, reason: 'no_mic' };
  if (systemAudio !== 'authorized') return { ok: false, reason: 'no_system_audio' };
  return { ok: true };
}

export function permissionAction(status, { deniedOpensSettings = true } = {}) {
  if (status === 'authorized') return 'none';
  if (status === 'denied' && deniedOpensSettings) return 'open_settings';
  return 'request';
}

export function settingsAnchor(type) {
  return type === PERMISSION.microphone ? 'Privacy_Microphone' : 'Privacy_ScreenCapture';
}

export function settingsDeepLinks(type) {
  const anchor = settingsAnchor(type);
  return [
    `x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?${anchor}`,
    `x-apple.systempreferences:com.apple.preference.security?${anchor}`,
  ];
}

export function permissionCopy(type) {
  if (type === PERMISSION.microphone) {
    return {
      enableLabel: 'Enable microphone',
      enabledLabel: 'Microphone is on',
      enableBody: 'Vocify records your voice as You on the call.',
      enabledBody: 'Your microphone is ready.',
    };
  }
  return {
    enableLabel: 'Enable system audio',
    enabledLabel: 'System audio is on',
    enableBody:
      'macOS lists this under Screen & System Audio Recording so Vocify can hear Zoom, Meet, and Teams as Them. Vocify does not capture your screen.',
    enabledBody: 'Meeting playback is ready.',
  };
}

export const TAP_DEVICE_NAME = 'vocify-audio-tap';

export function isTapDevice(name) {
  return String(name || '').includes(TAP_DEVICE_NAME);
}

export function pickMicConstraints(devices = [], preferredId) {
  const inputs = (Array.isArray(devices) ? devices : []).filter((device) => {
    const kind = device?.kind;
    if (kind && kind !== 'audioinput') return false;
    return !isTapDevice(device?.label || device?.name);
  });
  const preferred = preferredId && inputs.find((device) => device.deviceId === preferredId);
  const chosen = preferred || inputs[0];
  if (!chosen?.deviceId || chosen.deviceId === 'default') {
    return { audio: true, video: false };
  }
  return { audio: { deviceId: { exact: chosen.deviceId } }, video: false };
}

/**
 * Keyboard command policy. The shortcut opens the side panel.
 * It must not start or stop a memo recording.
 */

export function actionsForCommand(command) {
  if (command === 'toggle-recording') {
    return { openUi: true, toggleRecording: false };
  }
  return { openUi: false, toggleRecording: false };
}

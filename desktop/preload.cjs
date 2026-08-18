const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('vocifyDesktop', {
  platform: process.platform,
  systemAudio: {
    start: () => ipcRenderer.invoke('system-audio:start'),
    stop: () => ipcRenderer.invoke('system-audio:stop'),
    onPcm: (cb) => {
      const handler = (_event, data) => {
        const bytes = data instanceof Uint8Array ? data : Buffer.from(data);
        cb(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength));
      };
      ipcRenderer.on('system-audio:pcm', handler);
      return () => ipcRenderer.removeListener('system-audio:pcm', handler);
    },
  },
  shell: {
    setState: (state) => ipcRenderer.send('shell:state', state),
    showOverlay: () => ipcRenderer.invoke('overlay:show'),
    hideOverlay: () => ipcRenderer.invoke('overlay:hide'),
    openExternal: (url) => ipcRenderer.invoke('shell:open-external', url),
    command: (name) => ipcRenderer.send('shell:command', name),
    onCommand: (cb) => {
      const handler = (_event, name) => cb(name);
      ipcRenderer.on('shell:command', handler);
      return () => ipcRenderer.removeListener('shell:command', handler);
    },
    onOverlayState: (cb) => {
      const handler = (_event, state) => cb(state);
      ipcRenderer.on('overlay:state', handler);
      return () => ipcRenderer.removeListener('overlay:state', handler);
    },
  },
});

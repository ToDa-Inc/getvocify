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
});

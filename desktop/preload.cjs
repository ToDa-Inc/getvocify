const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('vocifyDesktop', {
  platform: process.platform,
});

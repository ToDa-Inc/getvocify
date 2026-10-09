(() => {
  const call = (op, args = {}) => {
    const result = window.webkit.messageHandlers.vocify.postMessage({ op, args });
    return result ?? Promise.resolve(undefined);
  };
  const listeners = {
    'system-audio:pcm': new Set(),
    'system-audio:lost': new Set(),
    'shell:command': new Set(),
    'overlay:state': new Set(),
  };
  const on = (channel) => (cb) => { listeners[channel].add(cb); return () => listeners[channel].delete(cb); };
  window.__vocifyEmit = (channel, payload) => {
    const set = listeners[channel];
    if (!set) return;
    const value = channel === 'system-audio:pcm'
      ? Uint8Array.from(atob(payload), (c) => c.charCodeAt(0)).buffer
      : payload;
    set.forEach((cb) => cb(value));
  };
  window.vocifyDesktop = {
    platform: 'darwin',
    systemAudio: {
      start: () => call('system-audio:start'),
      stop: () => call('system-audio:stop'),
      onPcm: on('system-audio:pcm'),
      onLost: on('system-audio:lost'),
    },
    permissions: { status: () => call('permissions:status'), request: (type) => call('permissions:request', { type }), open: (type) => call('permissions:open', { type }) },
    shell: {
      setState: (state) => { call('shell:state', { state }); },
      resize: (size) => call('shell:resize', { size }),
      showOverlay: () => call('overlay:show'),
      hideOverlay: () => call('overlay:hide'),
      openExternal: (url) => call('shell:open-external', { url }),
      command: (name) => { call('shell:command', { name }); },
      onCommand: on('shell:command'),
      onOverlayState: on('overlay:state'),
    },
    saas: { request: (payload) => call('saas:request', { payload }) },
    capture: {
      begin: (payload) => call('capture:begin', { payload }),
      append: (payload) => call('capture:append', { payload }),
      channelAbsent: (payload) => call('capture:channel-absent', { payload }),
      pending: () => call('capture:pending'),
      confirm: (id) => call('capture:confirm', { id }),
      discard: (id) => call('capture:discard', { id }),
    },
  };
})();

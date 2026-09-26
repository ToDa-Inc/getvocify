// Dev-only. Imported automatically by @reticlehq/vite-plugin, so you do not need to import it.
// Self-guards on import.meta.env.DEV, so it is a no-op in a production build.
import { registerCapabilities, registerStore } from '@reticlehq/react';
import { dialerReticleStore } from '@/lib/dialer-reticle-store';

if (import.meta.env.DEV) {
  registerStore('dialer', dialerReticleStore);

  registerCapabilities({
    testids: [],
    signals: ['dialer-phase', 'dialer-contact', 'dialer-call-sid'],
    stores: ['dialer'],
  });
}

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

import { reticle } from '@reticlehq/vite-plugin';

// Vercel injects VITE_API_URL for Production. Force the staging API when this
// branch builds so staging.getvocify.com cannot silently talk to prod.
if (process.env.VERCEL_GIT_COMMIT_REF === "staging") {
  process.env.VITE_API_URL = "https://getvocify-staging.up.railway.app/api/v1";
}

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => ({
  server: {
    host: "::",
    port: 8080,
  },
  plugins: [reticle(),react(), mode === "development" && componentTagger()].filter(Boolean),
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
}));

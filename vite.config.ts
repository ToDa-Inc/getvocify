import { defineConfig } from "vite";
import react from "@vitejs/plugin-react-swc";
import path from "path";
import { componentTagger } from "lovable-tagger";

import { reticle } from '@reticlehq/vite-plugin';

// Production Vercel sets VITE_API_URL to the prod API. On the staging branch
// build, force the staging Railway API so the dashboard cannot hit prod.
const vercelBranch = decodeURIComponent(process.env.VERCEL_GIT_COMMIT_REF ?? "");
if (vercelBranch === "staging") {
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
      "@shared": path.resolve(__dirname, "./shared"),
    },
  },
}));

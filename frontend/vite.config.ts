import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" keeps asset URLs relative so the app works behind Home Assistant ingress.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: { chunkSizeWarningLimit: 1500 },
  server: {
    proxy: { "/api": "http://localhost:8000" },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 39174,
    strictPort: true,
    proxy: {
      "/api": process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:38173"
    }
  },
  preview: {
    host: "0.0.0.0",
    port: 39174,
    strictPort: true,
    allowedHosts: true,
    proxy: {
      "/api": process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:38173"
    }
  }
});

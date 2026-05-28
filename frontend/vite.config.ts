import { defineConfig } from "vite";

export default defineConfig({
  server: {
    port: 5173,
    proxy: {
      "/ws": {
        target: "https://localhost:8340",
        changeOrigin: true,
        ws: true,
        secure: false,
      },
      "/api": {
        target: "https://localhost:8340",
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: "dist",
  },
});

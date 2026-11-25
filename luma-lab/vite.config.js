import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
const target = `http://127.0.0.1:${Number(process.env.LUMA_BACKEND_PORT || 18781)}`;
export default defineConfig({
  plugins: [react()],
  base: process.env.LUMA_HALL_VERSION ? "/luma/" : "/",
  define: {
    __LUMA_HALL_VERSION__: JSON.stringify(process.env.LUMA_HALL_VERSION || ""),
  },
  server: {
    host: "127.0.0.1",
    port: Number(process.env.LUMA_UI_PORT || 5178),
    strictPort: true,
    proxy: {
      "/ws": { target, ws: true },
      "/api": { target },
      "/legacy": { target, rewrite: (p) => p.replace(/^\/legacy/, "") },
    },
  },
});

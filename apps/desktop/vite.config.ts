import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  clearScreen: false,
  server: {
    host: "127.0.0.1",
    port: 1420,
    strictPort: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8765",
        configure: (proxy) => {
          const emitter = proxy as unknown as {
            on: (event: string, handler: (request: { removeHeader: (name: string) => void }) => void) => void;
          };
          emitter.on("proxyReq", (request) => request.removeHeader("origin"));
        },
      },
    },
  },
});

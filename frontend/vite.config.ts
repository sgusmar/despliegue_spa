import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // El frontend llama siempre a /api/*. Aquí lo redirige al Flask local y en
    // Render lo hace la regla de rewrite del static site: mismo prefijo y misma
    // reescritura en los dos sitios, así que no hace falta CORS en ninguno.
    proxy: {
      "/api": {
        target: "http://127.0.0.1:5000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});

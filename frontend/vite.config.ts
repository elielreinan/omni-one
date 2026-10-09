import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base "./" para o pywebview abrir o build direto do disco (file://).
export default defineConfig({
  base: "./",
  plugins: [react()],
});

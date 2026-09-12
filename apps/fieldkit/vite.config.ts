import { defineConfig } from "vite";
import { tanstackStart } from "@tanstack/react-start/plugin/vite";
import viteReact from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { nitro } from "nitro/vite";

// Field Kit — a self-contained public web surface (no auth, no database).
// It builds to a Vercel target via Nitro; dev serves on :5173.
export default defineConfig(({ command, isPreview }) => ({
  server: { port: 5173 },
  preview: { port: 4173 },
  resolve: { tsconfigPaths: true },
  plugins: [
    tailwindcss(),
    tanstackStart(),
    ...(command === "build" || isPreview
      ? [nitro({ preset: "vercel" })]
      : []),
    viteReact(),
  ],
}));

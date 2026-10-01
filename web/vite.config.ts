import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Behind Caddy (Compose) the API is same-origin. When running `npm run dev` directly on a
// developer machine, proxy API and admin calls to the Django dev server instead.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/admin": "http://localhost:8000",
      "/static": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  // Component and logic tests (npm test). Browser journeys are Playwright tests in e2e/.
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    restoreMocks: true,
    unstubGlobals: true,
    coverage: {
      provider: "v8",
      // The client-side rules: API access, formatting, the offline queue, routing and the leave forms.
      // Whole screens are covered by the Playwright journeys instead.
      include: [
        "src/api/**",
        "src/app/format.ts",
        "src/app/offlineQueue.ts",
        "src/app/router.ts",
        "src/features/auth/**",
        "src/features/admin/**",
        "src/features/privacy/**",
        "src/features/me/AccountScreen.tsx",
        "src/features/leave/Receipt.tsx",
        "src/features/leave/RequestForm.tsx",
        "src/features/people/RecordList.tsx",
        "src/features/people/ContactsTab.tsx",
        "src/features/people/BankTab.tsx",
        "src/features/people/HistoryTab.tsx",
        "src/features/reports/**",
      ],
      exclude: ["src/**/*.test.*", "src/test/**"],
      reporter: ["text"],
      thresholds: { lines: 85, statements: 85, functions: 85, branches: 75 },
    },
  },
});

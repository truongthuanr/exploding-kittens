import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "./tests/e2e", timeout: 90_000, workers: 1,
  use: { baseURL: "http://localhost:3000", trace: "retain-on-failure" },
  webServer: [
    { command: `${process.env.BACKEND_PYTHON || "../backend/.venv/bin/python"} -m uvicorn e2e_server:app --app-dir ../backend/tests --host 127.0.0.1 --port 8000`,
      wait: { stderr: /Uvicorn running on/ }, timeout: 30000,
      env: { APP_CORS_ORIGINS: '["http://localhost:3000"]', PYTHONPATH: "../backend" } },
    { command: "npm run start -- --hostname 127.0.0.1 --port 3000", wait: { stdout: /Ready in/ }, timeout: 30000 },
  ],
});

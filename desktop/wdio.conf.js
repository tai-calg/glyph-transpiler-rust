import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const executable = process.platform === "win32" ? "glyph-desktop.exe" : "glyph-desktop";
const appBinaryPath = resolve(here, "src-tauri", "target", "debug", executable);

export const config = {
  runner: "local",
  specs: ["./e2e/**/*.spec.js"],
  maxInstances: 1,
  capabilities: [
    {
      browserName: "tauri",
      "wdio:enforceWebDriverClassic": true,
      "tauri:options": {
        application: appBinaryPath,
      },
      "wdio:tauriServiceOptions": {
        appBinaryPath,
        appArgs: [],
        driverProvider: "embedded",
        embeddedPort: 4445,
      },
    },
  ],
  services: [
    [
      "@wdio/tauri-service",
      {
        appBinaryPath,
        driverProvider: "embedded",
        embeddedPort: 4445,
      },
    ],
  ],
  framework: "mocha",
  reporters: ["spec"],
  logLevel: "info",
  waitforTimeout: 30_000,
  connectionRetryTimeout: 60_000,
  connectionRetryCount: 1,
  mochaOpts: {
    ui: "bdd",
    timeout: 90_000,
  },
};

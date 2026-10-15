// Starts a fresh fake-AI backend for the end-to-end tests (port 8100, empty database).
import { spawn } from "node:child_process";
import { rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(here, "../../backend");
const data = path.resolve(here, "../test-results/e2e-data");
rmSync(data, { recursive: true, force: true });

const python = path.join(backend, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const child = spawn(python, ["-m", "uvicorn", "junior.main:app", "--port", "8100"], {
  cwd: backend,
  stdio: "inherit",
  env: {
    ...process.env,
    FAKE_AI: "true",
    DATA_DIR: data,
    SCHEDULER_ENABLED: "false",
    OPENAI_API_KEY: "",
    // Your real connections must never be used by tests: nothing may be posted for real.
    ARTIFICIAL_ANALYSIS_API_KEY: "",
    META_APP_ID: "",
    META_APP_SECRET: "",
    META_PAGE_ID: "",
    META_PAGE_TOKEN: "",
    META_IG_USER_ID: "",
    LINKEDIN_ACCESS_TOKEN: "",
    LINKEDIN_PERSON_ID: "",
    FRONTEND_ORIGIN: "http://localhost:3100",
  },
});
const stop = () => child.kill();
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
process.on("exit", stop);
child.on("exit", (code) => process.exit(code ?? 0));

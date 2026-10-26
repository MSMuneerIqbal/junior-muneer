// Starts a fresh fake-AI backend for the end-to-end tests (port 8100, empty database).
import { spawn, spawnSync } from "node:child_process";
import { cpSync, rmSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const backend = path.resolve(here, "../../backend");
const data = path.resolve(here, "../test-results/e2e-data");
rmSync(data, { recursive: true, force: true });
const skills = path.join(data, "skills");
cpSync(path.resolve(here, "../../skills"), skills, { recursive: true });
// Code proposals use this tiny throwaway repo, never the developer's source checkout.
const codeRoot = path.join(data, "code-fixture");
mkdirSync(path.join(codeRoot, "backend/junior"), { recursive: true });
mkdirSync(path.join(codeRoot, "backend/tests"), { recursive: true });
writeFileSync(path.join(codeRoot, ".gitignore"), "__pycache__/\n.pytest_cache/\n");
writeFileSync(path.join(codeRoot, "backend/junior/__init__.py"), "");
writeFileSync(path.join(codeRoot, "backend/junior/demo.py"), "def square(n):\n    return n + n\n");
writeFileSync(path.join(codeRoot, "backend/tests/test_demo.py"), "def test_square():\n    from junior.demo import square\n    assert square(3) == 9\n");
writeFileSync(path.join(codeRoot, "backend/pyproject.toml"), '[tool.pytest.ini_options]\npythonpath=["."]\n');
for (const args of [["init", "-q"], ["config", "user.name", "Synthetic test"], ["config", "user.email", "fixture@example.test"], ["add", "."], ["-c", "commit.gpgsign=false", "commit", "-qm", "fixture"]]) {
  const result = spawnSync("git", ["-c", "core.hooksPath=NUL", "-C", codeRoot, ...args], { encoding: "utf8" });
  if (result.status !== 0) throw new Error("Could not create isolated code-proposal fixture");
}

const python = path.join(backend, ".venv", process.platform === "win32" ? "Scripts/python.exe" : "bin/python");
const child = spawn(python, ["-m", "uvicorn", "junior.main:app", "--port", "8100"], {
  cwd: backend,
  stdio: "inherit",
  env: {
    ...process.env,
    FAKE_AI: "true",
    DATA_DIR: data,
    JUNIOR_SKILLS_DIR: skills, // Settings tests never edit the owner's real skills.
    JUNIOR_CODE_ROOT: codeRoot,
    SCHEDULER_ENABLED: "false",
    OPENAI_API_KEY: "",
    // Your real connections must never be used by tests: nothing may be posted for real.
    ARTIFICIAL_ANALYSIS_API_KEY: "",
    META_APP_ID: "",
    GITHUB_TOKEN: "",
    // A pretend WhatsApp for the e2e test (FAKE_AI + WHATSAPP_TOKEN=fake): nothing leaves this PC.
    WHATSAPP_TOKEN: "fake",
    WHATSAPP_PHONE_NUMBER_ID: "100200300",
    WHATSAPP_VERIFY_TOKEN: "e2e-verify",
    WHATSAPP_OWNER_NUMBER: "923001112233",
    // A pretend Gmail for the news email test (FAKE_AI + GMAIL_APP_PASSWORD=fake): nothing leaves this PC.
    GMAIL_ADDRESS: "me@example.com",
    GMAIL_APP_PASSWORD: "fake",
    // A pretend Gemini Live (FAKE_AI + GEMINI_API_KEY=fake): says one line when it hears you.
    GEMINI_API_KEY: "fake",
    DEEPSEEK_API_KEY: "",
    // A pretend Google (FAKE_AI + GOOGLE_CLIENT_ID=fake): approves at once; Docs, Sheets, Calendar in memory.
    GOOGLE_CLIENT_ID: "fake",
    GOOGLE_CLIENT_SECRET: "fake",
    GOOGLE_REDIRECT_URI: "http://127.0.0.1:8100/api/google/callback",
    GITHUB_CLIENT_ID: "fake", // a pretend GitHub for the Connect GitHub test
    GITHUB_AUTH: "",
    GITHUB_USER: "",
    META_APP_SECRET: "e2e-secret", // signs the pretend WhatsApp messages in the e2e test
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

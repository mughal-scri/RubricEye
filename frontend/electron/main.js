const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");
const fs = require("fs");
const crypto = require("crypto");

const BACKEND_PORT = 8765;
let backendProcess = null;

/** Read or generate a persistent local API token (Phase 2). */
function ensureApiToken() {
  if (process.env.RUBRICEYE_API_TOKEN) return process.env.RUBRICEYE_API_TOKEN;
  const dataDir = process.env.RUBRICEYE_DATA_DIR || path.join(require("os").homedir(), "rubriceye_data");
  const tokenFile = path.join(dataDir, ".api_token");
  try {
    if (fs.existsSync(tokenFile)) {
      const existing = fs.readFileSync(tokenFile, "utf-8").trim();
      if (existing) return existing;
    }
  } catch { /* fall through to generate */ }
  const token = crypto.randomBytes(32).toString("base64url");
  fs.mkdirSync(dataDir, { recursive: true });
  fs.writeFileSync(tokenFile, token, { mode: 0o600 });
  console.log(`[RubricEye] API token generated: ${tokenFile}`);
  return token;
}

function startBackend() {
  const backendDir = path.join(__dirname, "..", "..", "backend");
  const python = process.platform === "win32" ? "python" : "python3";
  const venvPython =
    process.platform === "win32"
      ? path.join(backendDir, "venv", "Scripts", "python.exe")
      : path.join(backendDir, "venv", "bin", "python");

  const executable = require("fs").existsSync(venvPython) ? venvPython : python;

  const apiToken = ensureApiToken();

  backendProcess = spawn(
    executable,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    {
      cwd: backendDir,
      env: { ...process.env, RUBRICEYE_API_TOKEN: apiToken },
      stdio: "inherit",
    }
  );
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 900,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  const devUrl = "http://127.0.0.1:5173";
  if (process.env.ELECTRON_START_URL) {
    win.loadURL(process.env.ELECTRON_START_URL);
  } else if (process.env.NODE_ENV === "development") {
    win.loadURL(devUrl);
  } else {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

app.whenReady().then(() => {
  startBackend();
  setTimeout(createWindow, 1500);
});

app.on("window-all-closed", () => {
  if (backendProcess) {
    backendProcess.kill();
  }
  if (process.platform !== "darwin") {
    app.quit();
  }
});

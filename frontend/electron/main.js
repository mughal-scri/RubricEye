const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

const BACKEND_PORT = 8765;
let backendProcess = null;

function startBackend() {
  const backendDir = path.join(__dirname, "..", "..", "backend");
  const python = process.platform === "win32" ? "python" : "python3";
  const venvPython =
    process.platform === "win32"
      ? path.join(backendDir, "venv", "Scripts", "python.exe")
      : path.join(backendDir, "venv", "bin", "python");

  const executable = require("fs").existsSync(venvPython) ? venvPython : python;

  backendProcess = spawn(
    executable,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(BACKEND_PORT)],
    {
      cwd: backendDir,
      env: { ...process.env },
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

const { app, BrowserWindow, ipcMain, dialog } = require("electron");
const fs = require("node:fs/promises");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { ApiClient, backendUrl } = require("./api-client");

async function startDesktop({ visible = true, settingsPath } = {}) {
  await app.whenReady();
  const settingsFile =
    settingsPath || path.join(app.getPath("userData"), "connection.json");
  let settings;
  try {
    settings = JSON.parse(await fs.readFile(settingsFile, "utf8"));
    settings.backend = backendUrl(settings.backend);
  } catch {
    settings = { backend: "http://127.0.0.1:8080" };
  }
  const client = new ApiClient(settings.backend);
  let window;
  const expected = pathToFileURL(path.join(__dirname, "index.html")).href;
  function handle(channel, handler) {
    ipcMain.handle(channel, async (event, ...args) => {
      if (
        event.sender !== window?.webContents ||
        event.senderFrame?.url !== expected
      )
        throw new Error("Untrusted request.");
      return handler(...args);
    });
  }
  handle("settings:read", () => settings);
  handle("settings:save", async (value) => {
    const next = { backend: backendUrl(value) };
    if (next.backend !== settings.backend) {
      await client.logout();
      client.setBase(next.backend);
    }
    await fs.mkdir(path.dirname(settingsFile), { recursive: true });
    await fs.writeFile(settingsFile, JSON.stringify(next), "utf8");
    settings = next;
    return settings;
  });
  handle("backend:probe", async (value) => {
    const result = await new ApiClient(backendUrl(value)).probe();
    return {
      ok: result.ok && result.data?.status === "ok",
      message: result.ok ? "Server is connected." : result.error,
    };
  });
  handle("auth:session", () => client.session());
  handle("auth:login", (credentials) =>
    client.login(credentials?.username, credentials?.password),
  );
  handle("auth:logout", () => client.logout());
  handle("api:request", (request) => client.request(request));
  handle("invoice:export", async (id) => {
    const result = await client.invoicePdf(id);
    if (!result.ok) return result;
    const choice = await dialog.showSaveDialog(window, {
      title: "Export invoice PDF",
      defaultPath: `invoice-${id}.pdf`,
      filters: [{ name: "PDF document", extensions: ["pdf"] }],
    });
    if (choice.canceled || !choice.filePath)
      return { ok: true, cancelled: true };
    await fs.writeFile(choice.filePath, result.data);
    return { ok: true, path: choice.filePath };
  });
  handle(
    "invoice:print",
    () =>
      new Promise((resolve) =>
        window.webContents.print(
          { silent: false, printBackground: true },
          (ok, message) => resolve({ ok, message }),
        ),
      ),
  );
  function createWindow() {
    window = new BrowserWindow({
      show: visible,
      width: 1400,
      height: 930,
      minWidth: 1060,
      minHeight: 720,
      backgroundColor: "#f5f6fa",
      autoHideMenuBar: true,
      webPreferences: {
        preload: path.join(__dirname, "preload.js"),
        contextIsolation: true,
        nodeIntegration: false,
        sandbox: true,
        offscreen: !visible,
        backgroundThrottling: false,
      },
    });
    window.webContents.setWindowOpenHandler(() => ({ action: "deny" }));
    window.webContents.on("will-navigate", (event) => event.preventDefault());
    window.loadFile("index.html");
    return window;
  }
  createWindow();
  app.on("activate", () => {
    if (!BrowserWindow.getAllWindows().length) createWindow();
  });
  return {
    get window() {
      return window;
    },
    client,
  };
}
if (require.main === module) {
  startDesktop().catch((error) => {
    dialog.showErrorBox("Unable to start Tripathi Operations", error.message);
    app.quit();
  });
  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") app.quit();
  });
}
module.exports = { startDesktop };

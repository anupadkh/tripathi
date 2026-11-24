const { app, dialog } = require("electron");
const path = require("node:path");
const fs = require("node:fs/promises");
const os = require("node:os");
const { spawn } = require("node:child_process");
const { once } = require("node:events");
const net = require("node:net");
const root = path.resolve(__dirname, "..");
app.on("window-all-closed", () => {});
let folder,
  server,
  desktop,
  errors = [];
async function command(executable, args, env) {
  const child = spawn(executable, args, {
    cwd: root,
    env,
    windowsHide: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let output = "";
  child.stdout.on("data", (chunk) => (output += chunk));
  child.stderr.on("data", (chunk) => (output += chunk));
  const [code] = await once(child, "exit");
  if (code !== 0) throw new Error(`Command failed (${code}): ${output}`);
}
async function waitUntil(work, message, limit = 20000) {
  const end = Date.now() + limit;
  while (Date.now() < end) {
    if (await work()) return;
    await new Promise((r) => setTimeout(r, 80));
  }
  throw new Error(message);
}
async function js(code) {
  const result = await desktop.window.webContents
    .executeJavaScript(`(async () => {
    try { return { ok: true, value: await (${code}) }; }
    catch (error) { return { ok: false, error: error.message + '\\n' + error.stack }; }
  })()`);
  if (!result.ok) throw new Error(result.error);
  return result.value;
}
async function idle() {
  await waitUntil(() => js("!busy"), "UI remained busy");
}
async function click(selector) {
  await idle();
  await js(
    `(()=>{const node=document.querySelector(${JSON.stringify(selector)});if(!node)throw new Error('Missing control: '+${JSON.stringify(selector)});if(node.disabled)throw new Error('Disabled control: '+${JSON.stringify(selector)});node.click();})()`,
  );
}
async function set(selector, value) {
  await js(
    `(()=>{const node=document.querySelector(${JSON.stringify(selector)});if(!node)throw new Error('Missing input: '+${JSON.stringify(selector)});node.value=${JSON.stringify(value)};node.dispatchEvent(new Event('input',{bubbles:true}));node.dispatchEvent(new Event('change',{bubbles:true}));})()`,
  );
}
async function submit(selector) {
  await idle();
  await js(
    `document.querySelector(${JSON.stringify(selector)}).requestSubmit()`,
  );
  await idle();
}
async function visible(selector) {
  await waitUntil(
    () => js(`Boolean(document.querySelector(${JSON.stringify(selector)}))`),
    "Missing UI: " + selector,
  );
}
async function run() {
  folder = await fs.mkdtemp(path.join(root, ".desktop-smoke-"));
  app.setPath("userData", path.join(folder, "electron-data"));
  const python =
    process.env.TRIPATHI_TEST_PYTHON ||
    path.join(root, ".venv", "Scripts", "python.exe");
  const env = {
    ...process.env,
    DJANGO_DB_PATH: path.join(folder, "smoke.sqlite3"),
    DJANGO_ALLOWED_HOSTS: "127.0.0.1,localhost,testserver",
    DJANGO_DEBUG: "1",
  };
  delete env.POSTGRES_DB;
  await command(python, ["manage.py", "migrate", "--noinput"], env);
  await command(python, ["scripts/desktop_fixture.py"], env);
  const reservation = net.createServer();
  reservation.listen(0, "127.0.0.1");
  await once(reservation, "listening");
  const port = reservation.address().port;
  await new Promise((r) => reservation.close(r));
  const base = `http://127.0.0.1:${port}`;
  server = spawn(
    python,
    ["manage.py", "runserver", `127.0.0.1:${port}`, "--noreload"],
    { cwd: root, env, windowsHide: true, stdio: "ignore" },
  );
  await fs.writeFile(path.join(folder, "server.pid"), String(server.pid));
  await waitUntil(async () => {
    try {
      return (await fetch(base + "/api/v1/health/")).ok;
    } catch {
      return false;
    }
  }, "Django did not become healthy");
  const settingsPath = path.join(folder, "connection.json");
  await fs.writeFile(settingsPath, JSON.stringify({ backend: base }));
  desktop = await require("./main").startDesktop({
    visible: false,
    settingsPath,
  });
  desktop.window.webContents.on("console-message", (...args) => {
    const details = args.find(
      (a) => a && typeof a === "object" && "message" in a,
    );
    if (details?.level === 3) errors.push(details.message);
  });
  await visible("#login-form");
  await set("#username", "desktop-test");
  await set("#password", "desktop-test-password");
  await submit("#login-form");
  await visible('[data-customer="1"]');
  if (
    await js(
      'Boolean(document.querySelector("#content img"))||Boolean(window.hacked)',
    )
  )
    throw new Error("Customer names were not escaped");
  await click("#next-page");
  await idle();
  await waitUntil(
    () =>
      js('document.querySelector("#pager")?.textContent.includes("Page 2")'),
    "Customer pagination failed",
  );
  await click("#prev-page");
  await idle();
  await click('[data-customer="1"]');
  await visible("#create-invoice");
  await click("#create-invoice");
  await visible("#line-form");
  for (const quantity of ["2", "3"]) {
    await set("#line-form [name=stock_item]", "2");
    await set("#line-form [name=location]", "1");
    await set("#line-form [name=density]", "28");
    await set("#line-form [name=description]", "Foam sheet");
    await set("#line-form [name=qty]", quantity);
    await set("#line-form [name=length]", "72");
    await set("#line-form [name=breadth]", "36");
    await set("#line-form [name=height]", "1");
    await submit("#line-form");
  }
  await click("#group-invoice");
  await visible("[data-rate]");
  await idle();
  if (
    !(await js(
      'document.getElementById("invoice-stage").textContent.includes("5.0000")',
    ))
  )
    throw new Error("Dimensional grouping failed");
  await set("[data-rate]", "100");
  await click("#save-rates");
  await idle();
  if (
    !(await js(
      'document.getElementById("totals").textContent.includes("565.00")',
    ))
  )
    throw new Error("Server pricing failed");
  await click("#post-invoice");
  await visible("#invoice-payment");
  await idle();
  const stock = await desktop.client.request({
    path: "stock/balances/?item=2",
  });
  if (!stock.ok || stock.data.results[0].quantity !== "5.0000")
    throw new Error("Invoice did not issue linked stock.");
  if (
    !(await js(
      'document.getElementById("content").textContent.includes("565.00")',
    ))
  )
    throw new Error("Posted invoice was not displayed");
  await click("#invoice-payment");
  await visible("#modal-form");
  await submit("#modal-form");
  await idle();
  if (
    !(await js(
      'document.querySelector(".invoice-total").textContent.includes("Outstanding NPR 0.00")',
    ))
  )
    throw new Error("Cash receipt was not allocated");
  const pdfPath = path.join(folder, "invoice.pdf");
  dialog.showSaveDialog = async () => ({ canceled: false, filePath: pdfPath });
  await click("#export-pdf");
  await idle();
  await waitUntil(
    async () => {
      try {
        await fs.access(pdfPath);
        return true;
      } catch {
        return false;
      }
    },
    "PDF export did not finish: " +
      (await js('document.getElementById("toast").textContent')),
    5000,
  );
  if (!(await fs.readFile(pdfPath)).subarray(0, 5).equals(Buffer.from("%PDF-")))
    throw new Error("PDF export failed");
  await click("#return-customer");
  await visible("#create-invoice");
  await click('[data-tab="payments"]');
  await idle();
  await visible("[data-receipt]");
  for (const page of [
    "purchases",
    "inventory",
    "production",
    "expenses",
    "payroll",
  ]) {
    await click(`[data-page="${page}"]`);
    await idle();
    await waitUntil(
      () =>
        js(
          '!document.getElementById("content").textContent.includes("Loading records")',
        ),
      "Module remained loading",
    );
    if (
      await js(
        'document.getElementById("content").textContent.includes("Unable to load")',
      )
    )
      throw new Error("Module failed: " + page);
  }
  // Exercise a real repeatable purchase form and persist its review/post flow.
  await click('[data-page="purchases"]');
  await idle();
  await visible("#module-create");
  await click("#module-create");
  await visible("#modal-form");
  await set("#modal-form [name=bill_number]", "SMOKE-PUR-1");
  await set("#nested-rows [name=quantity]", "10");
  await set("#nested-rows [name=rate]", "20");
  await submit("#modal-form");
  await idle();
  await visible("[data-document]");
  await click("[data-document]");
  await visible("#post-document");
  await click("#post-document");
  await idle();
  if (
    !(await js(
      'document.querySelector("#modal-content").textContent.includes("posted")',
    ))
  )
    throw new Error("Purchase posting failed");
  await click("#close-document");
  await click('[data-page="customers"]');
  await visible('[data-customer="1"]');
  await idle();
  const screenshot = await desktop.window.webContents.capturePage();
  await fs.writeFile(
    path.join(__dirname, "integration-preview.png"),
    screenshot.toPNG(),
  );
  if (
    await js(
      'localStorage.getItem("token")||localStorage.getItem("access_token")',
    )
  )
    throw new Error("Token leaked into renderer storage");
  await click("#logout");
  await visible("#login-form");
  if ((await desktop.client.request({ path: "customers/" })).status !== 401)
    throw new Error("Logout did not clear authentication");
  if (errors.length) throw new Error("Renderer errors: " + errors.join("\n"));
  return "PASS: real Django login, escaped customer names, customer pagination/detail, dimensional billing, grouping, server VAT totals, posting, cash allocation, PDF export, live modules, purchase creation/posting, and logout.";
}
(async () => {
  try {
    const result = await run();
    await fs.writeFile(path.join(__dirname, "smoke-result.txt"), result);
    console.log(result);
  } catch (error) {
    await fs.writeFile(
      path.join(__dirname, "smoke-result.txt"),
      error.stack || String(error),
    );
    console.error(error);
  } finally {
    if (server && server.exitCode === null) {
      try {
        await command(
          "taskkill.exe",
          ["/PID", String(server.pid), "/T", "/F"],
          process.env,
        );
      } catch {
        server.kill();
      }
    }
    desktop?.window?.destroy();
    if (folder) {
      const absolute = path.resolve(folder);
      if (
        path.dirname(absolute) === root &&
        path.basename(absolute).startsWith(".desktop-smoke-")
      ) {
        try {
          await fs.rm(absolute, {
            recursive: true,
            force: true,
            maxRetries: 5,
            retryDelay: 200,
          });
        } catch {}
      }
    }
    app.exit(
      (
        await fs.readFile(path.join(__dirname, "smoke-result.txt"), "utf8")
      ).startsWith("PASS")
        ? 0
        : 1,
    );
  }
})();

const pages = [
  ["customers", "◎", "Customers"],
  ["billing", "▤", "Invoices"],
  ["dashboard", "◈", "Overview"],
  ["purchases", "↓", "Purchases"],
  ["inventory", "▦", "Inventory"],
  ["production", "⚙", "Production"],
  ["expenses", "↗", "Expenses"],
  ["payroll", "◇", "Labour & payroll"],
  ["settings", "⋯", "Settings"],
];
const state = {
  user: null,
  authenticatedUserId: null,
  bootstrap: null,
  page: "customers",
  customer: null,
  editor: null,
  customerPage: 1,
  search: "",
  history: "invoices",
  historyPage: 1,
  listPage: 1,
  cache: new Map(),
  keys: new Map(),
};
const content = document.getElementById("content");
const modal = document.getElementById("modal");
let generation = 0,
  busy = false;
const esc = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const money = (value) => {
  if (value === null || value === undefined) return "—";
  const [whole, fraction = ""] = String(value).split(".");
  return `NPR ${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction.padEnd(2, "0").slice(0, 2)}`;
};
const can = (permission) =>
  state.user?.is_superuser || state.user?.permissions.includes(permission);
const today = () =>
  state.bootstrap?.date ||
  new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kathmandu" });
const button = (id, text, primary = false) =>
  `<button id="${id}" class="${primary ? "primary" : "secondary"}">${text}</button>`;
const title = (name, description, actions = "") =>
  `<div class="title-row"><div><h1>${esc(name)}</h1><p>${esc(description)}</p></div><div class="actions">${actions}</div></div>`;
const table = (heads, rows) =>
  rows.length
    ? `<div class="table-scroll"><table><thead><tr>${heads.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`
    : '<div class="empty">No records found.</div>';
const panel = (heading, body) =>
  `<div class="panel"><div class="panel-head"><h2>${esc(heading)}</h2></div>${body}</div>`;
const pill = (value) => `<span class="pill ${esc(value)}">${esc(value)}</span>`;
const on = (id, event, handler) => {
  const node = document.getElementById(id);
  if (node) node.addEventListener(event, handler);
};
function toast(message) {
  const node = document.getElementById("toast");
  node.textContent = message;
  node.style.display = "block";
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (node.style.display = "none"), 6000);
}
function notice(message) {
  document.getElementById("connection-notice").textContent = message;
}
function report(error) {
  toast(error.message || String(error));
  const node = document.getElementById("page-error");
  if (node) node.textContent = error.message || String(error);
}
async function act(work) {
  if (busy) return;
  busy = true;
  const buttons = [
    ...document.querySelectorAll("button, input, select, textarea"),
  ].map((b) => [b, b.disabled]);
  buttons.forEach(([b]) => (b.disabled = true));
  try {
    await work();
  } catch (error) {
    report(error);
  } finally {
    busy = false;
    buttons.forEach(([b, disabled]) => (b.disabled = disabled));
  }
}
async function api(path, method = "GET", data) {
  const fingerprint = method + path + JSON.stringify(data);
  let key;
  if (method === "POST" && !path.endsWith("/preview/")) {
    key = state.keys.get(fingerprint) || crypto.randomUUID();
    state.keys.set(fingerprint, key);
  }
  const result = await window.desktop.request({ path, method, data, key });
  if (!result.ok) {
    if (result.status === 401) {
      state.user = null;
      if (modal.open) modal.close();
      updateHeader();
      showLogin("Your session ended. Sign in again to continue.");
    }
    const error = new Error(result.error);
    error.status = result.status;
    throw error;
  }
  state.keys.delete(fingerprint);
  return result.data;
}
const postAction = (resource, object, action = "post", extra = {}) =>
  api(`${resource}/${object.id}/${action}/`, "POST", {
    revision: object.revision,
    ...extra,
  });
async function all(resource) {
  if (state.cache.has(resource)) return state.cache.get(resource);
  let page = 1,
    rows = [];
  while (true) {
    const data = await api(`${resource}/?page=${page}`);
    rows.push(...data.results);
    if (!data.next) break;
    page++;
  }
  state.cache.set(resource, rows);
  return rows;
}
function invalidate(...resources) {
  for (const resource of resources) state.cache.delete(resource);
}
function updateHeader() {
  document.getElementById("session-name").textContent =
    state.user?.name || state.user?.username || "";
  document.getElementById("connection-badge").textContent = state.user
    ? "LIVE SERVER"
    : "SIGNED OUT";
  document.getElementById("logout").hidden = !state.user;
  document.getElementById("workspace-title").textContent =
    state.bootstrap?.company || "Operations workspace";
  notice(
    state.user
      ? "Connected to your business database. Changes save to the server."
      : "Sign in with your Django account to load your business records.",
  );
}
function showLogin(message = "") {
  generation++;
  content.innerHTML = `<div class="login-panel panel"><span class="stage">TRIPATHI OPERATIONS</span><h1>Welcome back</h1><p>Sign in to view customers and create invoices.</p><form id="login-form"><label for="server">Server address</label><input id="server" type="url" required><label for="username">Username</label><input id="username" autocomplete="username" required><label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required><p class="error" id="login-error">${esc(message)}</p><button class="primary" type="submit">Sign in</button></form><p>Start the business server before signing in.</p></div>`;
  window.desktop.readSettings().then((settings) => {
    const field = document.getElementById("server");
    if (field) field.value = settings.backend;
  });
  on("login-form", "submit", (event) => {
    event.preventDefault();
    act(async () => {
      const credentials = {
        username: document.getElementById("username").value.trim(),
        password: document.getElementById("password").value,
      };
      await window.desktop.saveSettings(
        document.getElementById("server").value.trim(),
      );
      const result = await window.desktop.login(credentials);
      document.getElementById("password").value = "";
      if (!result.ok) {
        document.getElementById("login-error").textContent = result.error;
        return;
      }
      if (
        state.authenticatedUserId &&
        state.authenticatedUserId !== result.data.user.id
      ) {
        state.editor = null;
        state.keys.clear();
      }
      state.user = result.data.user;
      state.authenticatedUserId = result.data.user.id;
      state.cache.clear();
      state.bootstrap = await api("bootstrap/");
      updateHeader();
      await navigate("customers");
    });
  });
}
function pager(data, current, callback) {
  const container = document.getElementById("pager");
  if (!container) return;
  container.innerHTML = `<span>${data.count} records · Page ${current}</span><div>${button("prev-page", "← Previous")}${button("next-page", "Next →")}</div>`;
  document.getElementById("prev-page").disabled = !data.previous;
  document.getElementById("next-page").disabled = !data.next;
  on("prev-page", "click", () => act(() => callback(current - 1)));
  on("next-page", "click", () => act(() => callback(current + 1)));
}
async function navigate(page) {
  state.page = page;
  document
    .querySelectorAll("nav button")
    .forEach((node) =>
      node.classList.toggle("active", node.dataset.page === page),
    );
  if (!state.user && page !== "settings") {
    showLogin();
    return;
  }
  const version = ++generation;
  content.innerHTML = '<div class="empty">Loading records…</div>';
  try {
    if (page === "settings") await settingsPage(version);
    else if (page === "customers") await customersPage(version);
    else if (page === "customer") await customerPage(version);
    else if (page === "billing") await invoicesPage(version);
    else if (page === "editor") editorPage();
    else if (page === "dashboard") await dashboardPage(version);
    else await modulePage(version);
  } catch (error) {
    if (version !== generation) return;
    if (error.status === 401) return;
    content.innerHTML = title(
      "Unable to load records",
      error.message,
      button("retry", "Try again"),
    );
    on("retry", "click", () => navigate(page));
  }
}
async function customersPage(version) {
  const data = await api(
    `customers/?page=${state.customerPage}&search=${encodeURIComponent(state.search)}`,
  );
  if (version !== generation) return;
  content.innerHTML =
    title(
      "Customers",
      "Choose a customer, then create an invoice.",
      can("invoices.add_customer")
        ? button("add-customer", "+ Add customer", true)
        : "",
    ) +
    `<form id="search-form" class="search-bar"><input id="customer-search" aria-label="Search customers" placeholder="Search name, address, phone or PAN" value="${esc(state.search)}"><button class="secondary">Search</button></form>` +
    panel(
      "Customer directory",
      table(
        ["Customer", "Phone", "PAN", "Address", "Balance", ""],
        data.results.map((c) => [
          `<button class="text-link" data-customer="${c.id}">${esc(c.name || "Unnamed customer")}</button>`,
          esc(c.phone || "—"),
          esc(c.pan || "—"),
          esc(c.address || "—"),
          money(c.balance),
          `<button class="secondary" data-new-invoice="${c.id}">Create invoice</button>`,
        ]),
      ),
    ) +
    '<div id="pager" class="pager"></div>';
  on("search-form", "submit", (e) => {
    e.preventDefault();
    state.search = document.getElementById("customer-search").value.trim();
    state.customerPage = 1;
    navigate("customers");
  });
  content.querySelectorAll("[data-customer]").forEach(
    (b) =>
      (b.onclick = () => {
        state.customer = Number(b.dataset.customer);
        state.history = "invoices";
        state.historyPage = 1;
        navigate("customer");
      }),
  );
  content
    .querySelectorAll("[data-new-invoice]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          act(() =>
            newInvoice(
              data.results.find((c) => c.id === Number(b.dataset.newInvoice)),
            ),
          )),
    );
  on("add-customer", "click", () => customerForm());
  pager(data, state.customerPage, async (p) => {
    state.customerPage = p;
    await navigate("customers");
  });
}
function customerForm() {
  openForm(
    "Add customer",
    [
      { name: "name", label: "Customer name", required: true },
      { name: "phone", label: "Phone", type: "tel" },
      { name: "pan", label: "PAN / VAT number" },
      { name: "address", label: "Address" },
    ],
    async (values) => {
      const body = {
        name: values.name,
        address: values.address,
        phone: values.phone || null,
        pan: values.pan || null,
      };
      const customer = await api("customers/", "POST", body);
      state.customer = customer.id;
      invalidate("customers");
      await navigate("customer");
    },
    "Save customer",
  );
}
function customerYear() {
  return (
    state.bootstrap?.default_fiscal_year ||
    state.bootstrap?.fiscal_years?.find(
      (y) => y.start_date <= today() && y.end_date >= today(),
    )?.id ||
    state.bootstrap?.fiscal_years?.[0]?.id
  );
}
async function customerPage(version) {
  const id = state.customer;
  const year = state.selectedYear;
  const statementAllowed =
    can("invoices.view_invoice") &&
    can("invoices.view_payment") &&
    can("invoices.view_openingbalance");
  const [customer, statement] = await Promise.all([
    api(`customers/${id}/`),
    statementAllowed
      ? api(`customers/${id}/statement/${year ? "?fiscal_year=" + year : ""}`)
      : null,
  ]);
  if (version !== generation) return;
  const historyResource =
    state.history === "payments"
      ? "payments"
      : state.history === "openings"
        ? "opening-balances"
        : "invoices";
  const permission =
    historyResource === "payments"
      ? "invoices.view_payment"
      : historyResource === "opening-balances"
        ? "invoices.view_openingbalance"
        : "invoices.view_invoice";
  const data = can(permission)
    ? await api(
        `${historyResource}/?customer=${id}&page=${state.historyPage}${state.history === "vat" ? "&is_vat=true" : ""}${state.history === "invoices" ? "&is_vat=false" : ""}${year && historyResource === "invoices" ? "&fiscal_year=" + year : ""}`,
      )
    : { results: [], count: 0 };
  const receipts =
    state.history === "payments" && can("operations.view_customerreceipt")
      ? await api(`customer-payments/?customer=${id}&page=${state.historyPage}`)
      : null;
  if (version !== generation) return;
  content.innerHTML =
    title(
      customer.name || "Customer",
      `${customer.address || "No address"} · Phone ${customer.phone || "—"} · PAN ${customer.pan || "—"}`,
      button("back-customers", "← Customers") +
        (can("invoices.add_invoice")
          ? button("create-invoice", "+ Add new invoice", true)
          : ""),
    ) +
    `<div class="cards">${[
      ["Opening balance", statement?.opening_balance],
      ["Invoiced", statement?.invoiced],
      ["Payments received", statement?.received],
      ["Balance due", statement?.balance],
    ]
      .map(
        ([label, value]) =>
          `<div class="card"><small>${label}</small><strong>${money(value)}</strong></div>`,
      )
      .join("")}</div><div class="tabs">${[
      ["invoices", "Invoices"],
      ["vat", "VAT invoices"],
      ["payments", "Payments"],
      ["openings", "Opening balances"],
    ]
      .map(
        ([id, label]) =>
          `<button data-tab="${id}" class="secondary ${state.history === id ? "active" : ""}">${label}</button>`,
      )
      .join(
        "",
      )}<select id="statement-year" aria-label="Fiscal year"><option value="">All available history</option>${(state.bootstrap.fiscal_years || []).map((y) => `<option value="${y.id}" ${Number(year) === y.id ? "selected" : ""}>${esc(y.title)}</option>`).join("")}</select></div>` +
    panel(
      state.history === "vat"
        ? "VAT invoices"
        : state.history === "payments"
          ? "Customer payments"
          : state.history === "openings"
            ? "Opening balances"
            : "Customer invoices",
      historyResource === "invoices"
        ? invoiceTable(data.results)
        : historyResource === "payments"
          ? table(
              ["Date", "Method", "Amount"],
              data.results.map((p) => [
                esc(p.date),
                esc(
                  {
                    1: "Cheque",
                    2: "Cash",
                    3: "Bank transfer",
                    4: "Mobile / internet",
                    5: "Transport",
                    6: "Bank deposit",
                    7: "Goods returned",
                    8: "Discount",
                  }[p.payment_mode],
                ),
                money(p.amount),
              ]),
            )
          : table(
              ["Fiscal year", "Opening balance"],
              data.results.map((o) => [
                esc(
                  state.bootstrap.fiscal_years?.find((y) => y.id === o.term)
                    ?.title || o.term,
                ),
                money(o.amount),
              ]),
            ),
    ) +
    `<div id="pager" class="pager"></div>${can("operations.add_customerreceipt") ? button("receive-payment", "Record payment") : ""}` +
    (receipts
      ? panel(
          "Payment receipts and cheques",
          table(
            [
              "Receipt",
              "Date",
              "Method",
              "Account",
              "Cheque status",
              "Amount",
              "Status",
              "",
            ],
            receipts.results.map((r) => [
              esc(r.id),
              esc(r.date),
              esc(r.method),
              esc(r.account),
              r.method === "cheque" ? pill(r.cheque_status) : "—",
              money(r.amount),
              pill(r.status),
              `<button class="secondary" data-receipt="${r.id}">View receipt</button>`,
            ]),
          ),
        )
      : "");
  content
    .querySelectorAll("[data-receipt]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          act(() =>
            viewDocument("customer-payments", Number(b.dataset.receipt)),
          )),
    );
  on("back-customers", "click", () => navigate("customers"));
  on("create-invoice", "click", () => act(() => newInvoice(customer)));
  on("receive-payment", "click", () => act(() => paymentForm(customer)));
  content.querySelectorAll("[data-tab]").forEach(
    (b) =>
      (b.onclick = () => {
        state.history = b.dataset.tab;
        state.historyPage = 1;
        navigate("customer");
      }),
  );
  on("statement-year", "change", (e) => {
    state.selectedYear = e.target.value || null;
    state.historyPage = 1;
    navigate("customer");
  });
  bindInvoiceLinks(data.results);
  pager(data, state.historyPage, async (p) => {
    state.historyPage = p;
    await navigate("customer");
  });
}
function invoiceTable(rows) {
  return table(
    ["Bill", "Date", "Customer", "Type", "Status", "Total", "Outstanding", ""],
    rows.map((i) => [
      esc(i.number || i.vat_bill_no || `Draft #${i.id}`),
      esc(i.date),
      esc(
        i.customer_name ||
          state.cache.get("customers")?.find((c) => c.id === i.issued_for)
            ?.name ||
          i.issued_for,
      ),
      i.is_vat ? "VAT" : "Regular",
      pill(i.status),
      money(i.total),
      money(i.outstanding),
      `<button class="secondary" data-invoice="${i.id}">${i.status === "posted" || i.source === "legacy" ? "View" : "Continue"}</button>`,
    ]),
  );
}
function bindInvoiceLinks(rows) {
  content
    .querySelectorAll("[data-invoice]")
    .forEach(
      (b) =>
        (b.onclick = () => act(() => loadInvoice(Number(b.dataset.invoice)))),
    );
}
async function invoicesPage(version) {
  const data = await api(`invoices/?page=${state.listPage}`);
  if (version !== generation) return;
  content.innerHTML =
    title(
      "Invoices",
      "Select a customer to create a new invoice.",
      button("choose-customer", "Choose customer", true) +
        (state.editor &&
        (!state.editor.invoice ||
          ["draft", "grouped"].includes(state.editor.invoice.status))
          ? button("resume-draft", "Resume current draft")
          : ""),
    ) +
    panel("Invoice history", invoiceTable(data.results)) +
    '<div id="pager" class="pager"></div>';
  on("choose-customer", "click", () => navigate("customers"));
  on("resume-draft", "click", () => navigate("editor"));
  bindInvoiceLinks(data.results);
  pager(data, state.listPage, async (p) => {
    state.listPage = p;
    await navigate("billing");
  });
}
async function newInvoice(customer) {
  if (!can("invoices.add_invoice"))
    throw new Error("You need permission to create invoices.");
  if (
    state.editor?.dirty &&
    !confirm(
      "Start another invoice? Unsaved changes in the current invoice will be lost.",
    )
  )
    return;
  await loadStockChoices();
  state.editor = {
    customer,
    invoice: null,
    lines: [],
    stage: 1,
    dirty: false,
    preview: null,
    metadata: {
      date: today(),
      fiscal_year: customerYear(),
      is_vat: true,
      vat_rate: state.bootstrap.default_vat_rate,
      discount: "0.00",
      notes: "",
      credit_bank_name: "",
    },
  };
  await navigate("editor");
}
function editableLine(line) {
  const keys = [
    "density",
    "description",
    "qty",
    "unit",
    "taxable",
    "tax_include",
    "length",
    "breadth",
    "height",
    "mm",
  ];
  const out = {};
  keys.forEach((k) => {
    if (line[k] !== undefined && line[k] !== null) out[k] = line[k];
  });
  if (line.stock_item_id && line.location_id) {
    out.stock_item = line.stock_item_id;
    out.location = line.location_id;
  } else if (line.stock_item && line.location) {
    out.stock_item = line.stock_item;
    out.location = line.location;
  }
  return out;
}
async function loadInvoice(id) {
  await loadStockChoices();
  const invoice = await api(`invoices/${id}/`);
  const customer = await api(`customers/${invoice.issued_for}/`);
  state.editor = {
    customer,
    invoice,
    lines: invoice.lines.map(editableLine),
    stage: invoice.status === "grouped" ? 2 : 1,
    dirty: false,
    preview: null,
    metadata: Object.fromEntries(
      [
        "date",
        "fiscal_year",
        "is_vat",
        "vat_rate",
        "discount",
        "notes",
        "credit_bank_name",
      ].map((k) => [k, invoice[k] ?? ""]),
    ),
  };
  state.page = "editor";
  await navigate("editor");
}
async function loadStockChoices() {
  await Promise.all([
    can("operations.view_stockitem") ? all("items") : Promise.resolve([]),
    can("operations.view_location") ? all("locations") : Promise.resolve([]),
  ]);
}
function editorPage() {
  const e = state.editor;
  if (!e) {
    navigate("customers");
    return;
  }
  const i = e.invoice;
  const readonly =
    i &&
    (i.status === "posted" ||
      i.status === "cancelled" ||
      i.source === "legacy");
  if (readonly) {
    content.innerHTML =
      title(
        i.number || i.vat_bill_no || `Invoice #${i.id}`,
        `${e.customer.name} · ${i.date} · ${i.is_vat ? "VAT" : "Regular"} · ${i.status}`,
        button("return-customer", "← Customer") +
          (i.status === "posted"
            ? button("export-pdf", "Export PDF", true) +
              button("print-invoice", "Print")
            : ""),
      ) +
      `<div class="print-area">${panel(
        "Invoice details",
        table(
          ["Density", "Description", "Quantity", "Unit", "Rate", "Amount"],
          i.lines.map((l) => [
            esc(l.density),
            esc(l.description),
            esc(l.billing_quantity || l.qty),
            esc(l.unit),
            esc(l.rate || l.calculated_rate || "0"),
            money(l.price),
          ]),
        ),
      )}${
        i.groups.length
          ? panel(
              "Density summary",
              table(
                ["Density", "Combined quantity", "Unit", "Rate", "Amount"],
                i.groups.map((g) => [
                  esc(g.density),
                  esc(g.quantity),
                  esc(g.unit),
                  esc(g.rate),
                  money(g.amount),
                ]),
              ),
            )
          : ""
      }<div class="invoice-total">Total ${money(i.total)} · VAT ${money(i.tax)} · Outstanding ${money(i.outstanding)}</div><p>${esc(i.notes)}</p></div><div class="actions">${i.status === "posted" && can("operations.add_customerreceipt") ? button("invoice-payment", "Record payment") : ""}${i.status === "posted" && i.source === "api" && can("invoices.change_invoice") ? button("cancel-invoice", "Cancel invoice") : ""}</div><p id="page-error" class="error"></p>`;
    on("return-customer", "click", () => {
      state.customer = e.customer.id;
      navigate("customer");
    });
    on("export-pdf", "click", () =>
      act(async () => {
        const result = await window.desktop.exportInvoice(i.id);
        if (!result.ok) throw new Error(result.error);
        if (!result.cancelled) toast("Invoice PDF exported.");
      }),
    );
    on("invoice-payment", "click", () => act(() => paymentForm(e.customer, i)));
    on("print-invoice", "click", () =>
      act(async () => {
        const result = await window.desktop.print();
        if (
          !result.ok &&
          result.message &&
          result.message !== "Print job canceled"
        )
          throw new Error(result.message);
      }),
    );
    on("cancel-invoice", "click", () =>
      openForm(
        "Cancel invoice",
        [
          { name: "reason", label: "Reason", required: true },
          {
            name: "date",
            label: "Reversal date",
            type: "date",
            value: today(),
            required: true,
          },
        ],
        async (v) => {
          await postAction("invoices", i, "cancel", v);
          await loadInvoice(i.id);
        },
        "Cancel and reverse",
      ),
    );
    return;
  }
  content.innerHTML =
    title(
      i ? `Invoice draft #${i.id}` : "New invoice",
      `For ${e.customer.name} · ${e.customer.address || ""}`,
      button("return-customer", "← Customer") +
        (i ? button("reload-invoice", "Reload saved draft") : ""),
    ) +
    `<div class="flow"><span class="${e.stage === 1 ? "current" : ""}">1 · Foam items</span><span class="${e.stage === 2 ? "current" : ""}">2 · Density groups & rates</span></div><div class="panel"><div class="form-row"><div><label for="bill-date">Bill date</label><input id="bill-date" type="date" value="${esc(e.metadata.date)}"></div><div><label for="fiscal-year">Fiscal year</label><select id="fiscal-year">${(state.bootstrap.fiscal_years || []).map((y) => `<option value="${y.id}" ${Number(e.metadata.fiscal_year) === y.id ? "selected" : ""}>${esc(y.title)}</option>`).join("")}</select></div><div><label for="bill-type">Bill type</label><select id="bill-type"><option value="vat" ${e.metadata.is_vat ? "selected" : ""}>VAT</option><option value="regular" ${!e.metadata.is_vat ? "selected" : ""}>Regular</option></select></div><div><label for="vat-rate">VAT rate (%)</label><input id="vat-rate" type="number" min="0" max="100" step=".01" value="${esc(e.metadata.vat_rate)}"></div><div><label for="discount">Discount (NPR)</label><input id="discount" type="number" min="0" step=".01" value="${esc(e.metadata.discount)}"></div><div><label for="credit-bank">Credit bank reference</label><input id="credit-bank" value="${esc(e.metadata.credit_bank_name)}"></div></div><label for="bill-notes">Notes</label><textarea id="bill-notes">${esc(e.metadata.notes)}</textarea><p id="page-error" class="error"></p><div id="invoice-stage"></div></div>`;
  const bindings = {
    "bill-date": "date",
    "fiscal-year": "fiscal_year",
    "vat-rate": "vat_rate",
    discount: "discount",
    "credit-bank": "credit_bank_name",
    "bill-notes": "notes",
  };
  for (const [id, key] of Object.entries(bindings))
    on(id, "input", (event) => {
      e.metadata[key] =
        key === "fiscal_year" ? Number(event.target.value) : event.target.value;
      e.dirty = true;
      e.preview = null;
      const post = document.getElementById("post-invoice");
      if (post) post.disabled = true;
    });
  on("bill-type", "change", (event) => {
    e.metadata.is_vat = event.target.value === "vat";
    e.dirty = true;
    e.preview = null;
    const post = document.getElementById("post-invoice");
    if (post) post.disabled = true;
  });
  on("return-customer", "click", () => {
    state.customer = e.customer.id;
    navigate("customer");
  });
  on("reload-invoice", "click", () =>
    act(async () => {
      if (!e.dirty || confirm("Reload and discard unsaved changes?"))
        await loadInvoice(i.id);
    }),
  );
  if (!state.bootstrap.fiscal_years?.length) {
    document.getElementById("invoice-stage").innerHTML =
      "<p>Create a fiscal year in Settings before creating an invoice.</p>";
    return;
  }
  if (e.stage === 1) lineStage();
  else groupStage();
}
function lineStage() {
  const e = state.editor;
  const target = document.getElementById("invoice-stage");
  target.innerHTML =
    `<h2>Foam items</h2><p>Use dimensional mm billing for the current foam calculation, or enter a quantity in another unit.</p><form id="line-form"><div class="form-row"><label>Density<input name="density" required placeholder="28"></label><label>Description<input name="description" placeholder="Foam sheet"></label><label>Quantity / pieces<input name="qty" type="number" min=".0001" step=".0001" required value="1"></label><label>Billing unit<select name="unit"><option value="mm">Dimensional mm</option>${(
      state.bootstrap.units || []
    )
      .filter((u) => u !== "mm")
      .map((u) => `<option value="${esc(u)}">${esc(u)}</option>`)
      .join(
        "",
      )}</select></label><label>Length<input name="length" type="number" min="0" step=".0001" value="0"></label><label>Breadth<input name="breadth" type="number" min="0" step=".0001" value="0"></label><label>Height<input name="height" type="number" min="0" step=".0001" value="0"></label><label>Manual mm (if dimensions are zero)<input name="mm" type="number" min="0" step=".0001" value="0"></label><label>Taxability<select name="taxable"><option value="true">Taxable</option><option value="false">Non-taxable</option></select></label><label>Stock item (optional)<select name="stock_item"><option value="">Unlinked / non-stock line</option>${(
      state.cache.get("items") || []
    )
      .filter((i) => i.active && i.kind === "finished")
      .map(
        (i) =>
          `<option value="${i.id}">${esc(i.sku + " · " + i.name)}</option>`,
      )
      .join(
        "",
      )}</select></label><label>Stock location (optional)<select name="location"><option value="">Select location</option>${(state.cache.get("locations") || []).map((l) => `<option value="${l.id}">${esc(l.name)}</option>`).join("")}</select></label></div><button class="primary" type="submit">+ Add foam item</button></form>` +
    table(
      [
        "Density",
        "Description",
        "Dimensions",
        "Pieces / qty",
        "Billing unit",
        "",
      ],
      e.lines.map((l, index) => [
        esc(l.density),
        esc(l.description),
        esc(`${l.length || 0} × ${l.breadth || 0} × ${l.height || 0}`),
        esc(l.qty),
        esc(l.unit),
        `<button class="secondary" data-remove="${index}">Remove</button>`,
      ]),
    ) +
    `<div class="actions">${button("save-draft", "Save draft")}${button("group-invoice", "Continue to density groups →", true)}</div>`;
  document.querySelector("#line-form [name=stock_item]").onchange = (event) => {
    const item = state.cache
      .get("items")
      ?.find((i) => i.id === Number(event.target.value));
    if (item) {
      const form = document.getElementById("line-form");
      form.elements.density.value = item.density;
      form.elements.description.value = item.name;
      if (item.unit !== "piece") form.elements.unit.value = item.unit;
    }
  };
  on("line-form", "submit", (event) => {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.target));
    values.taxable = values.taxable === "true";
    values.tax_include = false;
    if (values.stock_item || values.location) {
      if (!values.stock_item || !values.location)
        return toast("Select both a stock item and a location.");
      values.stock_item = Number(values.stock_item);
      values.location = Number(values.location);
    } else {
      delete values.stock_item;
      delete values.location;
    }
    const q = Number(values.qty);
    if (!Number.isFinite(q) || q <= 0)
      return toast("Enter a positive quantity.");
    if (
      values.unit === "mm" &&
      !(
        Number(values.length) * Number(values.breadth) * Number(values.height) >
        0
      ) &&
      !(Number(values.mm) > 0)
    )
      return toast("Enter positive dimensions or a manual mm value.");
    e.lines.push(values);
    e.dirty = true;
    lineStage();
  });
  target.querySelectorAll("[data-remove]").forEach(
    (b) =>
      (b.onclick = () => {
        e.lines.splice(Number(b.dataset.remove), 1);
        e.dirty = true;
        lineStage();
      }),
  );
  on("save-draft", "click", () =>
    act(async () => {
      await saveDraft(true);
      editorPage();
      toast("Draft saved to Django.");
    }),
  );
  on("group-invoice", "click", () =>
    act(async () => {
      await saveDraft(true);
      e.invoice = await postAction("invoices", e.invoice, "group");
      e.stage = 2;
      e.dirty = false;
      e.preview = null;
      editorPage();
    }),
  );
}
async function saveDraft(withLines) {
  const e = state.editor;
  if (!e.lines.length) throw new Error("Add at least one foam item.");
  if (!e.metadata.fiscal_year) throw new Error("Select a fiscal year.");
  const data = { issued_for: e.customer.id, ...e.metadata };
  if (withLines) data.lines = e.lines.map(editableLine);
  e.invoice = e.invoice
    ? await api(`invoices/${e.invoice.id}/`, "PATCH", {
        revision: e.invoice.revision,
        ...data,
      })
    : await api("invoices/", "POST", data);
  e.dirty = false;
  return e.invoice;
}
function groupStage() {
  const e = state.editor;
  const target = document.getElementById("invoice-stage");
  target.innerHTML =
    `<h2>Density summary</h2><p>The server combines compatible density, billing unit and taxability groups. Enter a rate for each group.</p>` +
    table(
      ["Density", "Combined quantity", "Unit", "Taxable", "Rate", "Amount"],
      e.invoice.groups.map((g) => [
        esc(g.density),
        esc(g.quantity),
        esc(g.unit),
        g.taxable ? "Yes" : "No",
        `<input aria-label="Rate for density ${esc(g.density)}" data-rate="${g.id}" type="number" min=".0001" step=".0001" value="${esc(g.rate)}">`,
        money(g.amount),
      ]),
    ) +
    `<div id="totals" class="invoice-total">${e.preview ? `Subtotal ${money(e.preview.subtotal)} · Discount ${money(e.preview.discount)} · VAT ${money(e.preview.tax)} · Total ${money(e.preview.total)}` : "Save rates to calculate the final bill."}</div><div class="actions">${button("edit-items", "← Edit items")}${button("save-rates", "Save rates & calculate", true)}${button("post-invoice", "Finalize invoice", true)}</div><p>Finalize posts this invoice to the customer account. Record cash, cheque or mobile payments after posting; credit remains outstanding.</p>`;
  document.getElementById("post-invoice").disabled = !e.preview;
  target.querySelectorAll("[data-rate]").forEach(
    (input) =>
      (input.oninput = () => {
        e.dirty = true;
        e.preview = null;
        document.getElementById("post-invoice").disabled = true;
      }),
  );
  on("edit-items", "click", () => {
    e.stage = 1;
    editorPage();
  });
  on("save-rates", "click", () =>
    act(async () => {
      const rates = [...target.querySelectorAll("[data-rate]")].map(
        (input) => ({ id: Number(input.dataset.rate), rate: input.value }),
      );
      if (
        rates.some(
          (g) => !Number.isFinite(Number(g.rate)) || Number(g.rate) <= 0,
        )
      )
        throw new Error("Enter a positive rate for every group.");
      await saveDraft(false);
      for (const rate of rates) {
        e.invoice = await api(
          `invoices/${e.invoice.id}/groups/${rate.id}/`,
          "PATCH",
          { revision: e.invoice.revision, rate: rate.rate },
        );
      }
      e.preview = await api(`invoices/${e.invoice.id}/preview/`, "POST", {});
      e.dirty = false;
      editorPage();
    }),
  );
  on("post-invoice", "click", () =>
    act(async () => {
      e.invoice = await postAction("invoices", e.invoice);
      e.dirty = false;
      invalidate("customers");
      editorPage();
      toast(`Invoice ${e.invoice.number} posted to ${e.customer.name}.`);
    }),
  );
}
function fieldMarkup(f) {
  const value = f.value ?? "";
  if (f.options)
    return `<label>${esc(f.label)}<select name="${f.name}" ${f.required ? "required" : ""}>${!f.required ? '<option value="">None</option>' : ""}${f.options.map((o) => `<option value="${esc(o.value)}" ${String(value) === String(o.value) ? "selected" : ""}>${esc(o.label)}</option>`).join("")}</select></label>`;
  return `<label>${esc(f.label)}<input name="${f.name}" type="${f.type || "text"}" value="${esc(value)}" ${f.required ? "required" : ""} ${f.type === "number" ? `step="${f.step || ".0001"}" ${f.min !== undefined ? `min="${f.min}"` : ""}` : ""}></label>`;
}
function openForm(name, fields, submit, label = "Save", extra = "") {
  modal.innerHTML = `<div id="modal-content"><h2>${esc(name)}</h2><form id="modal-form"><div class="form-row">${fields.map(fieldMarkup).join("")}</div>${extra}<p id="modal-error" class="error"></p><div class="actions"><button class="primary" type="submit">${esc(label)}</button><button class="secondary" type="button" id="close-modal">Cancel</button></div></form></div>`;
  modal.showModal();
  on("close-modal", "click", () => modal.close());
  on("modal-form", "submit", (event) => {
    event.preventDefault();
    const originalForm = event.target;
    const formData = new FormData(originalForm);
    const values = Object.fromEntries(
      fields.map((f) => [f.name, formData.get(f.name)]),
    );
    act(async () => {
      try {
        if (
          document.querySelector("[data-lines]") &&
          !document.querySelector("#nested-rows .nested-row")
        )
          throw new Error("Add at least one line.");
        await submit(values);
        if (document.getElementById("modal-form") === originalForm)
          modal.close();
      } catch (error) {
        document.getElementById("modal-error").textContent = error.message;
        throw error;
      }
    });
  });
}
const options = (rows, label) =>
  rows.map((r) => ({ value: r.id, label: label(r) }));
async function paymentForm(customer, invoice = null) {
  const accounts = (await all("payment-accounts")).filter((a) => a.active);
  if (!accounts.length)
    throw new Error(
      "Add a cash, bank or mobile account in Settings before recording payments.",
    );
  const fields = [
    {
      name: "date",
      label: "Payment date",
      type: "date",
      value: today(),
      required: true,
    },
    {
      name: "amount",
      label: "Amount (NPR)",
      type: "number",
      min: ".01",
      step: ".01",
      value: invoice?.outstanding || "",
      required: true,
    },
    {
      name: "method",
      label: "Payment method",
      options: ["cash", "cheque", "mobile", "bank"].map((value) => ({
        value,
        label: value,
      })),
      required: true,
    },
    {
      name: "account",
      label: "Cash / bank / mobile account",
      options: options(accounts, (a) => `${a.name} · ${a.kind}`),
      required: true,
    },
    { name: "cheque_number", label: "Cheque number (for cheque)" },
    { name: "cheque_bank", label: "Cheque bank (for cheque)" },
  ];
  let receipt = null;
  let receiptPayload = null;
  openForm(
    `Record payment · ${customer.name}`,
    fields,
    async (v) => {
      const payload = {
        ...v,
        account: Number(v.account),
        customer: customer.id,
      };
      const signature = JSON.stringify(payload);
      if (!receipt) {
        receipt = await api("customer-payments/", "POST", payload);
        receiptPayload = signature;
      }
      if (receipt.status === "draft") {
        if (receiptPayload !== signature) {
          receipt = await api(`customer-payments/${receipt.id}/`, "PATCH", {
            revision: receipt.revision,
            ...payload,
          });
          receiptPayload = signature;
        }
        receipt = await postAction(
          "customer-payments",
          receipt,
          "post",
          invoice
            ? { allocations: [{ invoice: invoice.id, amount: receipt.amount }] }
            : {},
        );
      }
      invalidate("customers");
      if (invoice) await loadInvoice(invoice.id);
      else {
        state.customer = customer.id;
        await navigate("customer");
      }
      toast(
        v.method === "cheque"
          ? "Cheque recorded. Funds settle after clearance."
          : "Payment recorded in the customer account.",
      );
    },
    "Record payment",
  );
}
async function dashboardPage(version) {
  const cards = [];
  for (const [label, path, permission] of [
    ["Customers", "customers/", "invoices.view_customer"],
    ["Invoices", "invoices/", "invoices.view_invoice"],
    ["Production jobs", "job-orders/", "operations.view_joborder"],
    ["Stock balances", "stock/balances/", "operations.view_stockbalance"],
  ]) {
    if (can(permission)) {
      const data = await api(path);
      cards.push([label, data.count]);
    }
  }
  if (version !== generation) return;
  content.innerHTML =
    title(
      "Operations overview",
      "Current records from your Django server.",
      button("open-customers", "View customers", true),
    ) +
    `<div class="cards">${cards.map(([label, value]) => `<div class="card"><small>${label}</small><strong>${esc(value)}</strong><span class="hint">Live database</span></div>`).join("")}</div>` +
    panel(
      "Customer billing",
      `<p>Customers → customer account → add invoice → foam items → density groups and rates → finalize → payment.</p>`,
    );
  on("open-customers", "click", () => navigate("customers"));
}
async function initialize() {
  document.getElementById("navigation").innerHTML = pages
    .map(
      ([id, icon, name]) =>
        `<button data-page="${id}"><span>${icon}</span>${name}</button>`,
    )
    .join("");
  on("navigation", "click", (event) => {
    const node = event.target.closest("[data-page]");
    if (node && !busy) {
      state.listPage = 1;
      navigate(node.dataset.page);
    }
  });
  on("logout", "click", () =>
    act(async () => {
      await window.desktop.logout();
      state.user = null;
      state.authenticatedUserId = null;
      state.bootstrap = null;
      state.editor = null;
      state.customer = null;
      state.cache.clear();
      state.keys.clear();
      updateHeader();
      showLogin();
    }),
  );
  if (!window.desktop) {
    content.innerHTML = title(
      "Open the desktop app",
      "Start Tripathi Operations through Electron to sign in securely.",
    );
    return;
  }
  const session = await window.desktop.session();
  if (session.user) {
    state.user = session.user;
    state.authenticatedUserId = session.user.id;
    state.bootstrap = await api("bootstrap/");
    updateHeader();
    await navigate("customers");
  } else {
    updateHeader();
    showLogin();
  }
}
document.addEventListener("DOMContentLoaded", () => initialize().catch(report));

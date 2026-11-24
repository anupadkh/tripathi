const READ_ONLY = new Set([
  "payments",
  "opening-balances",
  "stock/balances",
  "stock/movements",
  "account-movements",
  "audit-events",
]);
const RESOURCES = new Set([
  "customers",
  "suppliers",
  "items",
  "locations",
  "bank-accounts",
  "payment-accounts",
  "workers",
  "fiscal-years",
  "invoices",
  "customer-payments",
  "cheques",
  "account-transfers",
  "purchase-bills",
  "goods-receipts",
  "supplier-payments",
  "stock-adjustments",
  "job-orders",
  "material-issues",
  "production-reports",
  "expense-categories",
  "expenses",
  "worksheets",
  "labour-entries",
  "payroll-runs",
  "salary-advances",
  "salary-payments",
  ...READ_ONLY,
]);
const ACTIONS = {
  invoices: ["group", "preview", "post", "cancel"],
  "customer-payments": [
    "post",
    "allocate",
    "clear",
    "bounce",
    "cancel",
    "reverse-allocations",
  ],
  cheques: ["clear", "bounce", "cancel", "reverse-allocations"],
  "supplier-payments": ["post", "clear", "bounce", "cancel"],
  "job-orders": ["post", "complete", "cancel"],
  "payroll-runs": ["calculate", "approve", "cancel"],
};
const DOCUMENTS = new Set([
  "account-transfers",
  "purchase-bills",
  "goods-receipts",
  "stock-adjustments",
  "material-issues",
  "production-reports",
  "expenses",
  "worksheets",
  "salary-advances",
  "salary-payments",
]);
function backendUrl(value) {
  if (typeof value !== "string" || value.length > 2048)
    throw new Error("Enter a valid server address.");
  const url = new URL(value);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error(
      "Use an HTTP or HTTPS server address without credentials, query or fragment.",
    );
  return url.href.replace(/\/$/, "");
}
function validateRoute(route, method = "GET") {
  if (
    typeof route !== "string" ||
    route.length > 2048 ||
    !["GET", "POST", "PATCH"].includes(method)
  )
    throw new Error("Unsupported API request.");
  const [pathname, query, ...extra] = route.split("?");
  if (
    extra.length ||
    pathname.includes("%") ||
    pathname.includes("..") ||
    pathname.includes("\\") ||
    pathname.startsWith("/")
  )
    throw new Error("Unsupported API route.");
  if (query)
    for (const key of new URLSearchParams(query).keys())
      if (
        ![
          "page",
          "search",
          "status",
          "customer",
          "supplier",
          "purchase",
          "job",
          "worker",
          "category",
          "item",
          "location",
          "account",
          "term",
          "fiscal_year",
          "is_vat",
          "from",
          "to",
          "date",
          "calendar",
        ].includes(key)
      )
        throw new Error("Unsupported API filter.");
  if (
    method === "GET" &&
    /^(bootstrap|auth\/me|health|version|dates\/convert|reports\/(sales|purchases|stock|production|expenses|payroll|cash-bank))\/$/.test(
      pathname,
    )
  )
    return;
  const match = pathname.match(
    /^([a-z-]+(?:\/(?:balances|movements))?)\/(?:([1-9]\d*)\/(?:([a-z-]+)(?:\/([1-9]\d*))?\/)?)?$/,
  );
  if (!match || !RESOURCES.has(match[1]))
    throw new Error("Unsupported API route.");
  const [, resource, id, action, group] = match;
  if (!action) {
    if (
      method === "GET" ||
      (!READ_ONLY.has(resource) &&
        ((method === "POST" && !id && resource !== "cheques") ||
          (method === "PATCH" && id && resource !== "cheques")))
    )
      return;
  } else {
    if (
      method === "GET" &&
      !group &&
      ((["customers", "suppliers"].includes(resource) &&
        action === "statement") ||
        (["payment-accounts", "bank-accounts"].includes(resource) &&
          action === "balance"))
    )
      return;
    if (
      resource === "invoices" &&
      action === "groups" &&
      group &&
      method === "PATCH"
    )
      return;
    const allowed =
      ACTIONS[resource] || (DOCUMENTS.has(resource) ? ["post", "cancel"] : []);
    if (method === "POST" && !group && allowed.includes(action)) return;
  }
  throw new Error("Unsupported API operation.");
}
function errorText(data) {
  if (!data || typeof data !== "object")
    return "The server could not complete this request.";
  return Object.entries(data)
    .map(
      ([field, value]) =>
        `${field === "detail" ? "" : field + ": "}${typeof value === "string" ? value : JSON.stringify(value)}`,
    )
    .join("\n")
    .slice(0, 1500);
}
class ApiClient {
  #token = null;
  #user = null;
  #expires = null;
  constructor(base = "http://127.0.0.1:8080", fetcher = fetch) {
    this.base = backendUrl(base);
    this.fetcher = fetcher;
  }
  clear() {
    this.#token = null;
    this.#user = null;
    this.#expires = null;
  }
  setBase(base) {
    this.base = backendUrl(base);
    this.clear();
  }
  session() {
    if (this.#expires && Date.parse(this.#expires) <= Date.now()) this.clear();
    return { user: this.#user, expires_at: this.#expires, backend: this.base };
  }
  async send(route, method = "GET", data, key, auth = true, binary = false) {
    if (auth && !this.session().user)
      return { ok: false, status: 401, error: "Sign in to continue." };
    const headers = { Accept: binary ? "application/pdf" : "application/json" };
    if (auth) headers.Authorization = `Bearer ${this.#token}`;
    if (data !== undefined) headers["Content-Type"] = "application/json";
    if (key) {
      if (typeof key !== "string" || key.length > 100)
        throw new Error("Invalid retry key.");
      headers["Idempotency-Key"] = key;
    }
    try {
      const response = await this.fetcher(`${this.base}/api/v1/${route}`, {
        method,
        headers,
        body: data === undefined ? undefined : JSON.stringify(data),
        signal: AbortSignal.timeout(20000),
        redirect: "error",
      });
      if (response.status === 401 && auth) this.clear();
      if (binary && response.ok) {
        const buffer = Buffer.from(await response.arrayBuffer());
        if (
          buffer.length > 25 * 1024 * 1024 ||
          buffer.subarray(0, 5).toString() !== "%PDF-"
        )
          throw new Error("The server did not return a valid invoice PDF.");
        return { ok: true, status: response.status, data: buffer };
      }
      const text = await response.text();
      if (text.length > 25 * 1024 * 1024)
        throw new Error("Server response is too large.");
      let body;
      try {
        body = JSON.parse(text);
      } catch {
        return {
          ok: false,
          status: response.status,
          error: `Server returned HTTP ${response.status} without a JSON API response. Check the address and server version.`,
        };
      }
      return response.ok
        ? { ok: true, status: response.status, data: body }
        : { ok: false, status: response.status, error: errorText(body) };
    } catch (error) {
      return {
        ok: false,
        status: 0,
        error: `Cannot reach the server: ${error.message}. You can retry this operation.`,
      };
    }
  }
  async login(username, password) {
    if (
      typeof username !== "string" ||
      typeof password !== "string" ||
      !username ||
      !password
    )
      return {
        ok: false,
        status: 400,
        error: "Enter your Django username and password.",
      };
    const result = await this.send(
      "auth/login/",
      "POST",
      { username, password },
      undefined,
      false,
    );
    if (result.ok) {
      const body = result.data;
      if (!body.token || !body.user || !body.expires_at)
        return {
          ok: false,
          status: 502,
          error: "The login response is incomplete.",
        };
      this.#token = body.token;
      this.#user = body.user;
      this.#expires = body.expires_at;
      return { ok: true, status: 200, data: this.session() };
    }
    return result;
  }
  async logout() {
    try {
      if (this.#token) await this.send("auth/logout/", "POST", {});
    } finally {
      this.clear();
    }
    return { ok: true };
  }
  request({ path, method = "GET", data, key } = {}) {
    validateRoute(path, method);
    return this.send(path, method, data, key);
  }
  invoicePdf(id) {
    if (!Number.isSafeInteger(id) || id < 1)
      throw new Error("Invalid invoice.");
    return this.send(
      `invoices/${id}/pdf/`,
      "GET",
      undefined,
      undefined,
      true,
      true,
    );
  }
  probe() {
    return this.send("health/", "GET", undefined, undefined, false);
  }
}
module.exports = { ApiClient, backendUrl, validateRoute };

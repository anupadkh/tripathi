const { test } = require("node:test");
const assert = require("node:assert/strict");
const { ApiClient, backendUrl, validateRoute } = require("./api-client");
const loginBody = {
  token: "test-private-token",
  expires_at: new Date(Date.now() + 3600000).toISOString(),
  user: { id: 1, username: "test", permissions: [] },
};
test("allowlisted routes reject traversal and arbitrary operations", () => {
  for (const route of [
    "customers/",
    "invoices/1/",
    "stock/balances/?item=1",
    "invoices/1/groups/2/",
  ])
    assert.doesNotThrow(() =>
      validateRoute(route, route.includes("/groups/") ? "PATCH" : "GET"),
    );
  for (const route of [
    "https://other.test/",
    "../auth/me/",
    "customers/%2e%2e/",
    "customers/1/delete/",
    "customers/?url=https://other.test",
    "invoices/1/pdf/",
  ])
    assert.throws(() => validateRoute(route));
  assert.throws(() => validateRoute("stock/movements/", "POST"));
  assert.throws(() => validateRoute("customers/", "DELETE"));
});
test("server address rejects embedded credentials and non-HTTP protocols", () => {
  assert.equal(backendUrl("http://127.0.0.1:8080/"), "http://127.0.0.1:8080");
  for (const url of [
    "file:///C:/secret",
    "http://name:password@server/",
    "https://server/?secret=x",
  ])
    assert.throws(() => backendUrl(url));
});
test("bearer token stays in the API client and is sent only to configured API", async () => {
  const calls = [];
  const client = new ApiClient(
    "http://127.0.0.1:8080",
    async (url, options) => {
      calls.push({ url, options });
      return new Response(
        JSON.stringify(
          url.endsWith("/auth/login/") ? loginBody : { results: [], count: 0 },
        ),
        { status: 200 },
      );
    },
  );
  const result = await client.login("test", "test-password");
  assert.equal(result.ok, true);
  assert.equal(result.data.token, undefined);
  assert.equal(client.session().token, undefined);
  assert.equal(JSON.stringify(client).includes("test-private-token"), false);
  await client.request({ path: "customers/" });
  assert.equal(
    calls[1].options.headers.Authorization,
    "Bearer test-private-token",
  );
  assert.equal(calls[1].url, "http://127.0.0.1:8080/api/v1/customers/");
});
test("expired or unauthorized sessions require a new login", async () => {
  const client = new ApiClient(
    "https://server.test",
    async (url) =>
      new Response(
        JSON.stringify(
          url.endsWith("/auth/login/") ? loginBody : { detail: "Expired" },
        ),
        { status: url.endsWith("/auth/login/") ? 200 : 401 },
      ),
  );
  await client.login("test", "password");
  assert.equal((await client.request({ path: "customers/" })).status, 401);
  assert.equal(client.session().user, null);
});
test("changing servers clears credentials", async () => {
  const client = new ApiClient(
    "https://old.test",
    async () => new Response(JSON.stringify(loginBody)),
  );
  await client.login("test", "password");
  client.setBase("https://new.test");
  assert.equal(client.session().user, null);
  assert.equal((await client.request({ path: "customers/" })).status, 401);
});
test("posting forwards retry keys and structured validation errors", async () => {
  let options;
  const client = new ApiClient("https://server.test", async (url, opt) => {
    options = opt;
    return new Response(
      JSON.stringify(
        url.endsWith("/auth/login/")
          ? loginBody
          : { amount: ["Payment exceeds balance."] },
      ),
      { status: url.endsWith("/auth/login/") ? 200 : 400 },
    );
  });
  await client.login("test", "password");
  const result = await client.request({
    path: "customer-payments/1/post/",
    method: "POST",
    data: { revision: 1 },
    key: "stable-key",
  });
  assert.equal(options.headers["Idempotency-Key"], "stable-key");
  assert.match(result.error, /Payment exceeds balance/);
});
test("invoice export validates IDs and PDF data", async () => {
  const client = new ApiClient("https://server.test", async (url) =>
    url.endsWith("/auth/login/")
      ? new Response(JSON.stringify(loginBody))
      : new Response("%PDF-1.7\nfixture"),
  );
  await client.login("test", "password");
  assert.throws(() => client.invoicePdf("../secret"));
  assert.equal((await client.invoicePdf(1)).ok, true);
});

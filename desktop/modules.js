const moduleConfig = {
  purchases: {
    title: "Purchases",
    description: "Supplier bills and goods received into stock.",
    resource: "purchase-bills",
    permission: "operations.view_purchasebill",
    headers: [
      "Bill no.",
      "Supplier",
      "Billed date",
      "Terms",
      "Total",
      "Status",
    ],
    row: (d) => [
      esc(d.bill_number),
      label("suppliers", d.supplier),
      esc(d.billed_date),
      esc(d.payment_method),
      money(d.total),
      pill(d.status),
    ],
    create: "operations.add_purchasebill",
  },
  inventory: {
    title: "Inventory",
    description:
      "Current item-wise stock from posted receipts, issues and production.",
    resource: "stock/balances",
    permission: "operations.view_stockbalance",
    headers: ["SKU", "Item", "Unit", "Location", "Available quantity"],
    row: (d) => [
      esc(
        state.cache.get("items")?.find((i) => i.id === d.item)?.sku || d.item,
      ),
      label("items", d.item),
      esc(state.cache.get("items")?.find((i) => i.id === d.item)?.unit || ""),
      label("locations", d.location),
      esc(d.quantity),
    ],
    create: "operations.add_stockadjustment",
  },
  production: {
    title: "Production",
    description: "Factory job orders, material issues and production reports.",
    resource: "job-orders",
    permission: "operations.view_joborder",
    headers: ["Job", "Product", "Planned quantity", "Date", "Status"],
    row: (d) => [
      `JOB-${d.id}`,
      label("items", d.product),
      esc(d.planned_quantity),
      esc(d.date),
      pill(d.completed ? "completed" : d.status),
    ],
    create: "operations.add_joborder",
  },
  expenses: {
    title: "Expenses",
    description: "Operating expenses with optional payees and job references.",
    resource: "expenses",
    permission: "operations.view_expense",
    headers: ["Date", "Category", "Payee", "Origin", "Amount", "Status"],
    row: (d) => [
      esc(d.date),
      label("expense-categories", d.category),
      esc(d.payee || "—"),
      esc(d.origin || "—"),
      money(d.amount),
      pill(d.status),
    ],
    create: "operations.add_expense",
  },
  payroll: {
    title: "Labour & payroll",
    description: "Worksheets, salary calculations, advances and payments.",
    resource: "payroll-runs",
    permission: "operations.view_payrollrun",
    headers: ["Payroll", "Period", "Expected days", "Payable", "Status"],
    row: (d) => [
      `PAY-${d.id}`,
      esc(`${d.start_date} → ${d.end_date}`),
      esc(d.expected_days),
      money(d.total),
      pill(d.status),
    ],
    create: "operations.add_payrollrun",
  },
};
function label(resource, id) {
  const row = state.cache.get(resource)?.find((r) => r.id === id);
  return esc(row?.name || row?.title || row?.sku || id || "—");
}
async function preloadMasters() {
  const permissions = {
    customers: "invoices.view_customer",
    items: "operations.view_stockitem",
    locations: "operations.view_location",
    suppliers: "operations.view_supplier",
    workers: "operations.view_worker",
    "expense-categories": "operations.view_expensecategory",
    "payment-accounts": "operations.view_paymentaccount",
  };
  await Promise.all(
    Object.entries(permissions)
      .filter(([, p]) => can(p))
      .map(([r]) => all(r)),
  );
}
async function modulePage(version) {
  const cfg = moduleConfig[state.page];
  if (!can(cfg.permission))
    throw new Error("Your account does not have access to this module.");
  await preloadMasters();
  const data = await api(`${cfg.resource}/?page=${state.listPage}`);
  if (version !== generation) return;
  const extra =
    state.page === "payroll"
      ? `${can("operations.add_worker") ? button("add-worker", "Add worker") : ""}${can("operations.add_worksheet") ? button("add-worksheet", "Record worksheet") : ""}${can("operations.add_salaryadvance") ? button("add-advance", "Salary advance") : ""}${button("show-worksheets", "Worksheets")}${button("show-advances", "Advances")}`
      : state.page === "purchases" && can("operations.add_supplier")
        ? button("add-supplier", "Add supplier")
        : "";
  content.innerHTML =
    title(
      cfg.title,
      cfg.description,
      (can(cfg.create)
        ? button(
            "module-create",
            state.page === "inventory"
              ? "Adjust stock"
              : state.page === "purchases"
                ? "+ Purchase bill"
                : state.page === "production"
                  ? "+ Job order"
                  : state.page === "expenses"
                    ? "+ Expense"
                    : "+ Payroll run",
            true,
          )
        : "") + extra,
    ) +
    panel(
      cfg.title,
      table(
        [...cfg.headers, ...(state.page === "inventory" ? [] : [""])],
        data.results.map((d) => [
          ...cfg.row(d),
          ...(state.page === "inventory"
            ? []
            : [
                `<button class="secondary" data-document="${d.id}">View</button>`,
              ]),
        ]),
      ),
    ) +
    '<div id="pager" class="pager"></div>';
  content
    .querySelectorAll("[data-document]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          act(() => viewDocument(cfg.resource, Number(b.dataset.document)))),
    );
  on("module-create", "click", () => act(() => moduleCreate(state.page)));
  on("add-supplier", "click", () => masterForm("suppliers"));
  on("add-worker", "click", () => masterForm("workers"));
  on("add-worksheet", "click", () => act(() => worksheetForm()));
  on("add-advance", "click", () => act(() => advanceForm()));
  on("show-worksheets", "click", () =>
    act(() => relatedList("worksheets", "Worksheets")),
  );
  on("show-advances", "click", () =>
    act(() => relatedList("salary-advances", "Salary advances")),
  );
  pager(data, state.listPage, async (p) => {
    state.listPage = p;
    await navigate(state.page);
  });
}
const dateField = (name = "date", text = "Date") => ({
  name,
  label: text,
  type: "date",
  value: today(),
  required: true,
});
const numberField = (name, text, value = "", min = ".0001") => ({
  name,
  label: text,
  type: "number",
  value,
  min,
  required: true,
});
const selectField = (
  name,
  text,
  rows,
  describe = (r) => r.name,
  required = true,
) => ({ name, label: text, options: options(rows, describe), required });
const itemFields = (items) => [
  selectField(
    "item",
    "Inventory item",
    items,
    (i) => `${i.sku} · ${i.name} (${i.unit})`,
  ),
  numberField("quantity", "Quantity", "1"),
  numberField("rate", "Rate (NPR)", "0", "0"),
];
function repeatingLines(fields, titleText = "Items") {
  return `<div class="line-editor" data-lines><h3>${esc(titleText)}</h3><div id="nested-rows"></div><button class="secondary" id="add-nested" type="button">+ Add line</button></div>`;
}
function bindRepeater(fields) {
  let seq = 0;
  const rows = document.getElementById("nested-rows");
  const add = () => {
    const id = ++seq;
    const node = document.createElement("div");
    node.className = "nested-row";
    node.dataset.row = id;
    node.innerHTML = `<div class="form-row">${fields.map(fieldMarkup).join("")}</div><button class="text-link" type="button">Remove line</button>`;
    node.querySelector("button").onclick = () => node.remove();
    rows.appendChild(node);
  };
  on("add-nested", "click", add);
  add();
}
function readRows() {
  return [...document.querySelectorAll("#nested-rows .nested-row")].map((row) =>
    Object.fromEntries(
      [...row.querySelectorAll("[name]")].map((node) => [
        node.name,
        node.value,
      ]),
    ),
  );
}
function requireOptions(rows, text) {
  if (!rows.length)
    throw new Error(`Add ${text} in Settings before continuing.`);
  return rows;
}
async function moduleCreate(page) {
  if (page === "purchases") {
    const suppliers = requireOptions(await all("suppliers"), "a supplier");
    const items = requireOptions(await all("items"), "inventory items");
    const fields = [
      selectField("supplier", "Supplier", suppliers),
      { name: "bill_number", label: "Supplier bill number", required: true },
      dateField("billed_date", "Billed date"),
      dateField(),
      {
        name: "payment_method",
        label: "Payment terms",
        options: ["credit", "cash", "cheque", "bank", "mobile"].map(
          (value) => ({ value, label: value }),
        ),
        required: true,
      },
      numberField("tax", "Supplier-billed tax (NPR)", "0", "0"),
      { name: "credit_bank_name", label: "Credit bank reference" },
      { name: "notes", label: "Notes" },
    ];
    const nested = itemFields(items);
    openForm(
      "Create purchase bill",
      fields,
      async (v) => {
        const lines = readRows().map((l) => ({ ...l, item: Number(l.item) }));
        if (!lines.length) throw new Error("Add at least one purchase item.");
        const doc = await api("purchase-bills/", "POST", {
          ...v,
          supplier: Number(v.supplier),
          lines,
        });
        await navigate("purchases");
        toast(`Purchase draft #${doc.id} saved. Review it before posting.`);
      },
      "Save purchase draft",
      repeatingLines(nested),
    );
    bindRepeater(nested);
  } else if (page === "inventory") {
    const items = requireOptions(await all("items"), "inventory items");
    const locations = requireOptions(
      await all("locations"),
      "a stock location",
    );
    const nested = [
      selectField("item", "Item", items),
      {
        name: "quantity",
        label: "Signed quantity (+ receive / − remove)",
        type: "number",
        required: true,
      },
    ];
    openForm(
      "Record stock adjustment",
      [
        dateField(),
        selectField("location", "Stock location", locations),
        { name: "reason", label: "Reason", required: true },
      ],
      async (v) => {
        const lines = readRows().map((l) => ({ ...l, item: Number(l.item) }));
        const doc = await api("stock-adjustments/", "POST", {
          ...v,
          location: Number(v.location),
          lines,
        });
        toast(`Adjustment draft #${doc.id} saved. Review it before posting.`);
        await navigate("inventory");
        await viewDocument("stock-adjustments", doc.id);
      },
      "Save adjustment draft",
      repeatingLines(nested),
    );
    bindRepeater(nested);
  } else if (page === "production") {
    const items = requireOptions(
      (await all("items")).filter((i) => i.kind === "finished"),
      "a finished-product item",
    );
    openForm(
      "Create factory job",
      [
        dateField(),
        selectField("product", "Finished product", items),
        numberField("planned_quantity", "Planned quantity", "1"),
        { name: "notes", label: "Job notes" },
      ],
      async (v) => {
        const doc = await api("job-orders/", "POST", {
          ...v,
          product: Number(v.product),
        });
        await navigate("production");
        toast(`Job #${doc.id} saved. Open it to release production.`);
      },
      "Save job draft",
    );
  } else if (page === "expenses") {
    const categories = requireOptions(
      await all("expense-categories"),
      "an expense category",
    );
    const accounts = requireOptions(
      await all("payment-accounts"),
      "a payment account",
    );
    openForm(
      "Record expense",
      [
        dateField(),
        selectField("category", "Expense category", categories),
        numberField("amount", "Amount (NPR)", "", ".01"),
        selectField(
          "account",
          "Payment account",
          accounts,
          (a) => `${a.name} · ${a.kind}`,
        ),
        { name: "payee", label: "Payee / third party (optional)" },
        { name: "origin", label: "Origin / reference (optional)" },
        { name: "notes", label: "Description" },
      ],
      async (v) => {
        const doc = await api("expenses/", "POST", {
          ...v,
          category: Number(v.category),
          account: Number(v.account),
        });
        await navigate("expenses");
        toast(`Expense #${doc.id} saved. Review it before posting.`);
      },
      "Save expense draft",
    );
  } else if (page === "payroll") {
    openForm(
      "Create payroll run",
      [
        dateField("start_date", "Period start"),
        dateField("end_date", "Period end"),
        numberField("expected_days", "Expected working days", "26", "1"),
        { name: "notes", label: "Payroll notes" },
      ],
      async (v) => {
        const doc = await api("payroll-runs/", "POST", {
          ...v,
          expected_days: Number(v.expected_days),
        });
        await navigate("payroll");
        toast(
          `Payroll #${doc.id} saved. Calculate and review before approval.`,
        );
      },
      "Save payroll draft",
    );
  }
}
async function worksheetForm() {
  const workers = requireOptions(await all("workers"), "workers");
  const nested = [
    selectField("worker", "Worker", workers),
    numberField("units", "Days / hours / pieces", "1"),
    numberField("overtime_hours", "Overtime hours", "0", "0"),
  ];
  openForm(
    "Record worksheet",
    [
      dateField(),
      { name: "description", label: "Work performed", required: true },
    ],
    async (v) => {
      const doc = await api("worksheets/", "POST", {
        ...v,
        entries: readRows().map((l) => ({ ...l, worker: Number(l.worker) })),
      });
      toast(`Worksheet #${doc.id} saved.`);
      await viewDocument("worksheets", doc.id);
    },
    "Save worksheet draft",
    repeatingLines(nested, "Labour entries"),
  );
  bindRepeater(nested);
}
async function advanceForm() {
  const workers = requireOptions(await all("workers"), "workers");
  const accounts = requireOptions(
    await all("payment-accounts"),
    "payment accounts",
  );
  openForm(
    "Salary advance",
    [
      dateField(),
      selectField("worker", "Worker", workers),
      selectField("account", "Payment account", accounts),
      numberField("amount", "Advance (NPR)", "", ".01"),
    ],
    async (v) => {
      const doc = await api("salary-advances/", "POST", {
        ...v,
        worker: Number(v.worker),
        account: Number(v.account),
      });
      toast(`Advance #${doc.id} saved.`);
      await viewDocument("salary-advances", doc.id);
    },
    "Save advance draft",
  );
}
async function relatedList(resource, titleText, query = "") {
  const data = await api(`${resource}/?${query}`);
  modal.innerHTML = `<div id="modal-content"><h2>${esc(titleText)}</h2>${table(
    ["Record", "Date", "Status", ""],
    data.results.map((d) => [
      `#${d.id}`,
      esc(d.date),
      pill(d.status),
      `<button class="secondary" data-related="${d.id}">View</button>`,
    ]),
  )}<p>${data.count} records; showing ${data.results.length}.</p>${button("close-related", "Close")}</div>`;
  if (!modal.open) modal.showModal();
  modal
    .querySelectorAll("[data-related]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          act(() => viewDocument(resource, Number(b.dataset.related)))),
    );
  on("close-related", "click", () => modal.close());
}
function documentBody(resource, d) {
  const summaryFields = {
    "purchase-bills": [
      ["Supplier", label("suppliers", d.supplier)],
      ["Bill number", esc(d.bill_number)],
      ["Total", money(d.total)],
    ],
    "job-orders": [
      ["Product", label("items", d.product)],
      ["Planned output", esc(d.planned_quantity)],
      ["Completed", d.completed ? "Yes" : "No"],
    ],
    expenses: [
      ["Category", label("expense-categories", d.category)],
      ["Payee", esc(d.payee || "—")],
      ["Amount", money(d.amount)],
    ],
    "customer-payments": [
      ["Customer", label("customers", d.customer)],
      ["Method", esc(d.method)],
      ["Cheque status", d.method === "cheque" ? pill(d.cheque_status) : "—"],
      ["Amount", money(d.amount)],
    ],
    "salary-advances": [
      ["Worker", label("workers", d.worker)],
      ["Amount", money(d.amount)],
    ],
    "production-reports": [
      ["Job", `JOB-${d.job}`],
      ["Finished output", esc(d.produced_quantity)],
    ],
    "material-issues": [
      ["Job", `JOB-${d.job}`],
      ["Location", label("locations", d.location)],
    ],
    "goods-receipts": [
      ["Purchase", `#${d.purchase}`],
      ["Received", esc(d.received_date)],
    ],
    "stock-adjustments": [
      ["Reason", esc(d.reason)],
      ["Location", label("locations", d.location)],
    ],
    "supplier-payments": [
      ["Supplier", label("suppliers", d.supplier)],
      ["Amount", money(d.amount)],
      ["Method", esc(d.method)],
    ],
    "salary-payments": [
      ["Payroll line", esc(d.payroll_line)],
      ["Amount", money(d.amount)],
    ],
    "account-transfers": [
      ["From", label("payment-accounts", d.source_account)],
      ["To", label("payment-accounts", d.destination_account)],
      ["Amount", money(d.amount)],
    ],
    worksheets: [["Work", esc(d.description)]],
    "payroll-runs": [
      ["Period", esc(`${d.start_date} → ${d.end_date}`)],
      ["Expected days", esc(d.expected_days)],
      ["Total net pay", money(d.total)],
    ],
  };
  let html = table(
    ["Field", "Value"],
    summaryFields[resource] || [["Date", esc(d.date)]],
  );
  if (d.lines?.length)
    html +=
      resource === "payroll-runs"
        ? table(
            [
              "Worker",
              "Units",
              "Base pay",
              "Overtime",
              "Deductions",
              "Advances",
              "Net pay",
              "",
            ],
            d.lines.map((l) => [
              label("workers", l.worker),
              esc(l.units),
              money(l.base_pay),
              money(l.overtime_pay),
              money(l.deductions),
              money(l.advances),
              money(l.net_pay),
              d.status === "posted"
                ? `<button class="secondary" data-pay-salary="${l.id}">Pay salary</button>`
                : "",
            ]),
          )
        : table(
            ["Item / purchase line", "Quantity", "Rate", "Amount"],
            d.lines.map((l) => [
              l.item ? label("items", l.item) : esc(l.purchase_line),
              esc(l.quantity),
              esc(l.rate ?? "—"),
              l.amount === undefined ? "—" : money(l.amount),
            ]),
          );
  if (d.entries?.length)
    html += table(
      ["Worker", "Work units", "Overtime hours"],
      d.entries.map((l) => [
        label("workers", l.worker),
        esc(l.units),
        esc(l.overtime_hours),
      ]),
    );
  if (d.consumption?.length)
    html += table(
      ["Material", "Consumed", "Waste"],
      d.consumption.map((l) => [
        label("items", l.item),
        esc(l.consumed_quantity),
        esc(l.waste_quantity),
      ]),
    );
  if (d.allocations?.length)
    html += table(
      ["Invoice", "Amount", "Status"],
      d.allocations.map((a) => [
        esc(a.invoice),
        money(a.amount),
        a.reversed ? "Reversed" : "Allocated",
      ]),
    );
  return html + `<p>${esc(d.notes || "")}</p>`;
}
async function viewDocument(resource, id) {
  const d = await api(`${resource}/${id}/`);
  const controls = [button("close-document", "Close")];
  if (d.status === "draft")
    controls.push(
      button(
        "post-document",
        resource === "payroll-runs"
          ? "Approve payroll"
          : resource === "job-orders"
            ? "Release job"
            : "Post document",
        true,
      ),
    );
  if (resource === "payroll-runs" && d.status === "draft")
    controls.push(button("calculate-payroll", "Calculate payroll"));
  if (d.status === "posted" && resource === "purchase-bills") {
    controls.push(
      button("receive-items", "Receive items"),
      button("pay-supplier", "Pay supplier"),
    );
  }
  if (d.status === "posted" && resource === "job-orders" && !d.completed)
    controls.push(
      button("issue-materials", "Issue materials"),
      button("production-report", "Record production"),
      button("complete-job", "Complete job"),
    );
  if (
    d.status === "posted" &&
    ["customer-payments", "supplier-payments"].includes(resource) &&
    d.method === "cheque" &&
    d.cheque_status !== "bounced"
  )
    controls.push(
      ...(d.cheque_status === "pending"
        ? [button("clear-cheque", "Clear cheque")]
        : []),
      button("bounce-cheque", "Bounce cheque"),
    );
  if (
    d.status === "posted" &&
    resource === "customer-payments" &&
    d.allocations.some((a) => !a.reversed)
  )
    controls.push(button("reverse-allocations", "Reverse allocations"));
  if (
    d.status === "posted" &&
    resource === "customer-payments" &&
    d.cheque_status !== "bounced" &&
    Number(d.unallocated_amount) > 0
  )
    controls.push(button("allocate-receipt", "Allocate to invoice"));
  if (d.status !== "cancelled")
    controls.push(button("cancel-document", "Cancel document"));
  modal.innerHTML = `<div id="modal-content"><h2>${esc(resource.replaceAll("-", " "))} #${d.id} · ${pill(d.status)}</h2>${documentBody(resource, d)}<p id="modal-error" class="error"></p><div class="actions">${controls.join("")}</div></div>`;
  if (!modal.open) modal.showModal();
  on("close-document", "click", () => modal.close());
  const finish = async () => {
    await navigate(state.page);
    toast("Saved to the server.");
  };
  on("post-document", "click", () =>
    act(async () => {
      if (resource === "payroll-runs" && !d.lines.length)
        throw new Error("Calculate and review payroll before approving it.");
      await postAction(
        resource,
        d,
        resource === "payroll-runs" ? "approve" : "post",
      );
      await viewDocument(resource, id);
      await finish();
    }),
  );
  on("calculate-payroll", "click", () =>
    act(async () => {
      await postAction(resource, d, "calculate");
      await viewDocument(resource, id);
    }),
  );
  on("receive-items", "click", () => act(() => goodsReceiptForm(d)));
  on("pay-supplier", "click", () => act(() => supplierPaymentForm(d)));
  on("issue-materials", "click", () => act(() => issueForm(d)));
  on("production-report", "click", () => act(() => productionForm(d)));
  on("complete-job", "click", () =>
    act(async () => {
      await postAction(resource, d, "complete");
      await viewDocument(resource, id);
      await finish();
    }),
  );
  for (const [id, action] of [
    ["clear-cheque", "clear"],
    ["bounce-cheque", "bounce"],
  ])
    on(id, "click", () =>
      openForm(
        `${action === "clear" ? "Clear" : "Bounce"} cheque`,
        [dateField()],
        async (v) => {
          await postAction(resource, d, action, v);
          await finish();
        },
        "Save cheque status",
      ),
    );
  on("cancel-document", "click", () =>
    openForm(
      "Cancel and reverse document",
      [{ name: "reason", label: "Reason", required: true }, dateField()],
      async (v) => {
        await postAction(resource, d, "cancel", v);
        await finish();
      },
      "Cancel and reverse",
    ),
  );
  on("reverse-allocations", "click", () =>
    openForm(
      "Reverse active allocations",
      [{ name: "reason", label: "Reason", required: true }],
      async (v) => {
        await postAction(resource, d, "reverse-allocations", {
          ...v,
          allocation_ids: d.allocations
            .filter((a) => !a.reversed)
            .map((a) => a.id),
        });
        await finish();
      },
      "Reverse allocations",
    ),
  );
  on("allocate-receipt", "click", () => act(() => allocationForm(d)));
  modal
    .querySelectorAll("[data-pay-salary]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          act(() =>
            salaryPaymentForm(
              d.lines.find((l) => l.id === Number(b.dataset.paySalary)),
            ),
          )),
    );
}
async function allocationForm(receipt) {
  let page = 1,
    invoices = [];
  while (true) {
    const data = await api(
      `invoices/?customer=${receipt.customer}&status=posted&page=${page}`,
    );
    invoices.push(
      ...data.results.filter(
        (i) => Number(i.outstanding) > Number(i.pending_payment || 0),
      ),
    );
    if (!data.next) break;
    page++;
  }
  requireOptions(invoices, "a posted invoice with an unpaid balance");
  openForm(
    "Allocate customer receipt",
    [
      selectField(
        "invoice",
        "Invoice",
        invoices,
        (i) =>
          `${i.number || i.vat_bill_no || "#" + i.id} · Outstanding ${money(i.outstanding)}`,
      ),
      numberField(
        "amount",
        "Amount to allocate (NPR)",
        receipt.unallocated_amount,
        ".01",
      ),
    ],
    async (values) => {
      await postAction("customer-payments", receipt, "allocate", {
        allocations: [
          { invoice: Number(values.invoice), amount: values.amount },
        ],
      });
      await navigate(state.page);
      toast("Receipt allocated to the invoice.");
    },
    "Allocate payment",
  );
}
async function goodsReceiptForm(purchase) {
  const locations = requireOptions(await all("locations"), "stock locations");
  const fields = [
    dateField("received_date", "Received date"),
    selectField("location", "Stock location", locations),
  ];
  const nested = [
    selectField(
      "purchase_line",
      "Purchase item",
      purchase.lines,
      (l) =>
        `${label("items", l.item).replaceAll("&amp;", "&")} · Ordered ${l.quantity}`,
    ),
    numberField("quantity", "Received quantity", "1"),
  ];
  openForm(
    "Receive purchased items",
    fields,
    async (v) => {
      const doc = await api("goods-receipts/", "POST", {
        ...v,
        purchase: purchase.id,
        location: Number(v.location),
        lines: readRows().map((l) => ({
          ...l,
          purchase_line: Number(l.purchase_line),
        })),
      });
      toast(`Receipt #${doc.id} saved. Post it to add stock.`);
      await viewDocument("goods-receipts", doc.id);
    },
    "Save receipt draft",
    repeatingLines(nested),
  );
  bindRepeater(nested);
}
async function supplierPaymentForm(purchase) {
  const accounts = requireOptions(
    await all("payment-accounts"),
    "payment accounts",
  );
  openForm(
    "Record supplier payment",
    [
      dateField(),
      numberField("amount", "Amount (NPR)", "", ".01"),
      selectField("account", "Payment account", accounts),
      {
        name: "method",
        label: "Method",
        options: ["cash", "bank", "mobile", "cheque"].map((value) => ({
          value,
          label: value,
        })),
        required: true,
      },
      { name: "cheque_number", label: "Cheque number" },
      { name: "cheque_bank", label: "Cheque bank" },
    ],
    async (v) => {
      const doc = await api("supplier-payments/", "POST", {
        ...v,
        account: Number(v.account),
        supplier: purchase.supplier,
        purchase: purchase.id,
      });
      await viewDocument("supplier-payments", doc.id);
    },
    "Save payment draft",
  );
}
async function issueForm(job) {
  const items = requireOptions(
    (await all("items")).filter((i) => i.kind !== "finished"),
    "raw materials",
  );
  const locations = requireOptions(await all("locations"), "stock locations");
  const nested = [
    selectField("item", "Material", items),
    numberField("quantity", "Quantity issued", "1"),
  ];
  openForm(
    "Issue factory materials",
    [dateField(), selectField("location", "Source location", locations)],
    async (v) => {
      const doc = await api("material-issues/", "POST", {
        ...v,
        job: job.id,
        location: Number(v.location),
        lines: readRows().map((l) => ({ ...l, item: Number(l.item) })),
      });
      await viewDocument("material-issues", doc.id);
    },
    "Save material issue",
    repeatingLines(nested),
  );
  bindRepeater(nested);
}
async function productionForm(job) {
  const items = requireOptions(
    (await all("items")).filter((i) => i.kind !== "finished"),
    "raw materials",
  );
  const locations = requireOptions(await all("locations"), "stock locations");
  const nested = [
    selectField("item", "Material", items),
    numberField("consumed_quantity", "Consumed", "0", "0"),
    numberField("waste_quantity", "Waste", "0", "0"),
  ];
  openForm(
    "Record production",
    [
      dateField(),
      selectField("location", "Finished stock location", locations),
      numberField("produced_quantity", "Finished quantity", "1"),
    ],
    async (v) => {
      const doc = await api("production-reports/", "POST", {
        ...v,
        job: job.id,
        location: Number(v.location),
        consumption: readRows().map((l) => ({ ...l, item: Number(l.item) })),
      });
      await viewDocument("production-reports", doc.id);
    },
    "Save production report",
    repeatingLines(nested, "Material consumption"),
  );
  bindRepeater(nested);
}
async function salaryPaymentForm(line) {
  const accounts = requireOptions(
    await all("payment-accounts"),
    "payment accounts",
  );
  openForm(
    "Pay salary",
    [
      dateField(),
      selectField("account", "Payment account", accounts),
      numberField("amount", "Salary payment (NPR)", line.net_pay, ".01"),
    ],
    async (v) => {
      const doc = await api("salary-payments/", "POST", {
        ...v,
        account: Number(v.account),
        payroll_line: line.id,
      });
      await viewDocument("salary-payments", doc.id);
    },
    "Save salary payment",
  );
}
const masterFields = {
  suppliers: [
    { name: "name", label: "Supplier name", required: true },
    { name: "address", label: "Address" },
    { name: "phone", label: "Phone" },
    { name: "pan", label: "PAN" },
    {
      name: "opening_balance",
      label: "Opening balance (NPR)",
      type: "number",
      value: "0",
      step: ".01",
    },
  ],
  items: [
    { name: "sku", label: "SKU", required: true },
    { name: "name", label: "Item name", required: true },
    {
      name: "kind",
      label: "Item type",
      options: ["raw", "finished", "consumable"].map((value) => ({
        value,
        label: value,
      })),
      required: true,
    },
    { name: "unit", label: "Stock unit", value: "piece", required: true },
    { name: "density", label: "Density (foam)" },
  ],
  locations: [{ name: "name", label: "Location name", required: true }],
  "expense-categories": [
    { name: "name", label: "Category name", required: true },
  ],
  "payment-accounts": [
    { name: "name", label: "Account name", required: true },
    {
      name: "kind",
      label: "Account type",
      options: ["cash", "bank", "mobile"].map((value) => ({
        value,
        label: value,
      })),
      required: true,
    },
    { name: "bank_name", label: "Bank / provider name" },
    { name: "account_number", label: "Account number" },
    {
      name: "opening_balance",
      label: "Opening balance (NPR)",
      type: "number",
      value: "0",
      step: ".01",
    },
  ],
  workers: [
    { name: "name", label: "Worker name", required: true },
    { name: "phone", label: "Phone" },
    {
      name: "salary_basis",
      label: "Salary basis",
      options: ["monthly", "daily", "hourly", "piece"].map((value) => ({
        value,
        label: value,
      })),
      required: true,
    },
    numberField("rate", "Base rate (NPR)", "0", "0"),
    numberField("overtime_rate", "Overtime rate per hour (NPR)", "0", "0"),
  ],
  "fiscal-years": [
    { name: "title", label: "Fiscal-year title", required: true },
    dateField("start_date", "Start date"),
    dateField("end_date", "End date"),
  ],
};
function masterForm(resource) {
  openForm(
    `Add ${resource.replaceAll("-", " ")}`,
    masterFields[resource],
    async (v) => {
      await api(`${resource}/`, "POST", v);
      invalidate(resource);
      if (resource === "fiscal-years")
        state.bootstrap = await api("bootstrap/");
      await navigate(state.page);
      toast("Record saved.");
    },
    "Save",
  );
}
async function settingsPage(version) {
  const settings = await window.desktop.readSettings();
  if (version !== generation) return;
  const masters = [
    ["fiscal-years", "Fiscal year", "invoices.add_term"],
    [
      "payment-accounts",
      "Cash / bank / mobile account",
      "operations.add_paymentaccount",
    ],
    ["items", "Inventory item", "operations.add_stockitem"],
    ["locations", "Stock location", "operations.add_location"],
    ["suppliers", "Supplier", "operations.add_supplier"],
    [
      "expense-categories",
      "Expense category",
      "operations.add_expensecategory",
    ],
    ["workers", "Worker", "operations.add_worker"],
  ];
  content.innerHTML =
    title(
      "Connection & settings",
      "Choose your server and maintain business records.",
    ) +
    panel(
      "Business server",
      `<label for="backend">Server address</label><input id="backend" type="url" value="${esc(settings.backend)}"><div class="actions">${button("save-settings", "Save connection", true)}${button("probe", "Test connection")}</div><p id="connection-status" role="status">Changing servers signs you out.</p>`,
    ) +
    (state.user
      ? panel(
          "Add business records",
          `<div class="actions wrap">${masters
            .filter(([, , p]) => can(p))
            .map(
              ([r, label]) =>
                `<button class="secondary" data-master="${r}">+ ${label}</button>`,
            )
            .join(
              "",
            )}</div><p>Opening stock and account balances should match your reviewed business balances.</p>${can("operations.add_accounttransfer") ? button("cash-deposit", "Transfer cash / bank funds") : ""}`,
        )
      : button("back-login", "Back to sign in", true));
  on("probe", "click", () =>
    act(async () => {
      const result = await window.desktop.probeBackend(
        document.getElementById("backend").value,
      );
      document.getElementById("connection-status").textContent = result.message;
    }),
  );
  on("save-settings", "click", () =>
    act(async () => {
      const value = document.getElementById("backend").value.trim();
      await window.desktop.saveSettings(value);
      const session = await window.desktop.session();
      if (!session.user) {
        state.user = null;
        state.bootstrap = null;
        state.editor = null;
        state.cache.clear();
        state.keys.clear();
        updateHeader();
        showLogin("Connection saved. Sign in to this server.");
      } else toast("Connection saved.");
    }),
  );
  on("back-login", "click", () => showLogin());
  content
    .querySelectorAll("[data-master]")
    .forEach((b) => (b.onclick = () => masterForm(b.dataset.master)));
  on("cash-deposit", "click", () =>
    act(async () => {
      const accounts = requireOptions(
        await all("payment-accounts"),
        "payment accounts",
      );
      openForm(
        "Transfer funds",
        [
          dateField(),
          selectField("source_account", "From account", accounts),
          selectField("destination_account", "To account", accounts),
          numberField("amount", "Amount (NPR)", "", ".01"),
        ],
        async (v) => {
          const doc = await api("account-transfers/", "POST", {
            ...v,
            source_account: Number(v.source_account),
            destination_account: Number(v.destination_account),
          });
          await viewDocument("account-transfers", doc.id);
        },
        "Save transfer draft",
      );
    }),
  );
}

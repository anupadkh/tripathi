# Tripathi Operations desktop

Electron is connected to the Django APIs. Sign in with your existing Django username and password. Business records are read from and written to the selected server; the app no longer displays sample data or creates local demo bills. Previously saved demo bills are left untouched and are not imported into your business accounts.

## Start

From the repository root, start the business server:

```powershell
.\run_backend.bat
```

The launcher defaults to `http://127.0.0.1:8080`. Set `TRIPATHI_API_PORT` to use a different port. A separately running Django server can use any configured address; enter its base URL on the sign-in screen or in Settings. Existing saved connection settings are preserved. Select the intended database on the Django server, not in the desktop client. See `../operations/README.md` before migrating an existing database.

Run the desktop source:

```powershell
cd desktop
npm install
npm start
```

Or use the Windows installer in `dist/Tripathi Operations Setup 0.2.0.exe`.

The installer contains the desktop client. Django must run separately, either on this computer or on your office server. It does not bundle Python or migrate your existing database. The default development database may be empty; sign into the server that contains your intended customer records.

## Customer-first billing

1. Customers opens after login. Search or page through the customer list.
2. Open a customer to see account totals, regular invoices, VAT invoices, payment history and opening balances.
3. Select **Add new invoice**. The customer is fixed for that invoice. Your configured fiscal year is used when available.
4. Enter individual foam items with density, dimensions or manual mm, quantity, unit and taxability. Optionally link an inventory item and location.
5. Save a draft or continue to density groups. For dimensional mm billing, Django calculates `length × breadth × height / 2592 × pieces`; compatible density/unit/taxability groups are combined. Enter group rates at this second stage.
6. Select **Save rates & calculate** to review Django's totals, then **Finalize invoice** to post it.
7. Record cash, cheque, bank or mobile payments. An unpaid invoice remains credit. A payment entered from the invoice view is posted and allocated atomically. Pending cheques reserve payment capacity and settle only on clearance.
8. View, print or export the posted invoice. Posted invoices are protected; cancellation creates guarded reversals.

Saved API drafts can be reopened from the invoice list. The current unsaved draft can be resumed through Invoices. Existing historical invoices are readable and printable. Historical payments that were not linked to invoices remain visible in the customer account; their per-invoice allocation requires review.

## Other live screens

- Purchases: add suppliers, save/review/post purchase bills, record receipts and supplier payments.
- Inventory: view stock balances; create/review/post signed stock adjustments.
- Production: save and release jobs, issue materials, record production consumption/waste and finished output, complete reconciled jobs.
- Expenses: save/review/post operating expenses with optional third-party information.
- Labour/payroll: create workers, worksheets, salary advances and payroll runs; calculate/review/approve payroll and record salary payments.
- Settings: manage the server address and add fiscal years, items, locations, payment accounts and categories; record account transfers.

These screens use the existing API business rules and permissions. Draft documents must be posted or approved to affect stock/cash/payroll. Domain corrections, advanced payroll rules and historical consolidation retain the limits documented in the backend README.

## Security and retries

Bearer tokens stay in the Electron main process and expire according to server settings. Passwords and tokens are not saved to files or renderer storage. Signing out revokes the token; changing servers clears the session. The preload bridge exposes a restricted set of operations, and the API proxy validates paths/methods. Renderer Node integration remains disabled with context isolation and sandboxing enabled. Invoice PDFs are fetched with authentication and saved only through the native Save dialog.

Write requests use server revisions and stable retry keys. Record creation and posting support idempotent retries; a stale revision produces a conflict instead of overwriting another user's work. If a draft edit conflicts, reload the saved draft and review it before retrying.

## Verification and packaging

```powershell
npm run check
npm test
npm run smoke
npm run dist
```

`smoke` launches a hidden Electron window against a temporary Django database, seeds synthetic records, and tests actual login, customer pagination/detail, dimensional billing, stock deduction, server totals, posting, cash allocation, PDF export, live module reads, purchase creation/posting, and logout. It does not use your business database. It requires the project's Python environment (or `TRIPATHI_TEST_PYTHON`). Results are written to `smoke-result.txt`; a UI preview is written to `integration-preview.png`. Both are ignored by Git.

The development build dependencies still report moderate npm audit findings. Review packaging dependencies before production distribution; custom installer branding and code-signing configuration remain separate release steps.

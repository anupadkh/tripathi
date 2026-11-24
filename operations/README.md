# Django operations backend

The backend exposes `/api/v1/` alongside the existing admin and invoice pages. The first implementation covers billing, customer/supplier payments, banking, purchase receipts, stock movements, factory production, expenses, labour and payroll. Domain code lives in one `operations` Django app with shared posting services; the existing `invoices` app retains historical records.

## Setup on Windows

Use Python 3.12 or newer compatible with the pinned packages. From the repository root:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py createsuperuser
.venv\Scripts\python.exe manage.py setup_roles
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

This selects `db.sqlite3` by default. To select the existing VAT database, use `vat_manage.py` in place of `manage.py`, or explicitly set `DJANGO_DB_PATH`. Back up an existing database before migrating it:

```powershell
$env:DJANGO_DB_PATH = 'C:\code\webapps\tripathi\db2.sqlite3'
.venv\Scripts\python.exe manage.py backup_database --output 'C:\code\webapps\tripathi\vat-before-api.sqlite3'
.venv\Scripts\python.exe manage.py migrate
```

`backup_database` creates a consistent SQLite backup and refuses to overwrite a file. For PostgreSQL, use the server's backup tooling. Do not run the development server as your production service.

Migration rehearsals were run on copies of `backup.sqlite3` and `db2.sqlite3`. The original databases were not migrated or merged. The migration rounds amounts to two decimal places and rates/quantities to four using half-up rounding, preserves IDs and balances at that precision, backfills posted states and unambiguous fiscal years, and consolidates duplicate counters before adding a unique constraint. Historical VAT flags are retained for review rather than automatically reclassifying old sales.

The two original datasets have separate IDs and histories. Choose the database for this installation; combining them requires an explicit mapping/reconciliation project. Historical item records remain invoice lines; new stock starts with posted receipts or reviewed opening-stock adjustments. Historical payments are not automatically assigned to individual invoices or bank accounts.

## Configuration

See `.env.example` at the repository root. Environment variables are read directly; `.env` is a template and is not automatically loaded. Set `DJANGO_SECRET_KEY` and `DJANGO_DEBUG=0` for deployment, and configure allowed hosts. HTTPS is required for remote token use. `POSTGRES_DB` selects PostgreSQL; otherwise SQLite uses immediate transactions and a 20-second busy timeout.

This is a single-company installation. Billing, Factory, Accounts and Payroll groups are created by `setup_roles`; assign users through Django admin. It does not grant access to any user automatically. Model view/add/change permissions apply to APIs; posted records and ledger rows cannot be deleted through the APIs. New operations records are read-only in admin so posting rules cannot be bypassed. The standard Django admin replaces the obsolete material admin theme.

Financial posting and reversals acquire a shared posting lock, then document/domain locks. This serializes postings across users in this installation; draft editing and reads remain separate. Use PostgreSQL for a shared multi-user server. PostgreSQL settings are implemented, but the automated suite and migration rehearsals were run on SQLite.

## Authentication and API conventions

- `GET health/` is public and returns `{"status":"ok"}` after checking the database.
- `POST auth/login/` accepts username/password and returns an expiring bearer token. Only its SHA-256 digest is stored on the server. Send `Authorization: Bearer <token>` on subsequent requests.
- `GET auth/me/`, `POST auth/logout/` and `GET bootstrap/` provide current identity, revocation and app configuration. Tokens expire after `API_TOKEN_HOURS` (default 8). Existing Django users and passwords continue to work.
- Session authentication remains available with CSRF protection for writes. The login endpoint issues tokens and does not create a session cookie. Login attempts are throttled; shared production workers should use a shared Django cache for coordinated throttling.
- List resources are paginated. Supported filters are implemented per resource: `status`, `customer`, `supplier`, `purchase`, `job`, `worker`, `category`, plus `from`/`to` date filters where the resource has a document date. Invoice lists additionally support `fiscal_year`; stock lists support item/location and account movements support account.
- JSON decimal values are strings. Dates are Gregorian ISO dates. `GET dates/convert/?calendar=ad&date=2026-10-10` converts dates to/from Nepali dates (`calendar=bs` for Nepali input).
- Update a document with `PATCH` and its current `revision`. Supply a fresh `Idempotency-Key` header and the current revision for every posting/state action. Retrying an identical request with the same key returns the original result. Changed payloads/paths with an already used key return 409. A stale revision returns 409. Retry a busy-database response with the same key.
- The server calculates invoice totals, VAT, group quantities, purchase totals and payroll. Inputs to server-managed fields are rejected.
- `GET schema/`, `GET docs/` and `operations/openapi.yaml` describe the API. Swagger UI may require internet access for its UI assets. The OpenAPI file works with offline tooling.

## Example: two-stage bill

1. Create a customer through `customers/` and a fiscal year through `fiscal-years/` (or use existing IDs).
2. Create a draft through `POST invoices/`:

```json
{
  "issued_for": 1,
  "fiscal_year": 1,
  "date": "2026-10-10",
  "is_vat": true,
  "vat_rate": "13.00",
  "discount": "0.00",
  "credit_bank_name": "",
  "lines": [
    {"density":"28","description":"Foam A","qty":"2","unit":"piece","taxable":true},
    {"density":"28","description":"Foam B","qty":"3","unit":"piece","taxable":true}
  ]
}
```

3. `POST invoices/{id}/group/` with `{"revision":1}` and a retry key. Compatible density/unit/taxability groups are combined.
4. `PATCH invoices/{id}/groups/{group_id}/` with the returned revision and `{"rate":"100.00"}` (include revision in the same body).
5. `POST invoices/{id}/preview/` to review totals. A discount is allocated proportionally across taxable and non-taxable amounts; group rates are tax-exclusive. The configured rate is a business input, not a legal tax determination.
6. `POST invoices/{id}/post/` with the newest revision/retry key. The server assigns a unique fiscal-year/series number and posts any linked stock issues atomically.
7. `GET invoices/{id}/pdf/` exports a basic printable invoice. The initial PDF uses standard Latin fonts; a reviewed Nepali font/layout is needed for Nepali-language printing.

Each line may include both `stock_item` and `location`. The line's unit and density must match that stock item. Without both fields it is a non-stock line. This avoids inventing stock mappings for historical foam descriptions. No dimension/unit conversion is inferred: submit quantities in the selected unit. The legacy form still computes its existing dimensional quantity formula on the server.

Credit is the unpaid balance; `credit_bank_name` records an optional reference and does not create money. The API does not implement bank loan accounting.

## Payments and banking

Create cash, bank and mobile accounts through `payment-accounts/`. Separate accounts support multiple banks/providers. Opening balances and account types are locked after movements exist.

Create `customer-payments/` with customer, date, amount, method and account; post it before allocating. Methods are `cash`, `bank`, `mobile` and `cheque`; the account type must match. Cheques require `cheque_number` and `cheque_bank`.

`POST customer-payments/{id}/allocate/` takes revision and an `allocations` list of invoice/amount pairs. It supports partial and split payments, enforces customer matching, and prevents over-allocation. Pending cheques reserve payment capacity, while invoice `outstanding` stays unpaid and `pending_payment` shows the reserved amount. `clear/` and `bounce/` require an event date. Only clearance affects accounts and creates the legacy payment mirror. A later bounce reverses that movement and restores the receivable. Supplier cheque actions follow the same lifecycle.

`reverse-allocations/` accepts revision, allocation_ids and reason, retaining allocation history. Cancel a receipt only after reversing its allocations. Cancelling a settled receipt reverses its ledger movement and zeroes the legacy payment mirror while retaining both records.

`account-transfers/` has source_account, destination_account, date and amount. Posting moves money without creating a customer payment or sales income. Account balances and movements are available through `payment-accounts/{id}/balance/`, `account-movements/` and `reports/cash-bank/`. Debit postings enforce non-negative available funds.

## Purchases and inventory

- `purchase-bills/`: supplier, bill_number, billed_date, date, payment_method (`cash`, `credit`, `cheque`, `bank`, `mobile`), optional credit_bank_name, supplier-billed tax and lines (item, quantity, rate). Posting calculates the total; payment_method records intended terms and does not automatically pay the supplier.
- `supplier-payments/`: supplier, optional purchase, amount, method/account and cheque information where applicable. Posting/clearance moves money and prevents paying a purchase beyond its balance. Supplier statements distinguish unsettled cheques from settled payments.
- `goods-receipts/`: purchase, received_date, location and lines (purchase_line, quantity). Posting checks ownership and quantities remaining, supports partial delivery and creates item-wise stock.
- `items/` and `locations/`: inventory masters. Stock item unit/density/type are locked after use.
- `stock-adjustments/`: location, reason and signed item/quantity lines. Use a reviewed positive adjustment for opening stock; negative adjustments cannot exceed available stock.
- `stock/balances/` and `stock/movements/`: read-only stock data. Purchase receipt, production receipt, material issue, sale and reversal movements update balances atomically.

Stock valuation, landed costs, stock transfers and purchase/sales return documents are not part of this initial quantity ledger.

## Factory, expenses and payroll

Post `job-orders/` with finished product and planned_quantity. Post `material-issues/` with job, location and item/quantity lines. These remove materials from stores once. A `production-reports/` document records job, finished-stock location, produced_quantity and consumption lines (item, consumed_quantity, waste_quantity). Posting validates against issued material and receives finished goods. It does not deduct materials twice. `job-orders/{id}/complete/` requires a posted report and all issued materials accounted for as consumption/waste.

Post `expenses/` with category, amount, account and optional payee, origin, job or worksheet. Third-party information is optional. Payroll payments are their own expense stream; do not manually create a second expense for the same salary payment. Expense reports cover general operating expenses; payroll reports show salary calculations and payments are tracked separately.

Workers have salary_basis (`monthly`, `daily`, `hourly`, `piece`), rate and overtime_rate. Post a `worksheets/` document with description, optional job and entries (worker, units, overtime_hours). Units mean attendance days for monthly/daily workers, hours for hourly workers, or output quantity for piece workers. Approved payroll prevents late posting/cancellation of covering worksheets.

Create `payroll-runs/` with start_date, end_date, expected_days and optional adjustments (worker, kind allowance/deduction, amount, reason). `calculate/` produces a draft breakdown; `approve/` recalculates and freezes it. Monthly pay is prorated by recorded days / expected_days; other bases multiply units by rate. Overtime uses overtime_rate. Posted, unsettled `salary-advances/` are deducted once and attached to the approved run. Overlapping approved payroll for a worker is rejected. Create/post `salary-payments/` only for approved payroll lines; partial payments are allowed, overpayment is rejected. Statutory deductions and policy-specific leave/overtime rules need explicit business configuration.

## Corrections, reports and auditing

Every document exposes `cancel/` with revision, reason and optional reversal date. Posted invoices, receipts, transfers, stock entries and expenses are corrected through reversals. Dependencies must be reversed first: payments/receipts before a purchase; salary payments before payroll; payroll before its worksheets. Reversals that would make cash/stock negative fail and roll back. Completed factory jobs are locked; reopen/correction handling requires a separate reviewed workflow.

`reports/sales/`, `purchases/`, `stock/`, `production/`, `expenses/`, `payroll/` and `cash-bank/` provide summaries under model permissions. `customers/{id}/statement/` uses historical opening balances and payment records; optional fiscal_year selects a specific period. Historical unallocated payments affect customer statements but cannot infer individual invoice balances. `suppliers/{id}/statement/` uses supplier opening balance, posted bills and settled payments. `audit-events/` retains actors, actions, requests and resulting document snapshots. No ordinary API deletion is offered.

## Verification

```powershell
.venv\Scripts\python.exe manage.py check
.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.venv\Scripts\python.exe manage.py test operations
.venv\Scripts\python.exe manage.py spectacular --file operations/openapi.yaml --validate
.venv\Scripts\python.exe scripts/verify_migrations.py
```

The migration rehearsal script uses SQLite backup copies, compares every rounded financial field and row ID, checks posted states and foreign keys, and verifies source-file hashes after the rehearsal. It never migrates the supplied source files. The test suite covers posting retries, transaction rollback, concurrency, billing, cheques, transfers, stock, purchases, production, payroll, reversals, permissions and legacy forms.

The existing Electron app can now probe this backend's health endpoint. Its business screens still run in local demo mode; wiring login and live API workflows into Electron is the next frontend step. Packaging/bundling Django into the installer is a separate deployment step.

The fresh local db.sqlite3 development database has been initialized with migrations and the four permission groups. It contains no customer records or login accounts. Create your own login with manage.py createsuperuser. run_backend.bat starts the local development API after checking that migrations are applied. Existing VAT/backup databases remain unchanged. Restore your pre-migration backup if you need to recover original floating-point precision; reversing schema migrations cannot undo rounding.

## Live desktop integration

The Electron client now uses the Django APIs for login, customers, invoices, payments and the other module screens. It follows the existing admin flow: customer list → customer account → Add New Invoice → foam items → density grouping/rates → posting/payment. The desktop no longer uses local demo data for business operations. See `../desktop/README.md` for launch instructions; `run_backend.bat` now defaults to port 8080 (override with `TRIPATHI_API_PORT`).

Customer lists support search and expose a permission-checked account balance; bootstrap supplies the user's configured billing fiscal year. Read-only `payments/` and `opening-balances/` resources expose existing customer histories. Invoice responses include the customer name and original stock links so saved drafts can be reopened without losing inventory links.

API dimensional lines may use unit `mm`. Django then derives billed quantity from the existing length/breadth/height formula or manual mm, while retaining piece counts for linked stock items with unit `piece`. Group quantities and invoice totals remain server-calculated. This replaces the earlier limitation requiring pre-converted dimensional quantities from clients.

Resource creation now accepts optional Idempotency-Key headers. Customer receipt posting accepts an optional allocations list and performs posting/allocation in the same transaction. PDF export negotiates `application/pdf`. The desktop keeps credentials in its main process and uses a restricted API proxy instead of direct renderer networking.

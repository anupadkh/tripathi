# Django changes for the Electron application

## Architecture and deployment

Keep Django and Django REST Framework as the business backend. Electron provides the desktop interface. Use one Django server and PostgreSQL for multiple office/factory computers; an office LAN does not require internet access. For a single computer, a bundled Django service and SQLite are possible. Do not give each client a separate database without designing synchronization.

The initial Electron implementation lives in `desktop/`. It has a local demo workflow and a configurable backend connection. Demo records do not update Django. Existing template routes are retained; the APIs below must be implemented before live business workflows are enabled. The initial renderer uses plain JavaScript and CSS, avoiding a frontend compilation dependency. React/TypeScript can be introduced as the interface grows.

## Existing backend issues to address first

- `requirements.txt` pins Django below 4.2. Upgrade to a supported release, preferably Django 5.2 LTS, after checking Python and admin plugin compatibility. Pin tested dependencies.
- `invoices/views.py` accepts financial totals from the browser. Recalculate totals, discounts, VAT and balances on the server.
- Invoice/item saves and invoice numbering are not atomic. Add transactions and concurrency-safe numbering with unique constraints per fiscal year and bill series.
- `Invoice.save()` currently treats a missing VAT bill number as VAT. Replace the conditional with explicit validated bill type rules.
- Payments reference customers but lack invoice allocations, bank accounts and cheque clearance information.
- `settings.py` and `vatBillsettings.py` use different databases. Inspect both and back them up before consolidating; account for overlapping IDs and invoice numbers.
- Move secrets and environment-dependent settings out of source; disable debug for deployed services and configure allowed hosts.

## Models and business services

Split new capabilities into billing, payments, purchases, inventory, production, expenses and payroll apps. Reuse business service functions from both APIs and admin.

| Area | Changes |
| --- | --- |
| Money | DecimalField amounts/rates; explicit precision, currency and rounding; reviewed float-to-decimal data migration |
| Billing | Draft, grouped, posted, cancelled states; original foam lines; density groups with consistent units, combined quantities and rates |
| Payments | Bank/payment accounts, receipts, invoice allocations, cheque number/bank/status, partial and split payments |
| Credit | Customer outstanding balance; clarify separately whether bank-financed credit is required |
| Transfers | Cash-to-bank account movements that do not create income or settle an invoice twice |
| Purchases | Suppliers, bills, lines, supplier payments, separate partial goods receipts |
| Inventory | Item masters, density/unit attributes, locations and stock movement ledger; balances from posted movements |
| Production | Job orders, material issues, actual consumption/waste, production reports, finished-stock receipts |
| Expenses | Categories, optional third-party payee, references and optional job/worksheet links |
| Payroll | Workers, worksheets, attendance/work entries, salary rules, advances, deductions, payroll runs and payments |
| Controls | Role permissions, audit events, document revisions, reversal records and protected posted documents |

Posting must validate and apply document, financial and stock effects in one transaction. Support idempotency keys on posting/payment operations and revision checks on updates. Use reversals or correction documents for posted records. Use PROTECT where deleting a referenced party would destroy financial history. Prevent payroll and expense records from counting the same labour payment twice.

Preserve fiscal-year opening balances. Store canonical Gregorian dates and expose validated Nepali date conversion for input/display. Define quantity conversions before combining foam of the same density.

## API contract

Prefix every endpoint with `/api/v1/`. Resource endpoints provide paginated list/detail/create/update operations subject to permissions and document state. Do not allow ordinary deletion of posted records.

| Module | Endpoints |
| --- | --- |
| Auth | POST auth/login/, POST auth/logout/, GET auth/me/ |
| Bootstrap | GET bootstrap/ (company, fiscal year, permissions, units, rates) |
| Masters | customers/, suppliers/, items/, bank-accounts/, payment-accounts/, workers/, fiscal-years/ |
| Billing | invoices/, POST invoices/{id}/group/, PATCH invoices/{id}/groups/{group_id}/, POST invoices/{id}/preview/, POST invoices/{id}/post/, POST invoices/{id}/cancel/ |
| Receipts | customer-payments/, POST customer-payments/{id}/allocate/, GET customers/{id}/statement/ |
| Banking | cheques/, POST cheques/{id}/clear/, POST cheques/{id}/bounce/, account-transfers/ |
| Purchases | purchase-bills/, goods-receipts/, POST goods-receipts/{id}/post/, supplier-payments/, GET suppliers/{id}/statement/ |
| Stock | GET stock/balances/, GET stock/movements/, stock-adjustments/, POST stock-adjustments/{id}/post/ |
| Production | job-orders/, material-issues/, production-reports/, POST production-reports/{id}/post/, POST job-orders/{id}/complete/ |
| Expenses | expense-categories/, expenses/, POST expenses/{id}/post/ |
| Labour | worksheets/, labour-entries/, payroll-runs/, POST payroll-runs/{id}/calculate/, POST payroll-runs/{id}/approve/, salary-payments/ |
| Reports | reports/sales/, reports/purchases/, reports/cash-bank/, reports/stock/, reports/production/, reports/expenses/, reports/payroll/ |
| Desktop | GET health/, GET version/, GET invoices/{id}/pdf/ |

Use decimal strings in JSON, ISO dates, stable IDs, field-level validation errors and explicit document status. Support filters for fiscal year, date range, customer, supplier, item and status. Document contracts with OpenAPI. Never trust totals or permissions supplied by the desktop.

Define authentication before enabling writes. Session authentication needs CSRF handling; token authentication needs expiry/revocation and protected credential storage. Require authentication by default, filter accessible querysets and enforce object/action permissions. Restrict origins instead of enabling wildcard CORS.

## Desktop integration

Use contextIsolation, renderer sandboxing and disabled Node integration. Expose only named operations through preload. Validate IPC arguments; the renderer cannot execute shell commands or access arbitrary files. Restrict navigation and backend protocols. Keep tokens out of localStorage. Use HTTPS for remote deployment. Loopback HTTP is suitable for a local service.

The desktop connection probe expects GET health/ to return JSON containing `status: "ok"`. The probe does not authenticate or enable live writes. Settings persist in Electron's userData directory. Demo data persists locally in the renderer and can be reset.

For packaged local backend mode, add Python/service bundling, authenticated loopback access, migrations, startup health checks, graceful shutdown and database backups. For shared-server mode, package the client independently. Backups/restores are administrator operations; do not expose unrestricted filesystem paths through HTTP.

## Implementation order and validation

1. Back up and assess both databases; upgrade Django and repair calculations/numbering.
2. Implement authentication, permissions, bootstrap and master-record APIs.
3. Implement two-stage billing, customer payments and printable invoices.
4. Add purchases and inventory receipt/issue ledger.
5. Add production, expenses, worksheets and payroll.
6. Add reports, audited corrections, installer and update strategy.

Test grouping/unit conversion, decimal rounding, invoice numbering under concurrency, transaction rollback, duplicate retries, payment allocations, partial receipts, stock consumption, production receipt and payroll cost reconciliation. Reconcile migrated customer balances and bill totals before switching users.

## References

- Django supported versions: https://www.djangoproject.com/download/#supported-versions
- DRF viewsets: https://www.django-rest-framework.org/api-guide/viewsets/
- Electron security: https://www.electronjs.org/docs/latest/tutorial/security

## Implementation status

The Django backend is now implemented in `operations/` and the existing `invoices` app. See `operations/README.md` for setup, API examples, migration guidance and practical limits. The running API and `operations/openapi.yaml` are the current contract.

Implemented: Django 5.2 upgrade, decimal migration, expiring bearer authentication, roles, two-stage billing and PDF export, payment allocations and cheque lifecycle, cash/bank transfers, purchases and partial receipts, quantity inventory ledger, job orders/material issues/production reports, expenses, worksheets, salary advances/calculations/payments, reports, audit events and guarded reversals. Critical state actions require revisions and idempotency keys. New domain models share one operations app and posting service layer.

Migration rehearsals pass on copies of both existing SQLite datasets. Original files remain unchanged. Historical database consolidation, stock item mapping, historical invoice payment allocation, advanced stock valuation/return workflows, business-specific payroll rules and final Nepali invoice layout remain explicit follow-up work. PostgreSQL configuration is available; integration tests currently use SQLite. Electron business screens remain in demo mode until live API integration is implemented.

## Frontend integration status

The desktop is now connected to live Django APIs and follows the admin's customer-first billing workflow. Authentication, customer search/pagination, customer histories, invoice drafts/dimensional entry/group pricing, posting, payments and PDF export are wired. Other module screens now display live records and provide domain forms/posting actions. See `desktop/README.md` for the current workflow and setup. Earlier references to the desktop being demo-only are superseded by this integration.

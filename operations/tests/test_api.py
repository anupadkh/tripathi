from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase
from invoices.models import Customer, Invoice, Term, Payment
from operations import models as m
from operations.services import account_balance


class OperationsApiTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            "owner", "owner@example.test", "test-password"
        )
        self.client.force_authenticate(self.user)
        self.customer = Customer.objects.create(name="Customer A")
        self.year = Term.objects.create(
            title="Test year", start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
        )
        self.cash = m.PaymentAccount.objects.create(
            name="Cash", kind="cash", opening_balance=Decimal("10000")
        )
        self.bank = m.PaymentAccount.objects.create(
            name="Bank", kind="bank", bank_name="Test bank"
        )
        self.location = m.Location.objects.create(name="Store")
        self.raw = m.StockItem.objects.create(
            sku="RAW", name="Chemical", kind="raw", unit="kg"
        )
        self.foam = m.StockItem.objects.create(
            sku="FOAM28", name="Foam", kind="finished", density="28", unit="piece"
        )

    def create(self, resource, data):
        response = self.client.post(f"/api/v1/{resource}/", data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def action(self, resource, obj, action="post", extra=None, key=None, expected=200):
        data = {"revision": obj["revision"], **(extra or {})}
        response = self.client.post(
            f"/api/v1/{resource}/{obj['id']}/{action}/",
            data,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key or str(uuid4()),
        )
        self.assertEqual(response.status_code, expected, response.data)
        return response.data

    def invoice(self, stock=False):
        lines = [
            {
                "density": "28",
                "description": "Foam A",
                "qty": "2",
                "unit": "piece",
                "taxable": True,
            },
            {
                "density": "28",
                "description": "Foam B",
                "qty": "3",
                "unit": "piece",
                "taxable": True,
            },
        ]
        if stock:
            for line in lines:
                line.update(stock_item=self.foam.pk, location=self.location.pk)
        invoice = self.create(
            "invoices",
            {
                "issued_for": self.customer.pk,
                "date": "2026-10-10",
                "fiscal_year": self.year.pk,
                "is_vat": True,
                "lines": lines,
            },
        )
        invoice = self.action("invoices", invoice, "group")
        self.assertEqual(len(invoice["groups"]), 1)
        self.assertEqual(Decimal(invoice["groups"][0]["quantity"]), 5)
        response = self.client.patch(
            f"/api/v1/invoices/{invoice['id']}/groups/{invoice['groups'][0]['id']}/",
            {"revision": invoice["revision"], "rate": "100"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def receipt(self, amount="100", method="cash"):
        data = {
            "customer": self.customer.pk,
            "date": "2026-10-10",
            "amount": amount,
            "method": method,
            "account": self.cash.pk if method == "cash" else self.bank.pk,
        }
        if method == "cheque":
            data.update(cheque_number="CH001", cheque_bank="Test bank")
        receipt = self.create("customer-payments", data)
        return self.action("customer-payments", receipt)

    def seed_stock(self, item, qty):
        adjustment = self.create(
            "stock-adjustments",
            {
                "date": "2026-10-10",
                "location": self.location.pk,
                "reason": "Opening stock",
                "lines": [{"item": item.pk, "quantity": qty}],
            },
        )
        return self.action("stock-adjustments", adjustment)

    def test_health_and_auth_permissions(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/api/v1/health/").data["status"], "ok")
        self.assertEqual(self.client.get("/api/v1/invoices/").status_code, 401)
        user = User.objects.create_user("limited", password="test-password")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get("/api/v1/invoices/").status_code, 403)
        self.assertEqual(
            self.client.post("/api/v1/invoices/", {}, format="json").status_code, 403
        )

    def test_expiring_token_logout(self):
        self.client.force_authenticate(None)
        response = self.client.post(
            "/api/v1/auth/login/",
            {"username": "owner", "password": "test-password"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        token = response.data["token"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/auth/logout/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)
        self.assertFalse(m.AccessToken.objects.filter(digest=token).exists())

    def test_billing_calculations_post_retry_and_immutability(self):
        invoice = self.invoice()
        key = "invoice-post"
        posted = self.action("invoices", invoice, key=key)
        self.assertEqual(posted["total"], "565.00")
        self.assertEqual(posted["tax"], "65.00")
        self.assertEqual(
            self.action("invoices", invoice, key=key)["number"], posted["number"]
        )
        self.assertEqual(m.DocumentSequence.objects.get().value, 1)
        response = self.client.patch(
            f"/api/v1/invoices/{invoice['id']}/",
            {"revision": posted["revision"], "notes": "changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            self.client.delete(f"/api/v1/invoices/{invoice['id']}/").status_code, 405
        )
        self.assertEqual(
            self.client.get(f"/api/v1/invoices/{invoice['id']}/pdf/").status_code, 200
        )

    def test_server_totals_cannot_be_forged(self):
        response = self.client.post(
            "/api/v1/invoices/",
            {
                "issued_for": self.customer.pk,
                "date": "2026-10-10",
                "fiscal_year": self.year.pk,
                "total": "1",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_stale_revision_and_reused_key(self):
        invoice = self.invoice()
        self.action("invoices", invoice, extra={"revision": 1}, expected=409)
        posted = self.action("invoices", invoice, key="one-key")
        self.action(
            "invoices",
            posted,
            "cancel",
            {"reason": "Wrong bill"},
            key="one-key",
            expected=409,
        )

    def test_posting_requires_retry_key(self):
        invoice = self.invoice()
        response = self.client.post(
            f"/api/v1/invoices/{invoice['id']}/post/",
            {"revision": invoice["revision"]},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_split_allocations_and_overpayment_rollback(self):
        invoice = self.action("invoices", self.invoice())
        first = self.receipt("200")
        second = self.receipt("365")
        self.action(
            "customer-payments",
            first,
            "allocate",
            {"allocations": [{"invoice": invoice["id"], "amount": "200"}]},
        )
        self.action(
            "customer-payments",
            second,
            "allocate",
            {"allocations": [{"invoice": invoice["id"], "amount": "365"}]},
        )
        self.assertEqual(
            Decimal(
                self.client.get(f"/api/v1/invoices/{invoice['id']}/").data[
                    "outstanding"
                ]
            ),
            0,
        )
        extra = self.receipt("1")
        self.action(
            "customer-payments",
            extra,
            "allocate",
            {"allocations": [{"invoice": invoice["id"], "amount": "1"}]},
            expected=400,
        )
        self.assertEqual(m.PaymentAllocation.objects.count(), 2)
        statement = self.client.get(
            f"/api/v1/customers/{self.customer.pk}/statement/"
        ).data
        self.assertEqual(Decimal(statement["balance"]), Decimal("-1"))

    def test_cheques_do_not_move_money_until_clearance(self):
        receipt = self.receipt("100", "cheque")
        self.assertEqual(account_balance(self.bank), 0)
        self.assertEqual(Payment.objects.count(), 0)
        cleared = self.action(
            "customer-payments", receipt, "clear", {"date": "2026-10-11"}
        )
        self.assertEqual(account_balance(self.bank), 100)
        self.assertEqual(Payment.objects.count(), 1)
        self.action(
            "customer-payments", cleared, "clear", {"date": "2026-10-11"}, expected=400
        )

    def test_bounced_cheque_releases_allocated_credit(self):
        invoice = self.action("invoices", self.invoice())
        receipt = self.receipt("100", "cheque")
        allocated = self.action(
            "customer-payments",
            receipt,
            "allocate",
            {"allocations": [{"invoice": invoice["id"], "amount": "100"}]},
        )
        self.action("customer-payments", allocated, "bounce", {"date": "2026-10-11"})
        self.assertEqual(
            Decimal(
                self.client.get(f"/api/v1/invoices/{invoice['id']}/").data[
                    "outstanding"
                ]
            ),
            565,
        )
        self.assertEqual(Payment.objects.count(), 0)

    def test_cash_to_bank_is_transfer_not_customer_payment(self):
        transfer = self.create(
            "account-transfers",
            {
                "date": "2026-10-10",
                "source_account": self.cash.pk,
                "destination_account": self.bank.pk,
                "amount": "1000",
            },
        )
        self.action("account-transfers", transfer, key="transfer")
        self.action("account-transfers", transfer, key="transfer")
        self.assertEqual(account_balance(self.cash), 9000)
        self.assertEqual(account_balance(self.bank), 1000)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(m.AccountMovement.objects.count(), 2)

    def test_failed_stock_post_rolls_back_bill_number_and_all_movements(self):
        invoice = self.invoice(stock=True)
        self.action("invoices", invoice, expected=400)
        self.assertEqual(m.DocumentSequence.objects.count(), 0)
        self.assertEqual(m.StockMovement.objects.count(), 0)
        self.assertEqual(Invoice.objects.get(pk=invoice["id"]).status, "grouped")

    def test_sale_stock_and_cancel_reversal(self):
        self.seed_stock(self.foam, "10")
        posted = self.action("invoices", self.invoice(stock=True))
        self.assertEqual(m.StockBalance.objects.get(item=self.foam).quantity, 5)
        self.action("invoices", posted, "cancel", {"reason": "Order cancelled"})
        self.assertEqual(m.StockBalance.objects.get(item=self.foam).quantity, 10)
        self.assertEqual(Invoice.objects.get().to_pay, 0)

    def test_purchase_partial_receipts_and_overreceipt(self):
        supplier = m.Supplier.objects.create(name="Supplier")
        purchase = self.create(
            "purchase-bills",
            {
                "supplier": supplier.pk,
                "bill_number": "PUR1",
                "billed_date": "2026-10-09",
                "date": "2026-10-09",
                "payment_method": "credit",
                "tax": "13",
                "lines": [{"item": self.raw.pk, "quantity": "10", "rate": "10"}],
            },
        )
        purchase = self.action("purchase-bills", purchase)
        self.assertEqual(purchase["total"], "113.00")

        def receipt(qty):
            return self.create(
                "goods-receipts",
                {
                    "purchase": purchase["id"],
                    "received_date": "2026-10-10",
                    "location": self.location.pk,
                    "lines": [
                        {"purchase_line": purchase["lines"][0]["id"], "quantity": qty}
                    ],
                },
            )

        self.action("goods-receipts", receipt("4"))
        self.action("goods-receipts", receipt("7"), expected=400)
        self.assertEqual(m.StockBalance.objects.get(item=self.raw).quantity, 4)
        self.action("goods-receipts", receipt("6"))
        self.assertEqual(m.StockBalance.objects.get(item=self.raw).quantity, 10)

    def test_production_issues_consumption_and_output(self):
        self.seed_stock(self.raw, "20")
        job = self.create(
            "job-orders",
            {"date": "2026-10-10", "product": self.foam.pk, "planned_quantity": "10"},
        )
        job = self.action("job-orders", job)
        issue = self.create(
            "material-issues",
            {
                "date": "2026-10-10",
                "job": job["id"],
                "location": self.location.pk,
                "lines": [{"item": self.raw.pk, "quantity": "5"}],
            },
        )
        self.action("material-issues", issue)
        report = self.create(
            "production-reports",
            {
                "date": "2026-10-10",
                "job": job["id"],
                "location": self.location.pk,
                "produced_quantity": "10",
                "consumption": [
                    {
                        "item": self.raw.pk,
                        "consumed_quantity": "4",
                        "waste_quantity": "1",
                    }
                ],
            },
        )
        self.action("production-reports", report)
        self.assertEqual(m.StockBalance.objects.get(item=self.raw).quantity, 15)
        self.assertEqual(m.StockBalance.objects.get(item=self.foam).quantity, 10)
        self.assertTrue(self.action("job-orders", job, "complete")["completed"])

    def test_expense_optional_payee_and_insufficient_funds(self):
        category = m.ExpenseCategory.objects.create(name="Food")
        expense = self.create(
            "expenses",
            {
                "date": "2026-10-10",
                "category": category.pk,
                "amount": "100",
                "account": self.cash.pk,
            },
        )
        self.action("expenses", expense)
        self.assertEqual(account_balance(self.cash), 9900)
        expense = self.create(
            "expenses",
            {
                "date": "2026-10-10",
                "category": category.pk,
                "amount": "10000",
                "account": self.cash.pk,
            },
        )
        self.action("expenses", expense, expected=400)
        self.assertEqual(account_balance(self.cash), 9900)

    def test_payroll_advance_deduction_payment_and_no_double_salary(self):
        worker = m.Worker.objects.create(
            name="Worker",
            salary_basis="daily",
            rate=Decimal("100"),
            overtime_rate=Decimal("50"),
        )
        worksheet = self.create(
            "worksheets",
            {
                "date": "2026-10-10",
                "description": "Factory shift",
                "entries": [{"worker": worker.pk, "units": "2", "overtime_hours": "1"}],
            },
        )
        self.action("worksheets", worksheet)
        advance = self.create(
            "salary-advances",
            {
                "date": "2026-10-10",
                "worker": worker.pk,
                "amount": "50",
                "account": self.cash.pk,
            },
        )
        self.action("salary-advances", advance)
        run = self.create(
            "payroll-runs",
            {
                "date": "2026-10-10",
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
                "expected_days": 26,
                "adjustments": [
                    {
                        "worker": worker.pk,
                        "kind": "deduction",
                        "amount": "10",
                        "reason": "Deduction",
                    }
                ],
            },
        )
        run = self.action("payroll-runs", run, "approve")
        self.assertEqual(run["total"], "190.00")
        self.assertEqual(m.SalaryAdvance.objects.get().settled_in_id, run["id"])
        payment = self.create(
            "salary-payments",
            {
                "date": "2026-10-10",
                "payroll_line": run["lines"][0]["id"],
                "amount": "190",
                "account": self.cash.pk,
            },
        )
        self.action("salary-payments", payment)
        self.assertEqual(account_balance(self.cash), 9760)
        extra = self.create(
            "salary-payments",
            {
                "date": "2026-10-10",
                "payroll_line": run["lines"][0]["id"],
                "amount": "1",
                "account": self.cash.pk,
            },
        )
        self.action("salary-payments", extra, expected=400)
        self.assertEqual(m.Expense.objects.count(), 0)
        duplicate = self.create(
            "payroll-runs", {"start_date": "2026-10-01", "end_date": "2026-10-31"}
        )
        self.action("payroll-runs", duplicate, "approve", expected=400)

    def test_report_and_schema_routes(self):
        for report in [
            "sales",
            "purchases",
            "stock",
            "production",
            "expenses",
            "payroll",
            "cash-bank",
        ]:
            response = self.client.get(f"/api/v1/reports/{report}/")
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.client.get("/api/v1/schema/").status_code, 200)

    def test_legacy_vat_missing_number(self):
        invoice = Invoice.objects.create(issued_for=self.customer, vat_bill_no=None)
        self.assertFalse(invoice.is_vat)

    def test_pending_cheque_has_separate_outstanding_and_reserved_amount(self):
        invoice = self.action("invoices", self.invoice())
        receipt = self.receipt("100", "cheque")
        self.action(
            "customer-payments",
            receipt,
            "allocate",
            {"allocations": [{"invoice": invoice["id"], "amount": "100"}]},
        )
        response = self.client.get(f"/api/v1/invoices/{invoice['id']}/")
        self.assertEqual(Decimal(response.data["outstanding"]), 565)
        self.assertEqual(Decimal(response.data["pending_payment"]), 100)

    def test_receipt_allocation_reversal_and_cancellation_preserve_history(self):
        invoice = self.action("invoices", self.invoice())
        receipt = self.receipt("100")
        receipt = self.action(
            "customer-payments",
            receipt,
            "allocate",
            {"allocations": [{"invoice": invoice["id"], "amount": "100"}]},
        )
        self.action(
            "customer-payments",
            receipt,
            "cancel",
            {"reason": "Wrong receipt", "date": "2026-10-11"},
            expected=400,
        )
        receipt = self.action(
            "customer-payments",
            receipt,
            "reverse-allocations",
            {
                "allocation_ids": [receipt["allocations"][0]["id"]],
                "reason": "Wrong allocation",
            },
        )
        self.action(
            "customer-payments",
            receipt,
            "cancel",
            {"reason": "Wrong receipt", "date": "2026-10-11"},
        )
        self.assertTrue(m.PaymentAllocation.objects.get().reversed)
        self.assertEqual(account_balance(self.cash), 10000)
        self.assertEqual(Payment.objects.get().amount, 0)
        self.assertEqual(
            Decimal(
                self.client.get(f"/api/v1/invoices/{invoice['id']}/").data[
                    "outstanding"
                ]
            ),
            565,
        )

    def test_cleared_cheque_bounce_reverses_deposit(self):
        receipt = self.receipt("100", "cheque")
        receipt = self.action(
            "customer-payments", receipt, "clear", {"date": "2026-10-11"}
        )
        self.action("customer-payments", receipt, "bounce", {"date": "2026-10-12"})
        self.assertEqual(account_balance(self.bank), 0)
        self.assertEqual(Payment.objects.get().amount, 0)
        self.assertEqual(m.AccountMovement.objects.count(), 2)

    def test_expense_cancel_reverses_cash_once(self):
        category = m.ExpenseCategory.objects.create(name="Food")
        expense = self.create(
            "expenses",
            {
                "date": "2026-10-10",
                "category": category.pk,
                "amount": "100",
                "account": self.cash.pk,
            },
        )
        expense = self.action("expenses", expense)
        self.action(
            "expenses",
            expense,
            "cancel",
            {"date": "2026-10-11", "reason": "Duplicate entry"},
            key="reverse-expense",
        )
        self.action(
            "expenses",
            expense,
            "cancel",
            {"date": "2026-10-11", "reason": "Duplicate entry"},
            key="reverse-expense",
        )
        self.assertEqual(account_balance(self.cash), 10000)
        self.assertEqual(m.AccountMovement.objects.count(), 2)

    def test_transfer_cancel_preserves_both_balances(self):
        transfer = self.create(
            "account-transfers",
            {
                "date": "2026-10-10",
                "source_account": self.cash.pk,
                "destination_account": self.bank.pk,
                "amount": "1000",
            },
        )
        transfer = self.action("account-transfers", transfer)
        self.action(
            "account-transfers",
            transfer,
            "cancel",
            {"date": "2026-10-11", "reason": "Wrong deposit"},
        )
        self.assertEqual(account_balance(self.cash), 10000)
        self.assertEqual(account_balance(self.bank), 0)

    def test_duplicate_receipt_lines_rejected(self):
        supplier = m.Supplier.objects.create(name="Supplier")
        purchase = self.create(
            "purchase-bills",
            {
                "supplier": supplier.pk,
                "bill_number": "P1",
                "billed_date": "2026-10-10",
                "payment_method": "cash",
                "lines": [{"item": self.raw.pk, "quantity": "10", "rate": "1"}],
            },
        )
        purchase = self.action("purchase-bills", purchase)
        line = {"purchase_line": purchase["lines"][0]["id"], "quantity": "6"}
        response = self.client.post(
            "/api/v1/goods-receipts/",
            {
                "purchase": purchase["id"],
                "received_date": "2026-10-10",
                "location": self.location.pk,
                "lines": [line, line],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(m.GoodsReceipt.objects.exists())

    def test_grouping_keeps_units_and_taxability_separate(self):
        invoice = self.create(
            "invoices",
            {
                "issued_for": self.customer.pk,
                "date": "2026-10-10",
                "fiscal_year": self.year.pk,
                "lines": [
                    {"density": "28", "qty": "1", "unit": "piece", "taxable": True},
                    {"density": "28", "qty": "1", "unit": "kg", "taxable": True},
                    {"density": "28", "qty": "1", "unit": "piece", "taxable": False},
                ],
            },
        )
        invoice = self.action("invoices", invoice, "group")
        self.assertEqual(len(invoice["groups"]), 3)

    def test_stock_item_unit_is_locked_after_use(self):
        self.seed_stock(self.raw, "10")
        response = self.client.patch(
            f"/api/v1/items/{self.raw.pk}/", {"unit": "piece"}, format="json"
        )
        self.assertEqual(response.status_code, 400)
        self.raw.refresh_from_db()
        self.assertEqual(self.raw.unit, "kg")

    def test_payroll_prevents_late_worksheet_posting(self):
        worker = m.Worker.objects.create(name="Worker", salary_basis="daily", rate=100)
        worksheet = self.create(
            "worksheets",
            {
                "date": "2026-10-10",
                "description": "Shift",
                "entries": [{"worker": worker.pk, "units": "1"}],
            },
        )
        self.action("worksheets", worksheet)
        run = self.create(
            "payroll-runs", {"start_date": "2026-10-01", "end_date": "2026-10-31"}
        )
        self.action("payroll-runs", run, "approve")
        late = self.create(
            "worksheets",
            {
                "date": "2026-10-11",
                "description": "Late shift",
                "entries": [{"worker": worker.pk, "units": "1"}],
            },
        )
        self.action("worksheets", late, expected=400)

    def test_labour_entry_cannot_modify_posted_worksheet(self):
        worker = m.Worker.objects.create(name="Worker", salary_basis="daily", rate=100)
        worksheet = self.create(
            "worksheets",
            {
                "date": "2026-10-10",
                "description": "Shift",
                "entries": [{"worker": worker.pk, "units": "1"}],
            },
        )
        worksheet = self.action("worksheets", worksheet)
        response = self.client.patch(
            f"/api/v1/labour-entries/{worksheet['entries'][0]['id']}/",
            {"units": "2"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_decimal_preview_and_report_use_strings_in_json(self):
        invoice = self.invoice()
        preview = self.client.post(
            f"/api/v1/invoices/{invoice['id']}/preview/", {}, format="json"
        )
        import json

        self.assertEqual(json.loads(preview.content)["total"], "565.00")
        self.action("invoices", invoice)
        report = self.client.get("/api/v1/reports/sales/")
        self.assertEqual(json.loads(report.content)["total"], "565.00")

    def test_nepali_date_round_trip(self):
        response = self.client.get(
            "/api/v1/dates/convert/", {"calendar": "ad", "date": "2026-10-10"}
        )
        self.assertEqual(response.status_code, 200, response.data)
        reverse = self.client.get(
            "/api/v1/dates/convert/", {"calendar": "bs", "date": response.data["bs"]}
        )
        self.assertEqual(reverse.data["ad"], "2026-10-10")
        self.assertEqual(
            self.client.get(
                "/api/v1/dates/convert/", {"calendar": "bs", "date": "invalid"}
            ).status_code,
            400,
        )

    def test_legacy_form_recalculates_and_rejects_posted_edits(self):
        from invoices.models import UserSystem

        UserSystem.objects.create(user=self.user, billing_term=self.year)
        self.client.force_login(self.user)
        import json

        data = {
            "items": json.dumps(
                [
                    {
                        "density": "28",
                        "description": "Foam",
                        "qty": 2,
                        "calculated_rate": 100,
                        "taxable": True,
                        "tax_include": False,
                    }
                ]
            ),
            "invoice": json.dumps(
                {
                    "date": "2026-10-10",
                    "total": 1,
                    "tax": 0,
                    "to_pay": 1,
                    "discount": 0,
                    "paid": 0,
                    "vat": "VAT-L1",
                }
            ),
        }
        response = self.client.post(f"/invoice/invoice/0/{self.customer.pk}", data)
        self.assertEqual(response.status_code, 200, response.content[:200])
        invoice = Invoice.objects.get()
        self.assertEqual(invoice.total, 226)
        self.assertEqual(invoice.tax, 26)
        response = self.client.post(f"/invoice/invoice/{invoice.pk}", data)
        self.assertEqual(response.status_code, 400)

    def test_legacy_invalid_line_has_no_partial_invoice_or_counter(self):
        from invoices.models import InvoiceCounter, UserSystem

        UserSystem.objects.create(user=self.user, billing_term=self.year)
        self.client.force_login(self.user)
        import json

        data = {
            "items": json.dumps([{"qty": 0, "taxable": True, "tax_include": False}]),
            "invoice": json.dumps({"date": "2026-10-10", "discount": 0, "paid": 0}),
        }
        response = self.client.post(f"/invoice/invoice/0/{self.customer.pk}", data)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Invoice.objects.count(), 0)
        self.assertEqual(InvoiceCounter.objects.count(), 0)

    def test_legacy_reports_require_login(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get("/invoice/invoice/1/term").status_code, 302)

    def test_token_expiry(self):
        import hashlib

        token = "expired-token"
        m.AccessToken.objects.create(
            user=self.user,
            digest=hashlib.sha256(token.encode()).hexdigest(),
            expires_at=timezone.now() - timedelta(seconds=1),
        )
        self.client.force_authenticate(None)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.assertEqual(self.client.get("/api/v1/auth/me/").status_code, 401)

    def test_supplier_cheque_payment_settles_on_clearance(self):
        supplier = m.Supplier.objects.create(name="Supplier")
        payment = self.create(
            "supplier-payments",
            {
                "supplier": supplier.pk,
                "amount": "100",
                "date": "2026-10-10",
                "method": "cheque",
                "account": self.bank.pk,
                "cheque_number": "OUT001",
                "cheque_bank": "Bank",
            },
        )
        payment = self.action("supplier-payments", payment)
        self.assertEqual(account_balance(self.bank), 0)
        # Fund the account through a cash deposit before clearing the outgoing cheque.
        transfer = self.create(
            "account-transfers",
            {
                "date": "2026-10-10",
                "source_account": self.cash.pk,
                "destination_account": self.bank.pk,
                "amount": "100",
            },
        )
        self.action("account-transfers", transfer)
        self.action("supplier-payments", payment, "clear", {"date": "2026-10-11"})
        self.assertEqual(account_balance(self.bank), 0)

    def test_customer_search_and_default_fiscal_year_match_admin_flow(self):
        from invoices.models import UserSystem

        UserSystem.objects.create(user=self.user, billing_term=self.year)
        Customer.objects.create(name="Another customer", address="Remote road")
        response = self.client.get("/api/v1/customers/", {"search": "Customer A"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Customer A")
        self.assertIn("balance", response.data["results"][0])
        self.assertEqual(
            self.client.get("/api/v1/bootstrap/").data["default_fiscal_year"],
            self.year.pk,
        )

    def test_idempotent_customer_creation(self):
        headers = {"HTTP_IDEMPOTENCY_KEY": "customer-create-retry"}
        data = {"name": "Customer created once"}
        first = self.client.post("/api/v1/customers/", data, format="json", **headers)
        retry = self.client.post("/api/v1/customers/", data, format="json", **headers)
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(retry.status_code, 201, retry.data)
        self.assertEqual(first.data["id"], retry.data["id"])
        self.assertEqual(Customer.objects.filter(name=data["name"]).count(), 1)
        conflict = self.client.post(
            "/api/v1/customers/", {"name": "Different"}, format="json", **headers
        )
        self.assertEqual(conflict.status_code, 409)

    def test_dimensional_billing_groups_mm_and_issues_piece_stock(self):
        self.seed_stock(self.foam, "10")
        lines = [
            {
                "density": "28",
                "qty": str(qty),
                "unit": "mm",
                "length": "144",
                "breadth": "36",
                "height": "1",
                "stock_item": self.foam.pk,
                "location": self.location.pk,
            }
            for qty in [2, 3]
        ]
        invoice = self.create(
            "invoices",
            {
                "issued_for": self.customer.pk,
                "date": "2026-10-10",
                "fiscal_year": self.year.pk,
                "is_vat": True,
                "lines": lines,
            },
        )
        invoice = self.action("invoices", invoice, "group")
        self.assertEqual(invoice["groups"][0]["quantity"], "10.0000")
        response = self.client.patch(
            f"/api/v1/invoices/{invoice['id']}/groups/{invoice['groups'][0]['id']}/",
            {"revision": invoice["revision"], "rate": "100"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        invoice = self.action("invoices", response.data)
        self.assertEqual(invoice["total"], "1130.00")
        self.assertEqual(m.StockBalance.objects.get(item=self.foam).quantity, 5)
        self.assertEqual(invoice["lines"][0]["stock_item_id"], self.foam.pk)
        self.assertEqual(invoice["lines"][0]["location_id"], self.location.pk)

    def test_dimensional_billing_rejects_missing_measurement(self):
        response = self.client.post(
            "/api/v1/invoices/",
            {
                "issued_for": self.customer.pk,
                "date": "2026-10-10",
                "fiscal_year": self.year.pk,
                "lines": [{"density": "28", "qty": "1", "unit": "mm"}],
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_receipt_post_and_invoice_allocation_are_atomic(self):
        invoice = self.action("invoices", self.invoice())
        receipt = self.create(
            "customer-payments",
            {
                "customer": self.customer.pk,
                "date": "2026-10-10",
                "amount": "566",
                "method": "cash",
                "account": self.cash.pk,
            },
        )
        self.action(
            "customer-payments",
            receipt,
            "post",
            {"allocations": [{"invoice": invoice["id"], "amount": "566"}]},
            expected=400,
        )
        self.assertEqual(m.CustomerReceipt.objects.get().status, "draft")
        self.assertEqual(account_balance(self.cash), 10000)
        self.assertEqual(Payment.objects.count(), 0)
        self.assertEqual(m.PaymentAllocation.objects.count(), 0)

    def test_readonly_payment_and_opening_history_are_customer_filtered(self):
        from invoices.models import OpeningBalance

        second = Customer.objects.create(name="Other")
        Payment.objects.create(
            customer=self.customer, amount=100, payment_mode=2, date="2026-10-10"
        )
        Payment.objects.create(
            customer=second, amount=200, payment_mode=2, date="2026-10-10"
        )
        OpeningBalance.objects.create(customer=self.customer, term=self.year, amount=10)
        self.assertEqual(
            self.client.get("/api/v1/payments/", {"customer": self.customer.pk}).data[
                "count"
            ],
            1,
        )
        self.assertEqual(
            self.client.get(
                "/api/v1/opening-balances/", {"customer": self.customer.pk}
            ).data["count"],
            1,
        )
        self.assertEqual(
            self.client.post("/api/v1/payments/", {}, format="json").status_code, 405
        )

    def test_pdf_export_accepts_pdf_media_type(self):
        invoice = self.action("invoices", self.invoice())
        response = self.client.get(
            f"/api/v1/invoices/{invoice['id']}/pdf/", HTTP_ACCEPT="application/pdf"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_customer_admin_renders_without_optional_user_profile(self):
        self.client.force_login(self.user)
        response = self.client.get(f"/invoices/customer/{self.customer.pk}/change/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Add New Invoice")

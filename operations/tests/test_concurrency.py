"""Exercise two simultaneous writers against Django's shared SQLite test database."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from time import sleep
from django.contrib.auth.models import User
from django.db import close_old_connections
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from invoices.models import Customer, Invoice, Items, Term
from operations.models import DensityGroup, DocumentSequence, PostingLock


class ConcurrentPostingTests(TransactionTestCase):
    def test_two_writers_receive_distinct_invoice_numbers(self):
        user = User.objects.create_superuser("owner", "owner@example.test", "password")
        other = User.objects.create_superuser("other", "other@example.test", "password")
        customer = Customer.objects.create(name="Customer")
        year = Term.objects.create(
            title="2026", start_date="2026-01-01", end_date="2026-12-31"
        )
        PostingLock.objects.create(pk=1)
        invoices = []
        for actor in [user, other]:
            invoice = Invoice.objects.create(
                issued_for=customer,
                issued_by=actor,
                fiscal_year=year,
                date="2026-10-10",
                source="api",
                status="grouped",
                is_vat=True,
            )
            Items.objects.create(
                invoice=invoice,
                density="28",
                qty=1,
                calculated_rate=0,
                taxable=True,
                tax_include=False,
            )
            DensityGroup.objects.create(
                invoice=invoice,
                density="28",
                unit="piece",
                taxable=True,
                quantity=1,
                rate=100,
            )
            invoices.append(invoice.pk)
        barrier = Barrier(2)

        def post(actor_id, invoice_id):
            close_old_connections()
            client = APIClient()
            client.force_authenticate(User.objects.get(pk=actor_id))
            barrier.wait(timeout=10)
            try:
                for attempt in range(20):
                    response = client.post(
                        f"/api/v1/invoices/{invoice_id}/post/",
                        {"revision": 1},
                        format="json",
                        HTTP_IDEMPOTENCY_KEY=f"concurrent-{invoice_id}",
                    )
                    if response.status_code != 409:
                        return response.status_code, response.data
                    sleep(0.05)
                return response.status_code, response.data
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda pair: post(*pair),
                    [(user.pk, invoices[0]), (other.pk, invoices[1])],
                )
            )
        for code, body in results:
            self.assertEqual(code, 200, body)
        self.assertEqual(len(set(body["number"] for _, body in results)), 2)
        self.assertEqual(DocumentSequence.objects.get().value, 2)
        self.assertEqual(Invoice.objects.filter(status="posted").count(), 2)

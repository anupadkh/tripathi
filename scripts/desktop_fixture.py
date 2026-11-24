"""Seed only an isolated database created by the Electron integration test."""

import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
path = Path(os.environ["DJANGO_DB_PATH"]).resolve()
assert (
    path.name == "smoke.sqlite3"
    and path.parent.name.startswith(".desktop-smoke-")
    and path.is_relative_to(ROOT)
), "Use an isolated smoke database."
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "foam_industry.settings")
import django

django.setup()
from django.contrib.auth.models import User
from django.utils import timezone
from django.db import transaction
from invoices.models import Customer, Term, UserSystem
from operations.models import (
    PaymentAccount,
    StockItem,
    Location,
    Supplier,
    Worker,
    ExpenseCategory,
)
from operations.models import StockAdjustment, StockAdjustmentLine
from operations.services import post_adjustment

now = timezone.localdate()
user = User.objects.create_superuser(
    "desktop-test", "desktop@example.test", "desktop-test-password"
)
year = Term.objects.create(
    title=f"{now.year} test fiscal year",
    start_date=now.replace(month=1, day=1),
    end_date=now.replace(month=12, day=31),
)
UserSystem.objects.create(user=user, billing_term=year)
Customer.objects.create(
    name="Alpha Foam Customer", address="Factory road", phone=9800000001, pan=123456789
)
Customer.objects.create(name='<img src=x onerror="window.hacked=true">')
for index in range(53):
    Customer.objects.create(name=f"Test customer {index:03}")
PaymentAccount.objects.create(name="Factory cash", kind="cash", opening_balance=10000)
PaymentAccount.objects.create(name="Test bank", kind="bank", bank_name="Bank")
StockItem.objects.create(sku="RAW", name="Raw chemical", kind="raw", unit="kg")
StockItem.objects.create(
    sku="FOAM", name="28 density foam", kind="finished", density="28", unit="piece"
)
Location.objects.create(name="Main store")
Supplier.objects.create(name="Materials supplier")
Worker.objects.create(
    name="Factory worker", salary_basis="daily", rate=500, overtime_rate=100
)
ExpenseCategory.objects.create(name="Food")
print("Isolated fixture prepared.")
with transaction.atomic():
    adjustment = StockAdjustment.objects.create(
        date=now,
        location=Location.objects.get(name="Main store"),
        reason="Test opening stock",
        created_by=user,
    )
    StockAdjustmentLine.objects.create(
        adjustment=adjustment, item=StockItem.objects.get(sku="FOAM"), quantity=10
    )
    post_adjustment(adjustment)

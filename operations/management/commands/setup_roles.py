from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission


class Command(BaseCommand):
    help = "Create module roles without assigning any users."

    def handle(self, *args, **options):
        roles = {
            "Billing": {
                "invoices": [
                    "customer",
                    "invoice",
                    "term",
                    "payment",
                    "openingbalance",
                ],
                "operations": [
                    "densitygroup",
                    "customerreceipt",
                    "paymentallocation",
                    "stockitem",
                    "location",
                ],
            },
            "Factory": {
                "operations": [
                    "stockitem",
                    "location",
                    "stockbalance",
                    "stockmovement",
                    "joborder",
                    "materialissue",
                    "productionreport",
                    "worksheet",
                    "labourentry",
                ]
            },
            "Accounts": {
                "invoices": [
                    "customer",
                    "invoice",
                    "term",
                    "payment",
                    "openingbalance",
                ],
                "operations": [
                    "supplier",
                    "paymentaccount",
                    "accountmovement",
                    "customerreceipt",
                    "paymentallocation",
                    "accounttransfer",
                    "purchasebill",
                    "goodsreceipt",
                    "supplierpayment",
                    "expensecategory",
                    "expense",
                    "stockbalance",
                    "stockmovement",
                    "stockitem",
                    "location",
                ],
            },
            "Payroll": {
                "operations": [
                    "worker",
                    "worksheet",
                    "labourentry",
                    "payrollrun",
                    "payrollline",
                    "payrolladjustment",
                    "salaryadvance",
                    "salarypayment",
                ]
            },
        }
        readonly = {
            "stockbalance",
            "stockmovement",
            "accountmovement",
            "densitygroup",
            "paymentallocation",
            "payrollline",
            "payment",
            "openingbalance",
        }
        for name, apps in roles.items():
            group, _ = Group.objects.get_or_create(name=name)
            permissions = Permission.objects.none()
            for app, models in apps.items():
                for model in models:
                    actions = (
                        ["view"] if model in readonly else ["view", "add", "change"]
                    )
                    permissions = permissions | Permission.objects.filter(
                        content_type__app_label=app,
                        content_type__model=model,
                        codename__in=[f"{action}_{model}" for action in actions],
                    )
            # Accounts used for payment entry can be selected without exposing balances.
            permissions = permissions | Permission.objects.filter(
                content_type__app_label="operations", codename="view_paymentaccount"
            )
            group.permissions.set(permissions.distinct())
            self.stdout.write(self.style.SUCCESS(f"Updated {name} role"))

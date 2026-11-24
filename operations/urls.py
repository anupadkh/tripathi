from django.urls import path, include
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from . import views as v

router = DefaultRouter()
for name, view in [
    ("customers", v.CustomerViewSet),
    ("payments", v.LegacyPaymentViewSet),
    ("opening-balances", v.OpeningBalanceViewSet),
    ("suppliers", v.SupplierViewSet),
    ("items", v.StockItemViewSet),
    ("locations", v.LocationViewSet),
    ("bank-accounts", v.BankAccountViewSet),
    ("payment-accounts", v.AccountViewSet),
    ("account-movements", v.AccountMovementViewSet),
    ("workers", v.WorkerViewSet),
    ("fiscal-years", v.TermViewSet),
    ("invoices", v.InvoiceViewSet),
    ("customer-payments", v.ReceiptViewSet),
    ("cheques", v.ChequeViewSet),
    ("account-transfers", v.TransferViewSet),
    ("purchase-bills", v.PurchaseViewSet),
    ("goods-receipts", v.GoodsReceiptViewSet),
    ("supplier-payments", v.SupplierPaymentViewSet),
    ("stock/balances", v.BalanceViewSet),
    ("stock/movements", v.MovementViewSet),
    ("stock-adjustments", v.AdjustmentViewSet),
    ("job-orders", v.JobViewSet),
    ("material-issues", v.IssueViewSet),
    ("production-reports", v.ProductionViewSet),
    ("expense-categories", v.CategoryViewSet),
    ("expenses", v.ExpenseViewSet),
    ("worksheets", v.WorksheetViewSet),
    ("labour-entries", v.LabourViewSet),
    ("payroll-runs", v.PayrollViewSet),
    ("salary-advances", v.AdvanceViewSet),
    ("salary-payments", v.SalaryPaymentViewSet),
    ("audit-events", v.AuditViewSet),
]:
    router.register(name, view, basename=name.replace("/", "-"))

urlpatterns = [
    path("health/", v.HealthView.as_view()),
    path("version/", v.VersionView.as_view()),
    path("auth/login/", v.LoginView.as_view()),
    path("auth/logout/", v.LogoutView.as_view()),
    path("auth/me/", v.MeView.as_view()),
    path("bootstrap/", v.BootstrapView.as_view()),
    path("reports/<str:report>/", v.ReportsView.as_view()),
    path("dates/convert/", v.DateConversionView.as_view()),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("", include(router.urls)),
]

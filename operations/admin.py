from django.contrib import admin
from django.apps import apps


class OperationsReadOnlyAdmin(admin.ModelAdmin):
    """Posting must go through the validated service/API, never generic admin edits."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


for model in apps.get_app_config("operations").get_models():
    if model.__name__ not in ("AccessToken", "IdempotencyRecord"):
        admin.site.register(model, OperationsReadOnlyAdmin)

from rest_framework.permissions import DjangoModelPermissions


class ModelPermissions(DjangoModelPermissions):
    perms_map = dict(
        DjangoModelPermissions.perms_map,
        GET=["%(app_label)s.view_%(model_name)s"],
        HEAD=["%(app_label)s.view_%(model_name)s"],
    )

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if getattr(view, "action", None) not in (
            "list",
            "retrieve",
            "create",
            "update",
            "partial_update",
            "destroy",
            "metadata",
            None,
        ):
            opts = view.get_queryset().model._meta
            action = (
                "view" if request.method in ("GET", "HEAD", "OPTIONS") else "change"
            )
            return request.user.has_perm(f"{opts.app_label}.{action}_{opts.model_name}")
        return super().has_permission(request, view)

from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from tenants.models import Tenant, TenantCustomer, TenantScopedRecord
from tenants.permissions import (
    RequiresTenantAdmin,
    RequiresTenantCustomer,
    RequiresTenantMembership,
)


class TenantContextMixin:
    tenant_lookup_url_kwarg = "tenant_slug"

    def get_tenant(self) -> Tenant:
        if hasattr(self, "_tenant"):
            return self._tenant

        slug = self.kwargs[self.tenant_lookup_url_kwarg]
        try:
            tenant = Tenant.objects.get(slug=slug)
        except Tenant.DoesNotExist as exc:
            raise NotFound("租户不存在。") from exc

        if not tenant.is_active:
            raise PermissionDenied("租户已停用。")

        self._tenant = tenant
        return tenant


class TenantContextView(TenantContextMixin, APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        tenant = self.get_tenant()
        return Response(
            {
                "slug": tenant.slug,
                "name": tenant.name,
                "timezone": tenant.timezone,
                "is_active": tenant.is_active,
            },
            status=status.HTTP_200_OK,
        )


class TenantMembershipView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership]

    def get(self, request, *args, **kwargs):
        tenant = self.get_tenant()
        if request.user.is_superuser:
            return Response({"role": "platform_admin"}, status=status.HTTP_200_OK)

        membership = request.user.tenant_memberships.get(tenant=tenant)
        return Response({"role": membership.role}, status=status.HTTP_200_OK)


class TenantScopedRecordView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantMembership, RequiresTenantAdmin]

    def get(self, request, *args, **kwargs):
        tenant = self.get_tenant()
        labels = list(
            TenantScopedRecord.objects.filter(tenant=tenant)
            .order_by("label")
            .values_list("label", flat=True)
        )
        return Response({"labels": labels}, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        tenant = self.get_tenant()
        label = request.data.get("label")
        if not label:
            return Response({"detail": "label 必填。"}, status=status.HTTP_400_BAD_REQUEST)

        TenantScopedRecord.objects.create(tenant=tenant, label=label)
        return Response({"label": label}, status=status.HTTP_201_CREATED)


class TenantCustomerMeView(TenantContextMixin, APIView):
    permission_classes = [RequiresTenantCustomer]

    def get(self, request, *args, **kwargs):
        tenant = self.get_tenant()
        tenant_customer = TenantCustomer.objects.get(tenant=tenant, user=request.user)
        return Response(
            {
                "tenant_slug": tenant.slug,
                "phone": request.user.customer_profile.phone,
                "display_name": tenant_customer.display_name,
                "notes": tenant_customer.notes,
                "tags": tenant_customer.tags,
            },
            status=status.HTTP_200_OK,
        )

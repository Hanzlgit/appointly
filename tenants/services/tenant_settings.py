from django.db import transaction

from tenants.models import Tenant


@transaction.atomic
def tenant_timezone_update(*, tenant: Tenant, timezone: str) -> Tenant:
    """更新租户时区。

    Args:
        tenant (Tenant): 目标租户。
        timezone (str): IANA 时区名称。

    Returns:
        Tenant: 更新后的租户。

    Raises:
        ValidationError: 时区名称无效。
    """
    tenant.timezone = timezone
    tenant.full_clean()
    tenant.save(update_fields=["timezone", "updated_at"])
    return tenant

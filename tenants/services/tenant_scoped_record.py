from django.db import transaction

from tenants.models import Tenant, TenantScopedRecord


@transaction.atomic
def tenant_scoped_record_create(*, tenant: Tenant, label: str) -> TenantScopedRecord:
    """在租户下创建 scoped record。

    Args:
        tenant (Tenant): 目标租户。
        label (str): 记录标签，租户内唯一。

    Returns:
        TenantScopedRecord: 新创建的 scoped record。

    Raises:
        ValidationError: label 为空或违反唯一约束。
    """
    record = TenantScopedRecord(tenant=tenant, label=label)
    record.full_clean()
    record.save()
    return record

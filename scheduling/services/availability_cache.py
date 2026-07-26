"""可用时段 Redis 缓存与失效。"""

import hashlib
import json

from django.core.cache import cache
from tenants.models import Tenant

from scheduling.constants import AVAILABILITY_CACHE_TTL_SECONDS
from scheduling.selectors import (
    scheduling_availability_aggregate,
    scheduling_availability_slots_for_resource,
)


def _availability_cache_version_key(*, tenant_id: int) -> str:
    """返回租户可用性缓存版本键。

    Args:
        tenant_id (int): 租户 ID。

    Returns:
        str: Redis 缓存键。
    """
    return f"scheduling:availability:ver:{tenant_id}"


def _availability_cache_get_version(*, tenant_id: int) -> int:
    """读取租户可用性缓存版本号。

    Args:
        tenant_id (int): 租户 ID。

    Returns:
        int: 当前版本号（至少为 1）。
    """
    key = _availability_cache_version_key(tenant_id=tenant_id)
    version = cache.get(key)
    if version is None:
        cache.set(key, 1, timeout=None)
        return 1
    return int(version)


def scheduling_availability_cache_invalidate(*, tenant_id: int) -> None:
    """使租户下全部可用时段缓存失效。

    Args:
        tenant_id (int): 租户 ID。
    """
    key = _availability_cache_version_key(tenant_id=tenant_id)
    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 2, timeout=None)


def _availability_cache_key(
    *,
    tenant_id: int,
    version: int,
    query_params: dict,
) -> str:
    """根据查询参数生成缓存键。

    Args:
        tenant_id (int): 租户 ID。
        version (int): 缓存版本号。
        query_params (dict): 可序列化的查询参数。

    Returns:
        str: Redis 缓存键。
    """
    payload = json.dumps(query_params, sort_keys=True, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"scheduling:availability:{tenant_id}:{version}:{digest}"


def scheduling_availability_query_cached(
    *,
    tenant: Tenant,
    start,
    end,
    resource_id: int | None = None,
    service_id: int | None = None,
    location_id: int | None = None,
) -> dict:
    """带 Redis 缓存的可用时段查询。

    Args:
        tenant (Tenant): 目标租户。
        start: 查询范围开始（UTC datetime）。
        end: 查询范围结束（UTC datetime）。
        resource_id (int | None): 指定资源时使用单资源模式。
        service_id (int | None): 聚合模式下的服务过滤。
        location_id (int | None): 可选地点过滤。

    Returns:
        dict: ``mode`` 为 ``resource`` 或 ``aggregate`` 的查询结果。
    """
    query_params = {
        "start": start,
        "end": end,
        "resource_id": resource_id,
        "service_id": service_id,
        "location_id": location_id,
    }
    version = _availability_cache_get_version(tenant_id=tenant.id)
    cache_key = _availability_cache_key(
        tenant_id=tenant.id,
        version=version,
        query_params=query_params,
    )
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    if resource_id is not None:
        result = {
            "mode": "resource",
            "slots": scheduling_availability_slots_for_resource(
                tenant=tenant,
                start=start,
                end=end,
                resource_id=resource_id,
                location_id=location_id,
            ),
        }
    else:
        result = {
            "mode": "aggregate",
            "availability": scheduling_availability_aggregate(
                tenant=tenant,
                start=start,
                end=end,
                service_id=service_id,
                location_id=location_id,
            ),
        }

    cache.set(cache_key, result, timeout=AVAILABILITY_CACHE_TTL_SECONDS)
    return result

"""为本地开发创建控制台测试账号。"""

from catalog.models import Resource
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from tenants.models import Tenant, TenantMembership, TenantRole

DEFAULT_TENANT_SLUG = "acme"
DEFAULT_PASSWORD = "StrongPass123!"

ACCOUNTS = (
    {
        "username": "acme-admin",
        "role": TenantRole.TENANT_ADMIN,
        "link_resource_name": None,
    },
    {
        "username": "acme-staff",
        "role": TenantRole.STAFF,
        "link_resource_name": "Alice",
    },
)


class Command(BaseCommand):
    """创建或重置 acme 租户的管理员与员工测试账号。"""

    help = "Create or reset console test accounts for local development."

    def add_arguments(self, parser) -> None:
        """注册命令行参数。

        Args:
            parser: Django 参数解析器。
        """
        parser.add_argument(
            "--tenant-slug",
            default=DEFAULT_TENANT_SLUG,
            help=f"Target tenant slug (default: {DEFAULT_TENANT_SLUG}).",
        )
        parser.add_argument(
            "--password",
            default=DEFAULT_PASSWORD,
            help="Password for all seeded console users.",
        )

    def handle(self, *args, **options) -> None:
        """执行账号 seed。

        Args:
            *args: Django 传入的位置参数。
            **options: 含 tenant_slug 与 password 的选项。
        """
        tenant_slug = options["tenant_slug"]
        password = options["password"]

        try:
            tenant = Tenant.objects.get(slug=tenant_slug)
        except Tenant.DoesNotExist as exc:
            raise CommandError(f"租户不存在: {tenant_slug}") from exc

        created_users: list[str] = []
        updated_users: list[str] = []

        with transaction.atomic():
            for spec in ACCOUNTS:
                user, created = User.objects.get_or_create(
                    username=spec["username"],
                    defaults={"is_staff": False, "is_superuser": False},
                )
                user.set_password(password)
                user.save(update_fields=["password"])

                membership, membership_created = TenantMembership.objects.update_or_create(
                    tenant=tenant,
                    user=user,
                    defaults={"role": spec["role"]},
                )

                resource_name = spec["link_resource_name"]
                if resource_name:
                    resource = Resource.objects.filter(tenant=tenant, name=resource_name).first()
                    if resource is None:
                        self.stdout.write(
                            self.style.WARNING(
                                f"未找到资源 {resource_name!r}，跳过 {user.username} 的资源绑定。"
                            )
                        )
                    elif resource.staff_user_id != user.id:
                        resource.staff_user = user
                        resource.save(update_fields=["staff_user", "updated_at"])

                if created or membership_created:
                    created_users.append(user.username)
                else:
                    updated_users.append(user.username)

                self.stdout.write(
                    f"  {user.username} @ {tenant.slug} ({membership.role})"
                )

        self.stdout.write(self.style.SUCCESS("\n控制台测试账号已就绪："))
        for spec in ACCOUNTS:
            self.stdout.write(f"  用户名: {spec['username']}")
            self.stdout.write(f"  密码:   {password}")
            self.stdout.write(f"  角色:   {spec['role']}")
            self.stdout.write(f"  登录:   /t/{tenant.slug}/console/login")
            self.stdout.write("")

        if created_users:
            self.stdout.write(self.style.SUCCESS(f"新建: {', '.join(created_users)}"))
        if updated_users:
            self.stdout.write(f"已更新密码/成员关系: {', '.join(updated_users)}")

from django.conf import settings
from django.db import models


class StaffProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
    )
    phone = models.CharField(max_length=32, unique=True, null=True, blank=True)

    class Meta:
        verbose_name = "后台账号资料"
        verbose_name_plural = "后台账号资料"

    def __str__(self) -> str:
        """返回后台账号的展示标识。"""
        return self.phone or str(self.user)


class CustomerProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="customer_profile",
    )
    phone = models.CharField(max_length=32, unique=True)

    class Meta:
        verbose_name = "客户账号资料"
        verbose_name_plural = "客户账号资料"

    def __str__(self) -> str:
        """返回客户手机号。"""
        return self.phone

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
        return self.phone or str(self.user)

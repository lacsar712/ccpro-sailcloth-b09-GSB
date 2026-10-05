from django.conf import settings
from django.db import models

DEFAULT_FABRIC_WEIGHT_GSM = 380


class Loft(models.Model):
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


class ClothRoll(models.Model):
    STATUS_RAW = "raw"
    STATUS_DIPPING = "dipping"
    STATUS_CURED = "cured"
    STATUS_CHOICES = [
        (STATUS_RAW, "原布"),
        (STATUS_DIPPING, "浸渍中"),
        (STATUS_CURED, "已固化"),
    ]

    loft = models.ForeignKey(Loft, on_delete=models.CASCADE, related_name="rolls")
    roll_code = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RAW)
    fabric_weight_gsm = models.PositiveIntegerField(default=DEFAULT_FABRIC_WEIGHT_GSM)
    # 克重等关键字段的乐观锁版本：每次克重落库 +1
    version = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["loft_id", "roll_code"]
        constraints = [
            models.UniqueConstraint(
                fields=["loft", "roll_code"],
                name="uniq_roll_code_per_loft",
            )
        ]

    def __str__(self):
        return f"{self.loft.name}/{self.roll_code}"


class DipRun(models.Model):
    roll = models.ForeignKey(ClothRoll, on_delete=models.CASCADE, related_name="dip_runs")
    started_at = models.DateTimeField()
    resin_pct = models.DecimalField(max_digits=5, decimal_places=2)
    cure_hours = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        return f"Dip@{self.roll_id} {self.started_at}"


class WeightAuditLog(models.Model):
    """克重改写审计：谁、何时、把哪一卷的克重从旧值改到新值。"""

    SOURCE_PANEL = "panel"
    SOURCE_LEDGER = "ledger"
    SOURCE_CHOICES = [
        (SOURCE_PANEL, "晾晒架面板"),
        (SOURCE_LEDGER, "布卷台账"),
    ]

    roll = models.ForeignKey(
        ClothRoll, on_delete=models.CASCADE, related_name="weight_logs"
    )
    old_value = models.PositiveIntegerField()
    new_value = models.PositiveIntegerField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="weight_logs",
    )
    # 冗余操作人用户名，即使用户账号日后删除，审计仍可读
    changed_by_username = models.CharField(max_length=150, default="")
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LEDGER
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"{self.roll} {self.old_value}->{self.new_value} by {self.changed_by_username}"

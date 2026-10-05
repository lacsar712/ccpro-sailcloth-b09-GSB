from django.db import transaction
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .exceptions import Conflict
from .models import (
    DEFAULT_FABRIC_WEIGHT_GSM,
    ClothRoll,
    DipRun,
    Loft,
    WeightAuditLog,
)
from .rules import can_change_weight, can_mark_roll_cured


class LoftSerializer(serializers.ModelSerializer):
    rollCount = serializers.SerializerMethodField()

    class Meta:
        model = Loft
        fields = ("id", "name", "location", "notes", "rollCount", "created_at")
        read_only_fields = ("id", "rollCount", "created_at")

    def get_rollCount(self, obj):
        if hasattr(obj, "roll_count"):
            return obj.roll_count
        return obj.rolls.count()


class ClothRollSerializer(serializers.ModelSerializer):
    loftId = serializers.PrimaryKeyRelatedField(source="loft", queryset=Loft.objects.all())
    rollCode = serializers.CharField(source="roll_code")
    fabricWeightGsm = serializers.IntegerField(
        source="fabric_weight_gsm", required=False, min_value=1
    )
    loftName = serializers.CharField(source="loft.name", read_only=True)
    # 克重乐观锁版本：前端改克重时必须回传当前 version
    expectedVersion = serializers.IntegerField(required=False, write_only=True)
    # 写入入口：panel=晾晒架面板，ledger=布卷台账
    source = serializers.ChoiceField(
        choices=[WeightAuditLog.SOURCE_PANEL, WeightAuditLog.SOURCE_LEDGER],
        required=False,
        write_only=True,
        default=WeightAuditLog.SOURCE_LEDGER,
    )

    class Meta:
        model = ClothRoll
        fields = (
            "id",
            "loftId",
            "loftName",
            "rollCode",
            "status",
            "fabricWeightGsm",
            "version",
            "notes",
            "source",
            "expectedVersion",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "version", "loftName", "created_at", "updated_at")

    def validate(self, attrs):
        loft = attrs.get("loft") or getattr(self.instance, "loft", None)
        roll_code = attrs.get("roll_code") or getattr(self.instance, "roll_code", None)
        if loft and roll_code:
            qs = ClothRoll.objects.filter(loft=loft, roll_code=roll_code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise serializers.ValidationError({"rollCode": "同一帆布间卷号必须唯一"})

        new_status = attrs.get("status")
        if new_status == ClothRoll.STATUS_CURED:
            roll = self.instance
            if roll is None:
                raise serializers.ValidationError(
                    {"status": "新建布卷不能直接设为已固化"}
                )
            # 合并未提交字段到临时视角：用当前实例校验
            ok, msg = can_mark_roll_cured(roll)
            if not ok:
                raise serializers.ValidationError({"status": msg})
        return attrs

    def create(self, validated_data):
        source = validated_data.pop("source", WeightAuditLog.SOURCE_LEDGER)
        validated_data.pop("expectedVersion", None)
        new_weight = validated_data.get(
            "fabric_weight_gsm", DEFAULT_FABRIC_WEIGHT_GSM
        )
        user = self.context["request"].user

        with transaction.atomic():
            # 新建即带非默认克重，视为首写：工人/管理员均可，留审计
            roll = ClothRoll.objects.create(**validated_data)
            if new_weight != DEFAULT_FABRIC_WEIGHT_GSM:
                roll.version = 2
                roll.save(update_fields=["version"])
                WeightAuditLog.objects.create(
                    roll=roll,
                    old_value=DEFAULT_FABRIC_WEIGHT_GSM,
                    new_value=new_weight,
                    changed_by=user if user and user.is_authenticated else None,
                    changed_by_username=user.get_username() if user and user.is_authenticated else "",
                    source=source,
                )
        return roll

    def update(self, instance, validated_data):
        expected_version = validated_data.pop("expectedVersion", None)
        source = validated_data.pop("source", WeightAuditLog.SOURCE_LEDGER)
        weight_in_payload = "fabric_weight_gsm" in validated_data
        new_weight = validated_data.get("fabric_weight_gsm")
        user = self.context["request"].user

        with transaction.atomic():
            # 锁定本行：两名管理员交叉改同一卷时，靠 version 只留一版
            roll = ClothRoll.objects.select_for_update().get(pk=instance.pk)
            weight_changes = (
                weight_in_payload and new_weight != roll.fabric_weight_gsm
            )
            if weight_changes:
                if expected_version is None:
                    raise serializers.ValidationError(
                        {"expectedVersion": "修改克重必须携带当前版本号 expectedVersion"}
                    )
                if expected_version != roll.version:
                    raise Conflict(
                        "该卷克重已被他人先改过（版本不一致），请刷新后取最新克重再改"
                    )
                ok, msg = can_change_weight(user, roll, new_weight)
                if not ok:
                    # 操作工越界改已非 380 的克重 / 已固化卷 → 一律拒绝
                    raise PermissionDenied(msg)

            # 锁内再次校验固化规则，避免与状态变更竞争
            if validated_data.get("status") == ClothRoll.STATUS_CURED:
                ok, msg = can_mark_roll_cured(roll)
                if not ok:
                    raise serializers.ValidationError({"status": msg})

            old_weight = roll.fabric_weight_gsm
            for attr, value in validated_data.items():
                setattr(roll, attr, value)
            if weight_changes:
                roll.version = roll.version + 1
            roll.save()

            if weight_changes:
                WeightAuditLog.objects.create(
                    roll=roll,
                    old_value=old_weight,
                    new_value=roll.fabric_weight_gsm,
                    changed_by=user if user and user.is_authenticated else None,
                    changed_by_username=user.get_username() if user and user.is_authenticated else "",
                    source=source,
                )
        return roll


class WeightAuditLogSerializer(serializers.ModelSerializer):
    rollId = serializers.IntegerField(source="roll.id", read_only=True)
    rollCode = serializers.CharField(source="roll.roll_code", read_only=True)
    loftName = serializers.CharField(source="roll.loft.name", read_only=True)
    oldValue = serializers.IntegerField(source="old_value", read_only=True)
    newValue = serializers.IntegerField(source="new_value", read_only=True)
    changedBy = serializers.CharField(source="changed_by_username", read_only=True)
    changedAt = serializers.DateTimeField(source="changed_at", read_only=True)
    sourceLabel = serializers.SerializerMethodField()

    class Meta:
        model = WeightAuditLog
        fields = (
            "id",
            "rollId",
            "rollCode",
            "loftName",
            "oldValue",
            "newValue",
            "changedBy",
            "source",
            "sourceLabel",
            "changedAt",
        )

    def get_sourceLabel(self, obj):
        return dict(WeightAuditLog.SOURCE_CHOICES).get(obj.source, obj.source)


class DipRunSerializer(serializers.ModelSerializer):
    rollId = serializers.PrimaryKeyRelatedField(
        source="roll", queryset=ClothRoll.objects.all()
    )
    startedAt = serializers.DateTimeField(source="started_at")
    resinPct = serializers.DecimalField(source="resin_pct", max_digits=5, decimal_places=2)
    cureHours = serializers.DecimalField(
        source="cure_hours",
        max_digits=6,
        decimal_places=2,
        required=False,
        allow_null=True,
    )
    rollCode = serializers.CharField(source="roll.roll_code", read_only=True)
    loftName = serializers.CharField(source="roll.loft.name", read_only=True)

    class Meta:
        model = DipRun
        fields = (
            "id",
            "rollId",
            "rollCode",
            "loftName",
            "startedAt",
            "resinPct",
            "cureHours",
            "notes",
            "created_at",
        )
        read_only_fields = ("id", "rollCode", "loftName", "created_at")

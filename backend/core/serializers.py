from rest_framework import serializers
from rest_framework.exceptions import APIException, PermissionDenied

from .models import ClothRoll, DipRun, Loft, WeightAuditLog
from .rules import FACTORY_DEFAULT_WEIGHT, can_mark_roll_cured, can_change_weight


class Conflict(APIException):
    status_code = 409
    default_detail = "资源刚被他人修改，请刷新后重试"
    default_code = "conflict"


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
    fabricWeightGsm = serializers.IntegerField(source="fabric_weight_gsm", required=False)
    # 克重乐观锁：改克重时必须带上所看到的版本号，与库内不一致即 409。
    expectedVersion = serializers.IntegerField(
        source="_expected_version", required=False, write_only=True, allow_null=False
    )
    version = serializers.IntegerField(read_only=True)
    loftName = serializers.CharField(source="loft.name", read_only=True)

    class Meta:
        model = ClothRoll
        fields = (
            "id",
            "loftId",
            "loftName",
            "rollCode",
            "status",
            "fabricWeightGsm",
            "expectedVersion",
            "version",
            "notes",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "loftName", "version", "created_at", "updated_at")

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

        # 克重写入分界（实例已被视图加行锁，此处读到的就是最新版本）
        if "fabric_weight_gsm" in attrs:
            new_weight = attrs["fabric_weight_gsm"]
            roll = self.instance
            if roll is None:
                # 创建时不允许夹带克重首写；380 走模型默认，非 380 直接拒绝
                if new_weight != FACTORY_DEFAULT_WEIGHT:
                    raise PermissionDenied(
                        "新建布卷的克重恒为出厂默认 380；首写克重请在布卷创建后进行"
                    )
                attrs.pop("fabric_weight_gsm")
                attrs.pop("_expected_version", None)
            elif new_weight != roll.fabric_weight_gsm:
                # 以行锁下的当前库内状态判定：此刻是已固化卷就一律拒，
                # 即使请求同时试图把状态改回原布也不许夹带克重。
                if roll.status == ClothRoll.STATUS_CURED:
                    raise PermissionDenied("该布卷已固化，克重不可修改")
                user = self.context["request"].user
                ok, msg = can_change_weight(user, roll, new_weight)
                if not ok:
                    raise PermissionDenied(msg)
                expected = attrs.pop("_expected_version", None)
                if expected is None:
                    raise serializers.ValidationError(
                        {"expectedVersion": "修改克重必须携带克重版本号"}
                    )
                if expected != roll.version:
                    raise Conflict("克重刚被他人修改，请刷新后以最新克重为准再改")
        # 未走克重分支时，expectedVersion 只是噪声，绝不能落进 create() 的关键字参数
        attrs.pop("_expected_version", None)
        return attrs

    def create(self, validated_data):
        validated_data.pop("_expected_version", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        new_weight = validated_data.pop("fabric_weight_gsm", None)
        validated_data.pop("_expected_version", None)
        weight_changed = (
            new_weight is not None and new_weight != instance.fabric_weight_gsm
        )
        old_weight = instance.fabric_weight_gsm
        instance = super().update(instance, validated_data)
        if weight_changed:
            user = self.context["request"].user
            instance.fabric_weight_gsm = new_weight
            instance.version += 1
            instance.save(update_fields=["fabric_weight_gsm", "version", "updated_at"])
            WeightAuditLog.objects.create(
                roll=instance,
                changed_by=user if user.is_authenticated else None,
                changed_by_name=user.get_username() if user.is_authenticated else "",
                old_value=old_weight,
                new_value=new_weight,
            )
        return instance


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


class WeightAuditLogSerializer(serializers.ModelSerializer):
    rollId = serializers.IntegerField(source="roll_id", read_only=True)
    rollCode = serializers.CharField(source="roll.roll_code", read_only=True)
    loftName = serializers.CharField(source="roll.loft.name", read_only=True)
    changedBy = serializers.CharField(source="changed_by_name", read_only=True)
    oldValue = serializers.IntegerField(source="old_value", read_only=True)
    newValue = serializers.IntegerField(source="new_value", read_only=True)
    changedAt = serializers.DateTimeField(source="changed_at", read_only=True)

    class Meta:
        model = WeightAuditLog
        fields = (
            "id",
            "rollId",
            "rollCode",
            "loftName",
            "changedBy",
            "oldValue",
            "newValue",
            "changedAt",
        )

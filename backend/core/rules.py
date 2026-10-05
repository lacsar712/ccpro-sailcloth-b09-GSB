"""帆布浸渍防水台业务规则。"""

from __future__ import annotations

from decimal import Decimal

from .models import DEFAULT_FABRIC_WEIGHT_GSM, ClothRoll, DipRun

MIN_CURE_HOURS_FOR_CURED = Decimal("12")


def latest_dip_run(roll: ClothRoll) -> DipRun | None:
    return roll.dip_runs.order_by("-started_at", "-id").first()


def can_mark_roll_cured(roll: ClothRoll) -> tuple[bool, str]:
    """
    布卷转为「已固化」(cured) 的前提：
    最近一条浸渍记录的固化时长已记录，且 >= 12 小时。
    """
    latest = latest_dip_run(roll)
    if latest is None:
        return False, "该布卷尚无浸渍记录，不能标记为已固化"
    if latest.cure_hours is None:
        return False, "最近浸渍记录尚未填写固化时长，不能标记为已固化"
    if latest.cure_hours < MIN_CURE_HOURS_FOR_CURED:
        return (
            False,
            f"最近浸渍固化时长 {latest.cure_hours} 小时低于 {MIN_CURE_HOURS_FOR_CURED} 小时，不能标记为已固化",
        )
    return True, ""


def can_change_weight(user, roll: ClothRoll, new_value) -> tuple[bool, str]:
    """
    克重写入分界：
    - 已固化卷：全员不得改克重；
    - 操作工：克重仍为出厂默认 380 时，只能写下第一个非 380 的数；
      已经不是 380 的克重不得再改；
    - 管理员：可改任意未固化卷的克重。
    """
    if new_value is None:
        return False, "克重不能为空"
    try:
        new_value = int(new_value)
    except (TypeError, ValueError):
        return False, "克重必须是整数"
    if new_value <= 0:
        return False, "克重必须为正整数"

    if roll.status == ClothRoll.STATUS_CURED:
        return False, "已固化卷的克重不得修改"

    if new_value == roll.fabric_weight_gsm:
        return False, "新克重与当前克重相同，无需修改"

    is_admin = bool(getattr(user, "is_superuser", False)) or (
        getattr(user, "role", None) == "admin"
    )
    if is_admin:
        return True, ""

    # 操作工：仅允许在克重仍为出厂默认 380 时首写非 380 值
    if roll.fabric_weight_gsm != DEFAULT_FABRIC_WEIGHT_GSM:
        return False, "操作工只能首写出厂默认克重（380），已改写过的克重请联系管理员"
    if new_value == DEFAULT_FABRIC_WEIGHT_GSM:
        return False, "首写克重必须是非 380 的实测值"
    return True, ""

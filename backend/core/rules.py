"""帆布浸渍防水台业务规则。"""

from __future__ import annotations

from decimal import Decimal

from .models import ClothRoll, DipRun

MIN_CURE_HOURS_FOR_CURED = Decimal("12")
FACTORY_DEFAULT_WEIGHT = 380


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


def can_change_weight(user, roll: ClothRoll, new_value: int) -> tuple[bool, str]:
    """
    克重写入分界：
    - 已固化卷：全员（含管理员）不得改克重；
    - 操作工：只能把仍是出厂默认 380 的克重写成第一个非 380 的值，
      已经不是 380 的克重不得再改；
    - 管理员：可改任意未固化卷的克重。
    新建布卷（roll is None）不允许在创建时夹带非默认克重——首写仍走既有卷的修改入口。
    """
    if roll is None:
        return False, "新建布卷时不可指定克重，克重首写请在布卷创建后进行"
    if roll.status == ClothRoll.STATUS_CURED:
        return False, "该布卷已固化，克重不可修改"
    if new_value == roll.fabric_weight_gsm:
        return False, "新克重与当前克重相同，无需修改"
    if user.role == "admin" or user.is_superuser:
        return True, ""
    # 操作工：仅允许 380 -> 非380 的一次性首写
    if roll.fabric_weight_gsm != FACTORY_DEFAULT_WEIGHT:
        return False, "操作工只能写入克重的首个非出厂值，已标定的克重须由管理员修改"
    if new_value == FACTORY_DEFAULT_WEIGHT:
        return False, "新克重不能仍是出厂默认值 380"
    return True, ""

from rest_framework import status
from rest_framework.exceptions import APIException


class Conflict(APIException):
    """克重乐观锁版本冲突：两名管理员交叉改同一卷，只允许一版留下。"""

    status_code = status.HTTP_409_CONFLICT
    default_detail = "数据已被他人修改，请刷新后重试"
    default_code = "conflict"

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import ClothRoll, DipRun, Loft, WeightAuditLog

User = get_user_model()


class WeightChangeTests(APITestCase):
    def setUp(self):
        self.loft = Loft.objects.create(name="测试帆布间", location="港区")
        self.admin = User.objects.create_user(
            "adm1", password="x", role=User.ROLE_ADMIN, is_superuser=True
        )
        self.admin2 = User.objects.create_user(
            "adm2", password="x", role=User.ROLE_ADMIN, is_superuser=True
        )
        self.worker = User.objects.create_user(
            "worker1", password="x", role=User.ROLE_WORKER
        )
        # 出厂默认 380 的未固化卷
        self.raw_default = ClothRoll.objects.create(
            loft=self.loft, roll_code="R-DEF", status=ClothRoll.STATUS_RAW
        )
        # 已被改写过（非 380）的未固化卷
        self.changed = ClothRoll.objects.create(
            loft=self.loft,
            roll_code="R-CHG",
            status=ClothRoll.STATUS_DIPPING,
            fabric_weight_gsm=420,
        )
        # 已固化卷（带满足规则的浸渍记录）
        self.cured = ClothRoll.objects.create(
            loft=self.loft,
            roll_code="R-CUR",
            status=ClothRoll.STATUS_CURED,
            fabric_weight_gsm=450,
        )
        DipRun.objects.create(
            roll=self.cured,
            started_at=timezone.now() - timezone.timedelta(days=1),
            resin_pct=Decimal("30"),
            cure_hours=Decimal("14"),
        )

    def patch_weight(self, user, roll_id, value, expected_version=None, source=None):
        self.client.force_authenticate(user)
        payload = {"fabricWeightGsm": value}
        if expected_version is not None:
            payload["expectedVersion"] = expected_version
        if source is not None:
            payload["source"] = source
        return self.client.patch(f"/api/rolls/{roll_id}/", payload, format="json")

    def test_worker_first_write_from_default_succeeds(self):
        """操作工：380 卷写下第一个非 380 数 → 成功。"""
        resp = self.patch_weight(self.worker, self.raw_default.id, 410, expected_version=1)
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.raw_default.refresh_from_db()
        self.assertEqual(self.raw_default.fabric_weight_gsm, 410)
        self.assertEqual(self.raw_default.version, 2)
        log = WeightAuditLog.objects.get(roll=self.raw_default)
        self.assertEqual(log.old_value, 380)
        self.assertEqual(log.new_value, 410)
        self.assertEqual(log.changed_by, self.worker)
        self.assertEqual(log.changed_by_username, "worker1")

    def test_worker_cannot_rewrite_non_default(self):
        """操作工：改已非 380 的克重 → 403，数值与版本不变。"""
        resp = self.patch_weight(self.worker, self.changed.id, 430, expected_version=1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.changed.refresh_from_db()
        self.assertEqual(self.changed.fabric_weight_gsm, 420)
        self.assertEqual(self.changed.version, 1)
        self.assertFalse(WeightAuditLog.objects.filter(roll=self.changed).exists())

    def test_worker_sending_same_value_is_noop(self):
        """克重未实际变化（380→380）视为 no-op：200 但不写审计、版本不动。"""
        resp = self.patch_weight(self.worker, self.raw_default.id, 380, expected_version=1)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.raw_default.refresh_from_db()
        self.assertEqual(self.raw_default.fabric_weight_gsm, 380)
        self.assertEqual(self.raw_default.version, 1)
        self.assertFalse(WeightAuditLog.objects.filter(roll=self.raw_default).exists())

    def test_admin_can_change_non_cured(self):
        """管理员：可改任意未固化卷克重，并产生审计行。"""
        resp = self.patch_weight(
            self.admin, self.changed.id, 430, expected_version=1, source="panel"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.changed.refresh_from_db()
        self.assertEqual(self.changed.fabric_weight_gsm, 430)
        self.assertEqual(self.changed.version, 2)
        log = WeightAuditLog.objects.get(roll=self.changed)
        self.assertEqual(log.old_value, 420)
        self.assertEqual(log.new_value, 430)
        self.assertEqual(log.changed_by, self.admin)
        self.assertEqual(log.source, "panel")

    def test_admin_change_without_audit_row_fails_contract(self):
        """显式断言：管理员改完审计必须出现行。"""
        self.patch_weight(self.admin, self.changed.id, 499, expected_version=1)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.changed).count(), 1)

    def test_cured_roll_weight_locked_for_everyone(self):
        """已固化卷：工人和管理员都不能改克重。"""
        resp_worker = self.patch_weight(self.worker, self.cured.id, 460, expected_version=1)
        self.assertEqual(resp_worker.status_code, status.HTTP_403_FORBIDDEN)
        resp_admin = self.patch_weight(self.admin, self.cured.id, 460, expected_version=1)
        self.assertEqual(resp_admin.status_code, status.HTTP_403_FORBIDDEN)
        self.cured.refresh_from_db()
        self.assertEqual(self.cured.fabric_weight_gsm, 450)
        self.assertFalse(WeightAuditLog.objects.filter(roll=self.cured).exists())

    def test_weight_change_requires_expected_version(self):
        """改克重不带 expectedVersion → 400。"""
        resp = self.patch_weight(self.admin, self.changed.id, 430)
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("expectedVersion", resp.data)

    def test_two_admins_concurrent_edit_only_one_wins(self):
        """两名管理员交叉改同一卷：先改成功，后到的旧版本 → 409，只一版留下。"""
        # 两人都先看到 version=1 / gsm=420
        r1 = self.patch_weight(self.admin, self.changed.id, 431, expected_version=1)
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        # 第二位仍拿旧版本号提交
        r2 = self.patch_weight(self.admin2, self.changed.id, 432, expected_version=1)
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)
        self.changed.refresh_from_db()
        self.assertEqual(self.changed.fabric_weight_gsm, 431)
        self.assertEqual(self.changed.version, 2)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.changed).count(), 1)
        # 刷新版本后第二位再改即可成功
        r3 = self.patch_weight(self.admin2, self.changed.id, 432, expected_version=2)
        self.assertEqual(r3.status_code, status.HTTP_200_OK)

    def test_status_patch_without_version_still_works(self):
        """不改克重的 PATCH（如状态/备注）无需版本号。"""
        self.client.force_authenticate(self.worker)
        resp = self.client.patch(
            f"/api/rolls/{self.raw_default.id}/",
            {"notes": "仅改备注"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.raw_default.refresh_from_db()
        self.assertEqual(self.raw_default.notes, "仅改备注")
        self.assertEqual(self.raw_default.version, 1)

    def test_weight_and_notes_together_rejected_atomically(self):
        """工人越界改克重时，同一请求里的备注也不落库。"""
        resp = self.patch_weight(self.worker, self.changed.id, 500, expected_version=1)
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_with_non_default_weight_logs_audit(self):
        """新建卷即带非默认克重 → 视为首写并留审计。"""
        self.client.force_authenticate(self.worker)
        resp = self.client.post(
            "/api/rolls/",
            {
                "loftId": self.loft.id,
                "rollCode": "R-NEW",
                "status": "raw",
                "fabricWeightGsm": 395,
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        roll = ClothRoll.objects.get(roll_code="R-NEW")
        self.assertEqual(roll.fabric_weight_gsm, 395)
        self.assertEqual(roll.version, 2)
        self.assertTrue(WeightAuditLog.objects.filter(roll=roll).exists())

    def test_audit_log_endpoint_lists_entries(self):
        """克重审计专页接口：全员可读、内容为旧→新值与操作人。"""
        self.patch_weight(
            self.admin, self.changed.id, 430, expected_version=1, source="ledger"
        )
        self.client.force_authenticate(self.worker)
        resp = self.client.get("/api/weight-logs/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        results = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["rollCode"], "R-CHG")
        self.assertEqual(row["oldValue"], 420)
        self.assertEqual(row["newValue"], 430)
        self.assertEqual(row["changedBy"], "adm1")
        self.assertEqual(row["source"], "ledger")
        self.assertIn("changedAt", row)

    def test_audit_log_is_read_only(self):
        """审计接口不接受写入。"""
        self.client.force_authenticate(self.admin)
        resp = self.client.post(
            "/api/weight-logs/",
            {"rollId": self.changed.id, "oldValue": 1, "newValue": 2},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

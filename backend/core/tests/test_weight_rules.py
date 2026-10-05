from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import ClothRoll, DipRun, Loft, WeightAuditLog

User = get_user_model()


class WeightWriteTests(APITestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="admin", password="x", role=User.ROLE_ADMIN
        )
        self.admin2 = User.objects.create_user(
            username="admin2", password="x", role=User.ROLE_ADMIN
        )
        self.worker = User.objects.create_user(
            username="worker", password="x", role=User.ROLE_WORKER
        )
        self.loft = Loft.objects.create(name="L1")
        self.roll380 = ClothRoll.objects.create(
            loft=self.loft, roll_code="R-380", status=ClothRoll.STATUS_RAW,
            fabric_weight_gsm=380,
        )
        self.roll420 = ClothRoll.objects.create(
            loft=self.loft, roll_code="R-420", status=ClothRoll.STATUS_DIPPING,
            fabric_weight_gsm=420,
        )
        self.rollCured = ClothRoll.objects.create(
            loft=self.loft, roll_code="R-C", status=ClothRoll.STATUS_CURED,
            fabric_weight_gsm=450,
        )
        DipRun.objects.create(
            roll=self.rollCured,
            started_at=timezone.now() - timezone.timedelta(days=1),
            resin_pct=Decimal("30"),
            cure_hours=Decimal("14"),
        )

    def patch(self, user, roll, **payload):
        self.client.force_authenticate(user)
        return self.client.patch(f"/api/rolls/{roll.id}/", payload, format="json")

    # ---- 操作工 ----

    def test_worker_first_write_from_default_succeeds_and_audits(self):
        resp = self.patch(self.worker, self.roll380, fabricWeightGsm=400, expectedVersion=0)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.roll380.refresh_from_db()
        self.assertEqual(self.roll380.fabric_weight_gsm, 400)
        self.assertEqual(self.roll380.version, 1)
        log = WeightAuditLog.objects.get(roll=self.roll380)
        self.assertEqual((log.old_value, log.new_value), (380, 400))
        self.assertEqual(log.changed_by, self.worker)
        self.assertEqual(log.changed_by_name, "worker")

    def test_worker_cannot_touch_non_default_weight(self):
        resp = self.patch(self.worker, self.roll420, fabricWeightGsm=430, expectedVersion=0)
        self.assertEqual(resp.status_code, 403, resp.content)
        self.roll420.refresh_from_db()
        self.assertEqual(self.roll420.fabric_weight_gsm, 420)
        self.assertEqual(self.roll420.version, 0)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.roll420).count(), 0)

    def test_worker_cannot_rewrite_after_own_first_write(self):
        r1 = self.patch(self.worker, self.roll380, fabricWeightGsm=400, expectedVersion=0)
        self.assertEqual(r1.status_code, 200, r1.content)
        r2 = self.patch(self.worker, self.roll380, fabricWeightGsm=410, expectedVersion=1)
        self.assertEqual(r2.status_code, 403, r2.content)
        self.roll380.refresh_from_db()
        self.assertEqual(self.roll380.fabric_weight_gsm, 400)

    def test_worker_writing_380_is_noop(self):
        resp = self.patch(self.worker, self.roll380, fabricWeightGsm=380, expectedVersion=0)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.roll380.refresh_from_db()
        self.assertEqual(self.roll380.fabric_weight_gsm, 380)
        self.assertEqual(self.roll380.version, 0)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.roll380).count(), 0)

    # ---- 管理员 ----

    def test_admin_can_change_non_default_weight_and_audits(self):
        resp = self.patch(self.admin, self.roll420, fabricWeightGsm=440, expectedVersion=0)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.roll420.refresh_from_db()
        self.assertEqual(self.roll420.fabric_weight_gsm, 440)
        self.assertEqual(self.roll420.version, 1)
        log = WeightAuditLog.objects.get(roll=self.roll420)
        self.assertEqual((log.old_value, log.new_value), (420, 440))
        self.assertEqual(log.changed_by_name, "admin")

    def test_admin_can_write_first_value_too(self):
        resp = self.patch(self.admin, self.roll380, fabricWeightGsm=395, expectedVersion=0)
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.roll380).count(), 1)

    def test_superuser_without_admin_role_can_change(self):
        su = User.objects.create_superuser(
            username="root", password="x", role=User.ROLE_WORKER
        )
        resp = self.patch(su, self.roll420, fabricWeightGsm=500, expectedVersion=0)
        self.assertEqual(resp.status_code, 200, resp.content)

    # ---- 已固化全员锁定 ----

    def test_cured_roll_locked_for_admin_and_worker(self):
        for user in (self.admin, self.worker):
            resp = self.patch(user, self.rollCured, fabricWeightGsm=460, expectedVersion=0)
            self.assertEqual(resp.status_code, 403, (user.username, resp.content))
        self.rollCured.refresh_from_db()
        self.assertEqual(self.rollCured.fabric_weight_gsm, 450)
        self.assertEqual(self.rollCured.version, 0)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.rollCured).count(), 0)

    def test_cannot_sneak_weight_in_status_change_on_cured_roll(self):
        # status 保持 cured + 夹带克重，同样必须拒绝
        resp = self.patch(
            self.admin, self.rollCured,
            status="cured", fabricWeightGsm=460, expectedVersion=0,
        )
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_cannot_uncure_and_change_weight_in_one_request(self):
        # 同一请求把已固化卷改回原布并夹带克重，仍必须拒绝
        resp = self.patch(
            self.admin, self.rollCured,
            status="raw", fabricWeightGsm=460, expectedVersion=0,
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.rollCured.refresh_from_db()
        self.assertEqual(self.rollCured.fabric_weight_gsm, 450)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.rollCured).count(), 0)

    # ---- 版本与并发 ----

    def test_stale_version_conflicts(self):
        resp = self.patch(self.admin2, self.roll420, fabricWeightGsm=470, expectedVersion=9)
        self.assertEqual(resp.status_code, 409, resp.content)
        self.roll420.refresh_from_db()
        self.assertEqual(self.roll420.fabric_weight_gsm, 420)
        self.assertEqual(WeightAuditLog.objects.filter(roll=self.roll420).count(), 0)

    def test_two_admins_cross_edit_only_one_version_survives(self):
        # 管理员 A 先改成功
        a = self.patch(self.admin, self.roll420, fabricWeightGsm=440, expectedVersion=0)
        self.assertEqual(a.status_code, 200, a.content)
        # 管理员 B 仍拿旧版本号提交 -> 409，A 的版本留下
        b = self.patch(self.admin2, self.roll420, fabricWeightGsm=460, expectedVersion=0)
        self.assertEqual(b.status_code, 409, b.content)
        self.roll420.refresh_from_db()
        self.assertEqual(self.roll420.fabric_weight_gsm, 440)
        self.assertEqual(self.roll420.version, 1)
        logs = WeightAuditLog.objects.filter(roll=self.roll420)
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().changed_by, self.admin)
        # B 刷新后带新版本号可接力修改
        c = self.patch(self.admin2, self.roll420, fabricWeightGsm=460, expectedVersion=1)
        self.assertEqual(c.status_code, 200, c.content)
        self.roll420.refresh_from_db()
        self.assertEqual(self.roll420.fabric_weight_gsm, 460)
        self.assertEqual(self.roll420.version, 2)

    def test_weight_change_requires_expected_version(self):
        resp = self.patch(self.admin, self.roll420, fabricWeightGsm=440)
        self.assertEqual(resp.status_code, 400, resp.content)

    # ---- 创建夹带克重 ----

    def test_create_with_non_default_weight_rejected(self):
        self.client.force_authenticate(self.worker)
        resp = self.client.post(
            "/api/rolls/",
            {"loftId": self.loft.id, "rollCode": "R-NEW", "status": "raw",
             "fabricWeightGsm": 400, "notes": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.assertFalse(ClothRoll.objects.filter(roll_code="R-NEW").exists())

    def test_create_with_default_weight_ok(self):
        self.client.force_authenticate(self.worker)
        resp = self.client.post(
            "/api/rolls/",
            {"loftId": self.loft.id, "rollCode": "R-NEW2", "status": "raw",
             "fabricWeightGsm": 380, "notes": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)
        roll = ClothRoll.objects.get(roll_code="R-NEW2")
        self.assertEqual(roll.fabric_weight_gsm, 380)
        self.assertEqual(roll.version, 0)

    def test_create_with_stray_expected_version_does_not_500(self):
        self.client.force_authenticate(self.worker)
        resp = self.client.post(
            "/api/rolls/",
            {"loftId": self.loft.id, "rollCode": "R-NEW3", "status": "raw",
             "expectedVersion": 7, "notes": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

    def test_put_with_weight_change_respects_boundary(self):
        # 全量 PUT 入口同样强制分界
        self.client.force_authenticate(self.worker)
        resp = self.client.put(
            f"/api/rolls/{self.roll420.id}/",
            {"loftId": self.loft.id, "rollCode": "R-420", "status": "dipping",
             "fabricWeightGsm": 430, "expectedVersion": 0, "notes": ""},
            format="json",
        )
        self.assertEqual(resp.status_code, 403, resp.content)
        self.roll420.refresh_from_db()
        self.assertEqual(self.roll420.fabric_weight_gsm, 420)

    # ---- 非克重字段不受影响 ----

    def test_status_only_patch_does_not_require_version(self):
        resp = self.patch(self.worker, self.roll380, status="dipping")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.roll380.refresh_from_db()
        self.assertEqual(self.roll380.status, "dipping")
        self.assertEqual(WeightAuditLog.objects.count(), 0)

    # ---- 审计接口 ----

    def test_audit_list_visible_to_worker(self):
        self.patch(self.admin, self.roll420, fabricWeightGsm=440, expectedVersion=0)
        self.client.force_authenticate(self.worker)
        resp = self.client.get("/api/weight-audits/")
        self.assertEqual(resp.status_code, 200, resp.content)
        results = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(len(results), 1)
        row = results[0]
        self.assertEqual(row["rollCode"], "R-420")
        self.assertEqual(row["loftName"], "L1")
        self.assertEqual(row["changedBy"], "admin")
        self.assertEqual((row["oldValue"], row["newValue"]), (420, 440))

    def test_audit_list_filter_by_roll(self):
        self.patch(self.admin, self.roll420, fabricWeightGsm=440, expectedVersion=0)
        self.client.force_authenticate(self.worker)
        resp = self.client.get(f"/api/weight-audits/?rollId={self.roll380.id}")
        results = resp.data["results"] if "results" in resp.data else resp.data
        self.assertEqual(results, [])

    def test_audit_endpoint_read_only(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/weight-audits/", {}, format="json")
        self.assertEqual(resp.status_code, 405, resp.content)

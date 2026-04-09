import os
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from core.queue import (
    get_all_queues_status,
    initialize_default_queues,
    start_default_queues,
    stop_default_queues,
)
from core.zju_activity import ZJUActivityService
from web import app


class QueueRuntimeTests(unittest.TestCase):
    def tearDown(self):
        stop_default_queues()

    def test_queue_is_lazy_before_initialization(self):
        result = subprocess.run(
            [
                "python3",
                "-c",
                "from core.queue import get_all_queues_status; print(get_all_queues_status())",
            ],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("{'main_queue': None, 'content_queue': None}", result.stdout)

    def test_default_queues_can_be_initialized_without_starting_workers(self):
        main_queue, content_queue = initialize_default_queues(start_workers=False)
        self.assertFalse(main_queue.get_queue_info()["is_running"])
        self.assertFalse(content_queue.get_queue_info()["is_running"])

    def test_default_queues_can_start_explicitly(self):
        initialize_default_queues(start_workers=False)
        start_default_queues()
        status = get_all_queues_status()
        self.assertTrue(status["main_queue"]["is_running"])
        self.assertTrue(status["content_queue"]["is_running"])


class ActivityMetadataTests(unittest.TestCase):
    def test_list_activities_exposes_source_status_metadata(self):
        service = ZJUActivityService()
        source = {
            "id": "library",
            "name": "图书馆讲座",
            "url": "https://example.com",
            "source_type": "core",
            "source_channel": "website",
            "category": "core",
            "selectors": {},
        }
        activity = {
            "id": "activity-1",
            "title": "测试讲座",
            "college_id": "library",
            "college_name": "图书馆讲座",
            "activity_type": "讲座",
            "speaker": None,
            "speaker_title": None,
            "speaker_intro": None,
            "activity_date": "2099-04-10",
            "activity_time": "19:00",
            "location": "紫金港校区图书馆",
            "organizer": "图书馆讲座",
            "description": "测试数据",
            "cover_image": None,
            "source_url": "https://example.com/1",
            "registration_required": False,
            "registration_link": None,
            "source_type": "core",
            "source_channel": "website",
            "raw_date_text": "2099-04-10",
        }

        def fetch_source_items(_source):
            service._update_source_status(_source, ok=True, item_count=1, cached=False)
            return [activity]

        with patch.object(service, "_build_website_sources", return_value=[source]), patch.object(
            service, "_build_wechat_sources", return_value=[]
        ), patch.object(service, "_fetch_source_items", side_effect=fetch_source_items):
            result = service.list_activities(limit=10)

        self.assertEqual(result["freshness"], "fresh")
        self.assertEqual(result["total"], 1)
        self.assertIn("last_success_sync_at", result)
        self.assertIn("validation", result)
        self.assertEqual(result["validation"]["dropped_count"], 0)
        self.assertIn("source_metrics", result)
        self.assertEqual(result["source_metrics"][0]["activity_count"], 1)
        self.assertIn("source_status", result)
        self.assertEqual(result["source_status"]["last_success_sync_at"], result["last_success_sync_at"])
        self.assertEqual(result["source_status"]["ok_sources"], 1)
        self.assertEqual(result["source_status"]["error_sources"], 0)
        self.assertEqual(result["source_status"]["items"][0]["id"], "library")


class ApiSmokeTests(unittest.TestCase):
    def setUp(self):
        self._old_local_bypass = os.environ.get("MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED")
        os.environ["MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED"] = "True"
        self.client = TestClient(app)

    def tearDown(self):
        if self._old_local_bypass is None:
            os.environ.pop("MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED", None)
        else:
            os.environ["MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED"] = self._old_local_bypass

    def test_auth_session_requires_login_by_default(self):
        os.environ["MAINTENANCE_ALLOW_LOCAL_UNAUTHENTICATED"] = "False"
        with TestClient(app) as client:
            response = client.get("/api/v1/wx/auth/session")
        self.assertEqual(response.status_code, 401)

    def test_health_endpoints_expose_runtime_metadata(self):
        activity_payload = {
            "list": [],
            "total": 0,
            "generated_at": "2026-04-09T13:00:00Z",
            "last_success_sync_at": "2026-04-09T12:30:00Z",
            "freshness": "partial",
            "source_status": {
                "generated_at": "2026-04-09T13:00:00Z",
                "last_success_sync_at": "2026-04-09T12:30:00Z",
                "total_sources": 2,
                "attempted_sources": 2,
                "ok_sources": 1,
                "error_sources": 1,
                "items": [],
            },
            "source_metrics": [
                {
                    "id": "library",
                    "name": "图书馆讲座",
                    "activity_count": 1,
                    "upcoming_count": 1,
                    "complete_info_count": 1,
                    "info_completeness_ratio": 1.0,
                    "dropped_invalid_count": 0,
                    "source_channels": ["website"],
                    "source_type": "core",
                }
            ],
            "validation": {
                "valid_count": 1,
                "dropped_count": 0,
                "dropped_by_source": {},
                "invalid_examples": [],
            },
        }

        with patch("apis.sys_info.activity_service.list_activities", return_value=activity_payload), patch(
            "apis.sys_info.activity_service.get_runtime_health",
            return_value={"status": "partial"},
        ):
            live_response = self.client.get("/api/v1/wx/sys/health/live")
            ready_response = self.client.get("/api/v1/wx/sys/health/ready")
            source_response = self.client.get("/api/v1/wx/sys/source_status")
            source_metrics_response = self.client.get("/api/v1/wx/sys/source_metrics")

        self.assertEqual(live_response.status_code, 200)
        self.assertEqual(live_response.json()["data"]["status"], "alive")
        self.assertEqual(ready_response.status_code, 200)
        self.assertEqual(ready_response.json()["data"]["status"], "partial")
        self.assertEqual(ready_response.json()["data"]["last_success_sync_at"], "2026-04-09T12:30:00Z")
        self.assertEqual(source_response.status_code, 200)
        self.assertEqual(source_response.json()["data"]["ok_sources"], 1)
        self.assertEqual(source_metrics_response.status_code, 200)
        self.assertEqual(source_metrics_response.json()["data"]["items"][0]["id"], "library")

    def test_config_summary_endpoint_exposes_config_boundaries(self):
        with patch(
            "apis.sys_info.cfg.get_runtime_config_summary",
            return_value={
                "runtime_config_path": "/tmp/config.yaml",
                "activity_source_config_path": "/tmp/config.json",
                "boundaries": {
                    "config_json": "活动来源",
                    "config_yaml": "运行配置",
                    "environment_variables": "环境覆盖",
                },
                "detected_env_placeholders": ["DB"],
                "active_env_overrides": ["DB"],
            },
        ):
            response = self.client.get("/api/v1/wx/sys/config_summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["activity_source_config_path"], "/tmp/config.json")

    def test_health_ready_returns_503_for_degraded_runtime(self):
        with patch(
            "apis.sys_info.activity_service.get_source_status_summary",
            return_value={
                "generated_at": "2026-04-09T13:00:00Z",
                "freshness": "degraded",
                "last_success_sync_at": None,
                "total_sources": 2,
                "attempted_sources": 2,
                "ok_sources": 0,
                "error_sources": 2,
                "items": [],
            },
        ), patch(
            "apis.sys_info.activity_service.get_runtime_health",
            return_value={"status": "degraded"},
        ):
            response = self.client.get("/api/v1/wx/sys/health/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], 50302)
        self.assertEqual(response.json()["data"]["status"], "degraded")

    def test_activity_routes_return_expected_payloads(self):
        activity_payload = {
            "list": [{"id": "activity-1", "title": "测试讲座"}],
            "total": 1,
            "page": 1,
            "limit": 100,
            "generated_at": "2026-04-09T13:00:00Z",
            "last_success_sync_at": "2026-04-09T12:30:00Z",
            "freshness": "fresh",
            "source_status": {"total_sources": 1, "attempted_sources": 1, "ok_sources": 1, "error_sources": 0, "items": []},
        }
        colleges_payload = [{"id": "library", "name": "图书馆", "category": "core"}]
        detail_payload = {"id": "activity-1", "title": "测试讲座", "description": "详情"}

        with patch("apis.zju_activity.service.list_activities", return_value=activity_payload), patch(
            "apis.zju_activity.service.get_colleges", return_value=colleges_payload
        ), patch("apis.zju_activity.service.get_activity", return_value=detail_payload):
            activities_response = self.client.get("/api/v1/wx/activities")
            colleges_response = self.client.get("/api/v1/wx/colleges")
            detail_response = self.client.get("/api/v1/wx/activities/activity-1")

        self.assertEqual(activities_response.status_code, 200)
        self.assertEqual(activities_response.json()["data"]["freshness"], "fresh")
        self.assertEqual(colleges_response.status_code, 200)
        self.assertEqual(colleges_response.json()["data"][0]["id"], "library")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["data"]["id"], "activity-1")

    def test_sync_endpoint_returns_503_when_worker_is_not_running(self):
        class FakeQuery:
            def filter(self, *_args, **_kwargs):
                return self

            def first(self):
                return SimpleNamespace(
                    id="mp-test",
                    mp_name="测试公众号",
                    faker_id="faker-id",
                )

        class FakeSession:
            def query(self, *_args, **_kwargs):
                return FakeQuery()

            def close(self):
                return None

        with patch("apis.mps.DB.get_session", return_value=FakeSession()), patch(
            "apis.mps.TaskQueue.get_queue_info", return_value={"is_running": False}
        ):
            response = self.client.post("/api/v1/wx/mps/mp-test/sync")

        self.assertEqual(response.status_code, 503)
        self.assertIn("同步 worker 未运行", response.json()["detail"]["message"])
        self.assertEqual(response.json()["detail"]["category"], "service_state")

    def test_queue_status_and_history_endpoints_return_management_data(self):
        queue_snapshot = {
            "tag": "文章采集",
            "is_running": True,
            "pending_count": 1,
            "pending_tasks": [{"task_name": "测试任务"}],
            "current_task": {"task_name": "同步中"},
            "history_count": 2,
            "recent_history": [],
            "history_page": {
                "history": [{"task_name": "历史任务", "status": "completed"}],
                "total": 2,
                "page": 1,
                "page_size": 10,
                "total_pages": 1,
            },
        }
        history_page = {
            "history": [{"task_name": "历史任务", "status": "completed"}],
            "total": 2,
            "page": 1,
            "page_size": 10,
            "total_pages": 1,
        }

        with patch("apis.sys_info.TaskQueue.get_management_snapshot", return_value=queue_snapshot), patch(
            "apis.sys_info.ContentTaskQueue.get_management_snapshot", return_value={**queue_snapshot, "tag": "内容补抓"}
        ), patch("apis.sys_info.TaskQueue.get_history_page", return_value=history_page):
            status_response = self.client.get("/api/v1/wx/sys/queue_status")
            history_response = self.client.get("/api/v1/wx/sys/queue_history?queue_name=main&page=1&page_size=10")

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["data"]["main_queue"]["tag"], "文章采集")
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_response.json()["data"]["history"][0]["task_name"], "历史任务")

    def test_source_refresh_endpoint_returns_manual_refresh_result(self):
        refresh_payload = {
            "source": {
                "id": "library",
                "name": "图书馆讲座",
                "source_channel": "website",
                "source_type": "core",
            },
            "refresh_mode": "direct_fetch",
            "item_count": 2,
            "valid_item_count": 2,
            "dropped_count": 0,
            "source_metric": {"id": "library", "activity_count": 2},
            "source_status": {"id": "library", "status": "ok"},
            "upstream_sync_required": False,
            "note": "官网来源已直接重新抓取。",
        }

        with patch("apis.sys_info.activity_service.refresh_source", return_value=refresh_payload):
            response = self.client.post("/api/v1/wx/sys/sources/library/refresh?source_channel=website")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["source"]["id"], "library")
        self.assertEqual(response.json()["data"]["refresh_mode"], "direct_fetch")


if __name__ == "__main__":
    unittest.main()

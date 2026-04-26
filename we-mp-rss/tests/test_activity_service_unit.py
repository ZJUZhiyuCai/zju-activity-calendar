import unittest
from unittest.mock import patch

from core.activity_sources.wechat import WechatActivityAdapter
from core.non_activity_classifier import classify_record_bucket
from core.zju_activity import ZJUActivityService


class ActivityServiceUnitTests(unittest.TestCase):
    def setUp(self):
        self.service = ZJUActivityService()

    def test_dedupe_prefers_richer_duplicate_record(self):
        lean = {
            "id": "lean",
            "title": "人工智能讲座",
            "college_id": "cs",
            "activity_date": "2099-04-10",
            "activity_time": None,
            "location": None,
            "speaker": None,
            "description": "短描述",
            "source_channel": "website",
        }
        rich = {
            "id": "rich",
            "title": "人工智能讲座",
            "college_id": "cs",
            "activity_date": "2099-04-10",
            "activity_time": "19:00",
            "location": "紫金港",
            "speaker": "张老师",
            "description": "更完整的活动说明",
            "source_channel": "wechat",
        }

        deduped = self.service._dedupe_activities([lean, rich])

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0]["id"], "rich")

    def test_decorate_activity_marks_upcoming_and_campus(self):
        activity = self.service._decorate_activity(
            {
                "id": "activity-1",
                "title": "图书馆讲座",
                "college_id": "library",
                "source_type": "core",
                "activity_date": "2099-04-10",
                "activity_time": "19:00",
                "location": "紫金港校区图书馆报告厅",
                "description": "这是一个字段较完整的活动预告，包含时间地点主讲人与访问原文链接，便于验证来源置信度评分。",
                "speaker": "主讲人",
                "source_url": "https://example.com/library/1",
            }
        )

        self.assertTrue(activity["is_upcoming"])
        self.assertEqual(activity["campus"], "紫金港")
        self.assertGreater(activity["student_score"], 0)
        self.assertEqual(activity["info_completeness_level"], "complete")
        self.assertGreaterEqual(activity["source_confidence_score"], 0.8)
        self.assertEqual(activity["source_confidence_level"], "high")
        self.assertIn(activity["preview_reason"], {"校级入口", "紫金港校区", "晚间场", "时间地点明确", "主讲人明确", "近期活动"})

    def test_student_view_date_sort_is_upgraded_to_relevance(self):
        source = {
            "id": "library",
            "name": "图书馆讲座",
            "url": "https://example.com",
            "source_type": "core",
            "source_channel": "website",
            "category": "core",
            "selectors": {},
        }
        farther = {
            "id": "later",
            "title": "一周后活动",
            "college_id": "library",
            "college_name": "图书馆讲座",
            "activity_type": "讲座",
            "speaker": None,
            "speaker_title": None,
            "speaker_intro": None,
            "activity_date": "2099-04-16",
            "activity_time": "19:00",
            "location": "紫金港",
            "organizer": "图书馆",
            "description": "远期活动",
            "cover_image": None,
            "source_url": "https://example.com/later",
            "registration_required": False,
            "registration_link": None,
            "source_type": "core",
            "source_channel": "website",
            "raw_date_text": "2099-04-16",
        }
        nearer = {
            **farther,
            "id": "nearer",
            "title": "明天活动",
            "activity_date": "2099-04-10",
            "source_url": "https://example.com/nearer",
            "raw_date_text": "2099-04-10",
        }

        with patch.object(self.service, "_build_website_sources", return_value=[source]), patch.object(
            self.service, "_build_wechat_sources", return_value=[]
        ), patch.object(self.service, "_fetch_source_items", return_value=[farther, nearer]):
            result = self.service.list_activities(limit=10, student_view=True, sort_by="date")

        self.assertEqual(result["sort_by"], "relevance")
        self.assertEqual(result["list"][0]["id"], "nearer")

    def test_build_sources_merges_registered_channels(self):
        config = {
            "data_sources": {
                "websites": {
                    "core": [
                        {
                            "id": "library",
                            "url": "https://example.com/list",
                            "parser_type": "zju_list",
                        }
                    ],
                    "colleges": [],
                },
                "wechat_accounts": {
                    "core": [
                        {
                            "type": "library",
                            "name": "浙大图书馆",
                        }
                    ],
                    "colleges": [],
                },
            },
            "crawl_config": {
                "parser": {
                    "zju_list": {
                        "list_selector": ".item",
                        "title_selector": "a",
                        "date_selector": ".date",
                    }
                }
            },
        }

        with patch.object(self.service, "_load_config", return_value=config):
            sources = self.service._build_sources()

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["id"], "library")
        self.assertEqual(sources[0]["source_channels"], ["website", "wechat"])

    def test_list_activities_dispatches_via_registered_service_methods(self):
        website_source = {
            "id": "library",
            "name": "图书馆讲座",
            "url": "https://example.com",
            "source_type": "core",
            "source_channel": "website",
            "category": "core",
            "selectors": {},
        }
        wechat_source = {
            "id": "library",
            "cache_key": "wechat:library",
            "name": "图书馆讲座",
            "url": None,
            "source_type": "core",
            "source_channel": "wechat",
            "category": "core",
            "mp_name": "浙大图书馆",
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
            "location": "紫金港",
            "organizer": "图书馆",
            "description": "测试",
            "cover_image": None,
            "source_url": "https://example.com/1",
            "registration_required": False,
            "registration_link": None,
            "source_type": "core",
            "source_channel": "website",
            "raw_date_text": "2099-04-10",
        }

        with patch.object(self.service, "_build_website_sources", return_value=[website_source]) as build_website, patch.object(
            self.service, "_build_wechat_sources", return_value=[wechat_source]
        ) as build_wechat, patch.object(self.service, "_fetch_source_items", return_value=[activity]) as fetch_website, patch.object(
            self.service, "_fetch_wechat_items", return_value=[]
        ) as fetch_wechat:
            result = self.service.list_activities(limit=10)

        self.assertEqual(result["total"], 1)
        build_website.assert_called_once()
        build_wechat.assert_called_once()
        fetch_website.assert_called_once_with(website_source)
        fetch_wechat.assert_called_once_with(wechat_source)

    def test_invalid_activity_is_dropped_by_schema_validation(self):
        source = {
            "id": "library",
            "name": "图书馆讲座",
            "url": "https://example.com",
            "source_type": "core",
            "source_channel": "website",
            "category": "core",
            "selectors": {},
        }
        invalid_activity = {
            "id": "broken-1",
            "title": "缺日期活动",
            "college_id": "library",
            "college_name": "图书馆讲座",
            "activity_type": "讲座",
            "activity_date": "",
            "source_url": "https://example.com/broken",
            "source_type": "core",
            "source_channel": "website",
        }

        with patch.object(self.service, "_build_website_sources", return_value=[source]), patch.object(
            self.service, "_build_wechat_sources", return_value=[]
        ), patch.object(self.service, "_fetch_source_items", return_value=[invalid_activity]):
            result = self.service.list_activities(limit=10)

        self.assertEqual(result["total"], 0)
        self.assertEqual(result["validation"]["dropped_count"], 1)
        self.assertEqual(result["source_metrics"][0]["dropped_invalid_count"], 1)

    def test_refresh_source_returns_per_source_summary(self):
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
            "speaker": "测试主讲人",
            "speaker_title": None,
            "speaker_intro": None,
            "activity_date": "2099-04-10",
            "activity_time": "19:00",
            "location": "紫金港",
            "organizer": "图书馆",
            "description": "这是一条足够长的测试活动描述，用来验证来源手动刷新接口会返回来源级统计和质量元数据。",
            "cover_image": None,
            "source_url": "https://example.com/1",
            "registration_required": False,
            "registration_link": None,
            "source_type": "core",
            "source_channel": "website",
            "raw_date_text": "2099-04-10",
        }

        with patch.object(self.service, "_build_website_sources", return_value=[source]), patch.object(
            self.service, "_fetch_source_items", return_value=[activity]
        ):
            result = self.service.refresh_source(source_id="library", source_channel="website")

        self.assertEqual(result["source"]["id"], "library")
        self.assertEqual(result["refresh_mode"], "direct_fetch")
        self.assertEqual(result["item_count"], 1)
        self.assertEqual(result["valid_item_count"], 1)
        self.assertEqual(result["dropped_count"], 0)
        self.assertEqual(result["source_metric"]["activity_count"], 1)
        self.assertFalse(result["upstream_sync_required"])

    def test_wechat_adapter_extracts_multiline_time_and_location_without_colon(self):
        adapter = WechatActivityAdapter()
        service = type(
            "FakeService",
            (),
            {
                "_load_config": lambda self: {
                    "crawl_config": {
                        "keywords": {
                            "primary": ["活动报名", "分享会"],
                            "series": [],
                            "exclude": [],
                        }
                    }
                }
            },
        )()
        source = {
            "id": "library",
            "cache_key": "wechat:library",
            "name": "图书馆讲座",
            "source_type": "core",
        }
        article = {
            "id": "article-1",
            "title": "活动报名 | 翻开春天，户外图书馆邀你来玩！",
            "description": "特邀嘉宾杨澜、紫金陈座谈分享，等你报名！",
            "url": "https://example.com/article-1",
            "publish_time": 1776654000,
            "content_html": """
                <div>
                  <p>分享主题</p>
                  <p>习得幸福的能力</p>
                  <p><strong>活动时间</strong></p>
                  <p>4月23日（周四）14:40</p>
                  <p><strong>活动地点</strong></p>
                  <p>紫金港校区启真湖大草坪</p>
                  <p><strong>主讲人简介</strong></p>
                  <p>杨澜，中国著名主持人。</p>
                </div>
            """,
        }

        activity = adapter._article_to_activity(service, source, article, use_llm=False)

        self.assertIsNotNone(activity)
        self.assertEqual(activity["activity_date"], "2026-04-23")
        self.assertEqual(activity["activity_time"], "4月23日（周四）14:40")
        self.assertEqual(activity["location"], "紫金港校区启真湖大草坪")

    def test_wechat_adapter_extracts_inline_time_without_colon(self):
        adapter = WechatActivityAdapter()
        service = type(
            "FakeService",
            (),
            {
                "_load_config": lambda self: {
                    "crawl_config": {
                        "keywords": {
                            "primary": ["活动报名", "分享会"],
                            "series": [],
                            "exclude": [],
                        }
                    }
                }
            },
        )()
        source = {
            "id": "library",
            "cache_key": "wechat:library",
            "name": "图书馆讲座",
            "source_type": "core",
        }
        article = {
            "id": "article-2",
            "title": "活动报名 | 图书分享会",
            "description": "欢迎参加分享会",
            "url": "https://example.com/article-2",
            "publish_time": 1776654000,
            "content": "分享会预告\n活动时间4月25日（周六）14:00\n活动地点紫金港校区启真湖大草坪\n",
        }

        activity = adapter._article_to_activity(service, source, article, use_llm=False)

        self.assertIsNotNone(activity)
        self.assertEqual(activity["activity_date"], "2026-04-25")
        self.assertEqual(activity["activity_time"], "4月25日（周六）14:00")
        self.assertEqual(activity["location"], "紫金港校区启真湖大草坪")

    def test_wechat_adapter_does_not_treat_time_is_tight_as_activity_time(self):
        adapter = WechatActivityAdapter()
        article = {
            "id": "article-time-tight",
            "title": "考研冲刺站——“源梦紫金”考研经验分享会来啦！",
            "description": "叮！你的考试周即将到来，请准备好～",
            "url": "https://example.com/article-time-tight",
            "publish_time": 1776654000,
            "content": "考试周即将到来，时间紧，任务重。欢迎关注后续安排。",
        }

        metadata = adapter.extract_article_metadata(article)

        self.assertIsNone(metadata["activity_time"])
        self.assertIsNone(metadata["activity_date"])

    def test_recap_title_is_classified_as_non_activity_even_with_activity_words(self):
        bucket, reason = classify_record_bucket(
            title="E同研学室丨洞察学术前沿 赋能科技创新与人才培养分享会顺利举办",
            description="4月10日上午，双方围绕学术前沿、人才培养等议题进行学术报告。",
            activity_date="2026-04-10",
        )

        self.assertEqual(bucket, "non_activity")
        self.assertEqual(reason, "title_recap_signal")

    def test_detail_enrichment_extracts_multiline_time_and_location_without_colon(self):
        activity = {
            "id": "activity-1",
            "title": "活动报名 | 图书分享会",
            "college_id": "library",
            "college_name": "图书馆讲座",
            "activity_type": "讲座",
            "activity_date": "2026-04-23",
            "activity_time": None,
            "location": None,
            "source_url": "https://example.com/detail",
            "source_type": "core",
            "source_channel": "wechat",
        }
        html = """
            <html>
              <body>
                <div class="content">
                  <p><strong>活动时间</strong></p>
                  <p>4月23日（周四）14:40</p>
                  <p><strong>活动地点</strong></p>
                  <p>紫金港校区启真湖大草坪</p>
                </div>
              </body>
            </html>
        """

        with patch.object(self.service, "_fetch_html", return_value=html):
            enriched = self.service._enrich_activity_detail(activity)

        self.assertEqual(enriched["activity_time"], "4月23日（周四）14:40")
        self.assertEqual(enriched["location"], "紫金港校区启真湖大草坪")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""
文章内容补全服务 - 集成到 APScheduler

功能：
1. 定时抓取空内容文章（每分钟一篇，分散请求）
2. 风控检测与自动暂停
3. 持久化任务状态

用法：
    由 web.py 在 startup 时自动启动
"""

import json
import os
import random
import time
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

from core.print import print_error, print_info, print_warning

# 状态文件路径
STATE_FILE = Path("data/content_filler_state.json")
DB_URL = "sqlite:///data/db.db"

# 风控配置
RATE_LIMIT_PAUSE_MINUTES = 30  # 触发风控后暂停30分钟
MAX_RETRIES = 3  # 单篇文章最大重试次数


class ContentFillerState:
    """持久化任务状态"""

    def __init__(self):
        self.state = {
            "last_run_at": None,
            "last_article_id": None,
            "last_article_title": None,
            "rate_limited_at": None,  # 风控触发时间
            "rate_limited_until": None,  # 风控暂停结束时间
            "success_count": 0,
            "fail_count": 0,
            "rate_limited_count": 0,
            "updated_at": None,
        }
        self._load()

    def _load(self):
        """从文件加载状态"""
        if STATE_FILE.exists():
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self.state.update(loaded)
            except Exception as e:
                print_warning(f"加载 content_filler 状态失败: {e}")

    def save(self):
        """保存状态到文件"""
        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            self.state["updated_at"] = datetime.now().isoformat()
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print_error(f"保存 content_filler 状态失败: {e}")

    def is_rate_limited(self) -> bool:
        """检查是否处于风控暂停期"""
        if self.state.get("rate_limited_until"):
            until = datetime.fromisoformat(self.state["rate_limited_until"])
            if datetime.now() < until:
                remaining = (until - datetime.now()).total_seconds() // 60
                print_warning(f"ContentFiller 处于风控暂停期，还剩 {remaining:.0f} 分钟")
                return True
            else:
                # 暂停期已过，清除状态
                self.state["rate_limited_at"] = None
                self.state["rate_limited_until"] = None
                self.save()
        return False

    def mark_rate_limited(self):
        """标记触发风控"""
        now = datetime.now()
        until = now.timestamp() + RATE_LIMIT_PAUSE_MINUTES * 60
        self.state["rate_limited_at"] = now.isoformat()
        self.state["rate_limited_until"] = datetime.fromtimestamp(until).isoformat()
        self.state["rate_limited_count"] = self.state.get("rate_limited_count", 0) + 1
        self.save()
        print_warning(f"ContentFiller 触发风控，暂停 {RATE_LIMIT_PAUSE_MINUTES} 分钟")

    def record_success(self, article_id: str, title: str):
        """记录成功"""
        self.state["last_run_at"] = datetime.now().isoformat()
        self.state["last_article_id"] = article_id
        self.state["last_article_title"] = title
        self.state["success_count"] = self.state.get("success_count", 0) + 1
        self.save()

    def record_fail(self, error: str):
        """记录失败"""
        self.state["last_run_at"] = datetime.now().isoformat()
        self.state["fail_count"] = self.state.get("fail_count", 0) + 1
        self.save()


def get_user_agent() -> str:
    """获取随机 User-Agent"""
    return random.choice([
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
    ])


def extract_text_from_html(html: str) -> str:
    """
    从 HTML 提取纯文本，处理微信的 CSS 隐藏问题
    微信使用 visibility: hidden 隐藏内容，get_text() 会返回空
    这里通过删除所有标签来提取文本
    """
    from bs4 import BeautifulSoup
    import re

    soup = BeautifulSoup(html, "html.parser")

    # 移除 script 和 style 标签
    for tag in soup(["script", "style"]):
        tag.decompose()

    # 获取文本
    text = soup.get_text()

    # 清理多余空行
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def fetch_article_content(url: str) -> dict:
    """抓取单篇文章内容"""
    headers = {
        "User-Agent": get_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://mp.weixin.qq.com/",
        "Connection": "keep-alive",
    }

    try:
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()
        html = response.text

        # 检查风控
        if "当前环境异常" in html or "完成验证后即可继续访问" in html:
            return {"success": False, "error": "rate_limited", "content": "", "content_html": ""}

        # 解析内容
        soup = BeautifulSoup(html, "html.parser")
        content_div = soup.select_one("#js_content") or soup.select_one(".rich_media_content")

        if content_div:
            content_html = str(content_div)
            # 使用自定义提取方法处理 CSS 隐藏问题
            content_text = extract_text_from_html(content_html)
            # 如果还是空，尝试使用 visible 文本提取
            if not content_text.strip():
                content_text = content_div.get_text("\n", strip=True)
        else:
            content_html = html
            content_text = extract_text_from_html(html)

        # 最终清理
        lines = [line.strip() for line in content_text.splitlines() if line.strip()]
        content_text = "\n".join(lines)

        # 如果内容为空，标记为失败避免重复抓取
        if not content_text.strip():
            return {"success": False, "error": "empty_content", "content": "", "content_html": ""}

        return {
            "success": True,
            "content": content_text,
            "content_html": content_html,
            "length": len(content_text),
        }

    except requests.exceptions.Timeout:
        return {"success": False, "error": "timeout", "content": "", "content_html": ""}
    except Exception as e:
        return {"success": False, "error": str(e), "content": "", "content_html": ""}


def get_next_empty_article(engine) -> dict | None:
    """获取下一篇需要补全内容的文章（只选从未抓取的，排除有内容和已标记为空的）"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, mp_id, title, url, publish_time
            FROM articles
            WHERE (content IS NULL OR content = '')
              AND (content IS NULL OR content != '[empty]')
              AND url IS NOT NULL
            ORDER BY publish_time DESC
            LIMIT 1
        """))
        row = result.fetchone()
        if row:
            return dict(row._mapping)
    return None


def update_article_content(engine, article_id: str, content: str, content_html: str):
    """更新文章内容"""
    with engine.connect() as conn:
        conn.execute(text("""
            UPDATE articles
            SET content = :content, content_html = :content_html, updated_at = :updated_at
            WHERE id = :id
        """), {
            "id": article_id,
            "content": content,
            "content_html": content_html,
            "updated_at": int(time.time()),
        })
        conn.commit()


def fill_one_article():
    """
    主任务：抓取一篇空内容文章
    由 APScheduler 每分钟调用一次
    """
    state = ContentFillerState()

    # 检查风控暂停期
    if state.is_rate_limited():
        return

    engine = create_engine(DB_URL)

    # 获取下一篇空内容文章
    article = get_next_empty_article(engine)
    if not article:
        return  # 没有需要处理的文章

    article_id = article["id"]
    title = article["title"]
    url = article["url"]

    # 抓取内容
    result = fetch_article_content(url)

    if not result["success"]:
        if result.get("error") == "rate_limited":
            state.mark_rate_limited()
            print_warning(f"ContentFiller 触发风控: {title[:40]}...")
        elif result.get("error") == "empty_content":
            # 内容为空，标记为特殊值避免重复抓取
            update_article_content(engine, article_id, "[empty]", "")
            state.record_fail("empty_content")
            print_warning(f"ContentFiller 内容为空: {title[:40]}...")
        else:
            state.record_fail(result.get("error", "未知错误"))
            print_error(f"ContentFiller 抓取失败: {title[:40]}... - {result.get('error')}")
        return

    # 更新数据库
    update_article_content(engine, article_id, result["content"], result["content_html"])
    state.record_success(article_id, title)

    print_info(f"ContentFiller 成功: {title[:40]}... ({result['length']}字)")


def get_filler_status() -> dict:
    """获取 filler 状态（用于 API 查询）"""
    state = ContentFillerState()
    return {
        **state.state,
        "is_rate_limited": state.is_rate_limited(),
        "state_file": str(STATE_FILE),
    }


if __name__ == "__main__":
    # 手动测试
    fill_one_article()

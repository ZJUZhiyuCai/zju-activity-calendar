#!/usr/bin/env python3
"""
公众号文章内容补全测试程序

功能：
1. 查询 articles 表中 content 为空的记录
2. 逐个抓取内容（带延迟，避免触发风控）
3. 用正则提取时间、地点、主讲人等信息
4. 更新到数据库

用法：
    python3 fill_article_content.py --limit 5 --interval 60
"""

import argparse
import random
import re
import time
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text

# 数据库连接
DB_URL = "sqlite:///data/db.db"


def get_empty_articles(engine, limit: int = 10, mp_id: str = None):
    """获取内容为空的文章列表"""
    with engine.connect() as conn:
        if mp_id:
            result = conn.execute(text("""
                SELECT id, mp_id, title, url, description, publish_time
                FROM articles
                WHERE (content IS NULL OR content = '') AND url IS NOT NULL
                  AND mp_id = :mp_id
                ORDER BY publish_time DESC
                LIMIT :limit
            """), {"mp_id": mp_id, "limit": limit})
        else:
            result = conn.execute(text("""
                SELECT id, mp_id, title, url, description, publish_time
                FROM articles
                WHERE (content IS NULL OR content = '') AND url IS NOT NULL
                ORDER BY publish_time DESC
                LIMIT :limit
            """), {"limit": limit})
        return [dict(row._mapping) for row in result]


def fetch_article_content(url: str, use_playwright: bool = False) -> dict:
    """
    抓取文章内容
    优先使用 requests，失败时可选 Playwright
    """
    import requests

    headers = {
        "User-Agent": random.choice([
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        ]),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Referer": "https://mp.weixin.qq.com/",
    }

    try:
        # 使用 session 保持连接
        session = requests.Session()
        response = session.get(url, headers=headers, timeout=30, allow_redirects=True)
        response.raise_for_status()

        html = response.text

        # 检查是否被风控
        if "当前环境异常" in html or "完成验证后即可继续访问" in html:
            return {
                "success": False,
                "error": "rate_limited",
                "content": "",
                "content_html": "",
            }

        # 解析 HTML
        soup = BeautifulSoup(html, "html.parser")

        # 提取正文
        content_div = soup.select_one("#js_content") or soup.select_one(".rich_media_content")
        content_html = str(content_div) if content_div else html
        content_text = content_div.get_text("\n", strip=True) if content_div else soup.get_text("\n", strip=True)

        # 清理文本
        content_text = clean_text(content_text)

        return {
            "success": True,
            "content": content_text,
            "content_html": content_html,
            "title": soup.select_one("#activity_name") or soup.title,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "content": "",
            "content_html": "",
        }


def clean_text(text: str) -> str:
    """清理文本内容"""
    if not text:
        return ""
    # 移除多余空行
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return "\n".join(lines)


def extract_activity_info(text: str) -> dict:
    """
    从正文提取活动信息
    """
    info = {
        "speaker": None,
        "activity_time": None,
        "location": None,
        "activity_date": None,
    }

    if not text:
        return info

    # 主讲人/报告人/分享人
    speaker_patterns = [
        r"(?:主讲人|报告人|分享人|嘉宾|主讲)\s*[:：]\s*([^\n]{2,30})",
        r"(?:主讲|报告)\s*[:：]\s*([^\n]{2,30})",
    ]
    for pattern in speaker_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["speaker"] = match.group(1).strip()
            break

    # 活动时间
    time_patterns = [
        r"(?:活动时间|讲座时间|时间)\s*[:：]\s*([^\n]{5,50})",
        r"(?:时间|Time)\s*[:：]\s*([^\n]{5,50})",
    ]
    for pattern in time_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["activity_time"] = match.group(1).strip()
            break

    # 地点
    location_patterns = [
        r"(?:活动地点|讲座地点|地点|Location)\s*[:：]\s*([^\n]{3,40})",
        r"(?:地点|Place)\s*[:：]\s*([^\n]{3,40})",
    ]
    for pattern in location_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            info["location"] = match.group(1).strip()
            break

    # 提取日期 (从 activity_time 或正文)
    date_patterns = [
        r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        r"(\d{4})-(\d{2})-(\d{2})",
        r"(\d{4})/(\d{2})/(\d{2})",
    ]
    search_text = info["activity_time"] or text[:500]
    for pattern in date_patterns:
        match = re.search(pattern, search_text)
        if match:
            info["activity_date"] = f"{match.group(1)}-{match.group(2).zfill(2)}-{match.group(3).zfill(2)}"
            break

    return info


def update_article_content(engine, article_id: str, content: str, content_html: str = ""):
    """更新文章内容到数据库"""
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


def main():
    parser = argparse.ArgumentParser(description="补全公众号文章内容")
    parser.add_argument("--limit", type=int, default=5, help="最多处理多少篇")
    parser.add_argument("--interval", type=int, default=60, help="每篇间隔秒数（默认60秒）")
    parser.add_argument("--mp-id", type=str, help="只处理指定公众号ID")
    args = parser.parse_args()

    engine = create_engine(DB_URL)

    print(f"[{datetime.now().strftime('%H:%M:%S')}] 开始补全文章内容...")
    print(f"参数: limit={args.limit}, interval={args.interval}s")
    print()

    # 获取空内容文章
    articles = get_empty_articles(engine, args.limit, args.mp_id)

    if not articles:
        print("没有需要补全的文章（所有文章已有内容）")
        return

    print(f"找到 {len(articles)} 篇需要补全的文章\n")

    success_count = 0
    fail_count = 0
    rate_limited = False

    for i, article in enumerate(articles, 1):
        if rate_limited:
            print(f"[{i}/{len(articles)}] 跳过（已被风控）: {article['title'][:40]}")
            continue

        print(f"[{i}/{len(articles)}] 处理: {article['title'][:50]}...")
        print(f"      URL: {article['url'][:60]}...")

        # 抓取内容
        result = fetch_article_content(article['url'])

        if not result['success']:
            if result.get('error') == 'rate_limited':
                print(f"      ❌ 触发风控（环境异常），停止处理")
                rate_limited = True
                fail_count += 1
            else:
                print(f"      ❌ 抓取失败: {result.get('error', '未知错误')}")
                fail_count += 1
            print()
            continue

        # 提取活动信息
        info = extract_activity_info(result['content'])

        # 更新数据库
        update_article_content(
            engine,
            article['id'],
            result['content'],
            result['content_html']
        )

        success_count += 1

        print(f"      ✅ 成功抓取，内容长度: {len(result['content'])} 字符")
        if info['speaker']:
            print(f"      👤 主讲人: {info['speaker']}")
        if info['activity_date']:
            print(f"      📅 日期: {info['activity_date']}")
        if info['activity_time']:
            print(f"      ⏰ 时间: {info['activity_time']}")
        if info['location']:
            print(f"      📍 地点: {info['location']}")
        print()

        # 间隔等待（最后一篇不等待）
        if i < len(articles):
            wait = args.interval + random.randint(-5, 5)
            print(f"      ⏳ 等待 {wait} 秒...")
            time.sleep(wait)
            print()

    print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 处理完成:")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    if rate_limited:
        print(f"  ⚠️ 触发风控，建议稍后再试或换用住宅代理")


if __name__ == "__main__":
    main()

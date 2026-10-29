#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import html
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

# =========================
# 配置
# =========================
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "").strip()
WECOM_WEBHOOK = os.getenv("WECOM_WEBHOOK", "").strip()

TRENDING_URL = "https://github.com/trending"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

PERIODS = [
    ("daily", "日榜", "Daily"),
    ("weekly", "周榜", "Weekly"),
    ("monthly", "月榜", "Monthly"),
]

MAX_REPOS_PER_PERIOD = 10  # 每个榜单取前 N 个，避免消息过长


# =========================
# 抓取
# =========================
def fetch_trending(since: str) -> list[dict]:
    """抓取 github.com/trending?since=daily/weekly/monthly"""
    url = f"{TRENDING_URL}?since={since}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = soup.select("article.Box-row")
    repos = []

    for article in articles[:MAX_REPOS_PER_PERIOD]:
        try:
            # 仓库名
            h2 = article.select_one("h2 a")
            if not h2:
                continue
            repo_path = h2.get("href", "").strip("/")
            if not repo_path or "/" not in repo_path:
                continue

            # 描述
            desc_el = article.select_one("p")
            description = desc_el.get_text(" ", strip=True) if desc_el else ""
            if len(description) > 160:
                description = description[:157] + "..."

            # 语言
            lang_el = article.select_one('[itemprop="programmingLanguage"]')
            language = lang_el.get_text(strip=True) if lang_el else "N/A"

            # Star / Fork（页面上的数字，通常带 k 后缀）
            stat_items = article.select("a.Link--muted")
            stars = "N/A"
            forks = "N/A"
            for a in stat_items:
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "/stargazers" in href:
                    stars = text
                elif "/forks" in href or "/network/members" in href:
                    forks = text

            # 本期 Star 增长（"x stars today/this week/this month"）
            growth = ""
            growth_el = article.select_one("span.d-inline-block.float-sm-right")
            if growth_el:
                growth = growth_el.get_text(" ", strip=True)

            repos.append(
                {
                    "repo": repo_path,
                    "url": f"https://github.com/{repo_path}",
                    "description": description or "No description",
                    "language": language,
                    "stars": stars,
                    "forks": forks,
                    "growth": growth,
                }
            )
        except Exception as e:
            print(f"[WARN] parse item failed: {e}", file=sys.stderr)
            continue

    return repos


# =========================
# 格式化：PushPlus（HTML 模板，样式更好控制）
# =========================
def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


def build_pushplus_html(all_data: dict[str, list[dict]]) -> str:
    """生成带内联样式的好看 HTML 表格"""
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    parts = [
        f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
                    max-width:760px;margin:0 auto;padding:8px;background:#f6f8fa;color:#24292f;">
          <h2 style="margin:0 0 4px 0;font-size:20px;color:#0f172a;">GitHub Trending · 每日推送</h2>
          <p style="margin:0 0 16px 0;font-size:12px;color:#57606a;">北京时间 {now_bj}</p>
        """
    ]

    for period_key, label_cn, label_en in PERIODS:
        repos = all_data.get(period_key, [])
        parts.append(
            f"""
            <div style="margin:18px 0 8px 0;">
              <span style="display:inline-block;padding:3px 10px;border-radius:999px;
                           background:#0969da;color:#ffffff;font-size:13px;font-weight:600;">
                {label_cn} / {label_en}
              </span>
            </div>
            """
        )

        if not repos:
            parts.append(
                '<p style="font-size:13px;color:#57606a;margin:6px 0;">暂无数据</p>'
            )
            continue

        parts.append(
            """
            <table style="width:100%;border-collapse:collapse;font-size:12px;
                          background:#ffffff;border:1px solid #d0d7de;border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:#f0f3f6;color:#24292f;text-align:left;">
                  <th style="padding:8px 6px;border-bottom:1px solid #d0d7de;width:28px;">#</th>
                  <th style="padding:8px 6px;border-bottom:1px solid #d0d7de;">项目</th>
                  <th style="padding:8px 6px;border-bottom:1px solid #d0d7de;">语言</th>
                  <th style="padding:8px 6px;border-bottom:1px solid #d0d7de;">Star</th>
                  <th style="padding:8px 6px;border-bottom:1px solid #d0d7de;">本期增长</th>
                </tr>
              </thead>
              <tbody>
            """
        )

        for idx, repo in enumerate(repos, start=1):
            bg = "#ffffff" if idx % 2 == 1 else "#fafbfc"
            parts.append(
                f"""
                <tr style="background:{bg};">
                  <td style="padding:7px 6px;border-bottom:1px solid #eaeef2;color:#57606a;">{idx}</td>
                  <td style="padding:7px 6px;border-bottom:1px solid #eaeef2;">
                    <a href="{esc(repo['url'])}" style="color:#0969da;text-decoration:none;font-weight:600;">
                      {esc(repo['repo'])}
                    </a>
                    <div style="color:#57606a;font-size:11px;line-height:1.35;margin-top:2px;">
                      {esc(repo['description'])}
                    </div>
                  </td>
                  <td style="padding:7px 6px;border-bottom:1px solid #eaeef2;color:#24292f;">{esc(repo['language'])}</td>
                  <td style="padding:7px 6px;border-bottom:1px solid #eaeef2;color:#24292f;">{esc(repo['stars'])}</td>
                  <td style="padding:7px 6px;border-bottom:1px solid #eaeef2;color:#1a7f37;">{esc(repo['growth'] or '-')}</td>
                </tr>
                """
            )

        parts.append("</tbody></table>")

    parts.append("</div>")
    return "".join(parts)


# =========================
# 格式化：企业微信 markdown_v2
# =========================
def build_wecom_markdown_v2(all_data: dict[str, list[dict]]) -> str:
    """生成企业微信 markdown_v2 表格"""
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")

    lines = [
        "## GitHub Trending · 每日推送",
        f"> 北京时间 {now_bj}",
        "",
    ]

    for period_key, label_cn, label_en in PERIODS:
        repos = all_data.get(period_key, [])
        lines.append(f"### {label_cn} / {label_en}")
        lines.append("")

        if not repos:
            lines.append("暂无数据")
            lines.append("")
            continue

        # markdown_v2 表格语法
        lines.append("| # | 项目 | 语言 | Star | 本期增长 |")
        lines.append("| :-- | :-- | :-- | :-- | :-- |")

        for idx, repo in enumerate(repos, start=1):
            repo_link = f"[{repo['repo']}]({repo['url']})"
            desc = repo["description"]
            if len(desc) > 60:
                desc = desc[:57] + "..."
            # 企业微信表格里不另起描述行，只放简短说明在项目名后，避免过宽
            project_cell = f"{repo_link}"
            lines.append(
                f"| {idx} | {project_cell} | {repo['language']} | "
                f"{repo['stars']} | {repo['growth'] or '-'} |"
            )

        lines.append("")

    return "\n".join(lines)


# =========================
# 推送：PushPlus
# =========================
def push_pushplus(content_html: str) -> bool:
    if not PUSHPLUS_TOKEN:
        print("[INFO] PUSHPLUS_TOKEN 为空，跳过 PushPlus")
        return True

    url = "https://www.pushplus.plus/send"
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": "GitHub Trending 日/周/月榜",
        "content": content_html,
        "template": "html",   # html 模板样式最可控
    }

    for attempt in range(3):
        try:
            resp = requests.post(url, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 200:
                print("[OK] PushPlus 发送成功")
                return True
            print(f"[WARN] PushPlus 返回异常: {data}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] PushPlus 第 {attempt + 1} 次失败: {e}", file=sys.stderr)
        time.sleep(2)

    print("[ERROR] PushPlus 发送失败", file=sys.stderr)
    return False


# =========================
# 推送：企业微信机器人
# =========================
def push_wecom(content_md_v2: str) -> bool:
    if not WECOM_WEBHOOK:
        print("[INFO] WECOM_WEBHOOK 为空，跳过企业微信")
        return True

    # 企业微信 markdown_v2 内容上限 4096 字节左右，做一次截断保护
    # 按字符截断不精确，但可以避免直接超限
    max_chars = 3800
    if len(content_md_v2) > max_chars:
        content_md_v2 = content_md_v2[:max_chars] + "\n\n> 内容过长，已截断"

    payload = {
        "msgtype": "markdown_v2",
        "markdown_v2": {
            "content": content_md_v2
        },
    }

    for attempt in range(3):
        try:
            resp = requests.post(WECOM_WEBHOOK, json=payload, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data.get("errcode") == 0:
                print("[OK] 企业微信发送成功")
                return True
            print(f"[WARN] 企业微信返回异常: {data}", file=sys.stderr)
        except Exception as e:
            print(f"[WARN] 企业微信第 {attempt + 1} 次失败: {e}", file=sys.stderr)
        time.sleep(2)

    print("[ERROR] 企业微信发送失败", file=sys.stderr)
    return False


# =========================
# 主流程
# =========================
def main() -> int:
    if not PUSHPLUS_TOKEN and not WECOM_WEBHOOK:
        print("[ERROR] 至少需要配置 PUSHPLUS_TOKEN 或 WECOM_WEBHOOK 之一", file=sys.stderr)
        return 1

    all_data = {}
    for period_key, label_cn, label_en in PERIODS:
        print(f"[INFO] 抓取 {label_cn} ({period_key}) ...")
        try:
            all_data[period_key] = fetch_trending(period_key)
            print(f"[INFO] {label_cn} 抓取到 {len(all_data[period_key])} 条")
        except Exception as e:
            print(f"[ERROR] {label_cn} 抓取失败: {e}", file=sys.stderr)
            all_data[period_key] = []
        time.sleep(1)

    if not any(all_data.values()):
        print("[ERROR] 三个榜单均未抓到数据，终止推送", file=sys.stderr)
        return 1

    pushplus_html = build_pushplus_html(all_data)
    wecom_md = build_wecom_markdown_v2(all_data)

    ok_pushplus = push_pushplus(pushplus_html)
    ok_wecom = push_wecom(wecom_md)

    # 只要一个成功就算 workflow 成功；两个都失败才失败
    if ok_pushplus or ok_wecom:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())

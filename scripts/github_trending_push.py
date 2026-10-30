#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GitHub Trending 日/周/月榜推送
- PushPlus: HTML 样式表格
- 企业微信智能机器人: WebSocket 长连接主动推送 (BotID + Secret)
"""

import asyncio
import html
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

# 企业微信 SDK
try:
    from aibot import WSClient, WSClientOptions
except ImportError:
    print("[ERROR] 缺少依赖 wecom-aibot-python-sdk，请先 pip install wecom-aibot-python-sdk", file=sys.stderr)
    sys.exit(1)

# =========================
# 环境变量配置
# =========================
PUSHPLUS_TOKEN = os.getenv("PUSHPLUS_TOKEN", "").strip()
WECOM_BOT_ID = os.getenv("WECOM_BOT_ID", "").strip()
WECOM_BOT_SECRET = os.getenv("WECOM_BOT_SECRET", "").strip()
# 单聊填 userid；如果推送到群聊，改为群 chatid 并把 CHAT_TYPE 设为 2
WECOM_TARGET_ID = os.getenv("WECOM_TARGET_ID", "").strip()
WECOM_CHAT_TYPE = int(os.getenv("WECOM_CHAT_TYPE", "1"))  # 1=单聊, 2=群聊

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

MAX_REPOS = 5  # 每个榜单取前 N 个


# =========================
# 抓取 GitHub Trending
# =========================
def fetch_trending(since: str) -> list[dict]:
    url = f"{TRENDING_URL}?since={since}"
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = soup.select("article.Box-row")
    repos = []

    for article in articles[:MAX_REPOS]:
        try:
            h2 = article.select_one("h2 a")
            if not h2:
                continue
            repo_path = h2.get("href", "").strip("/")
            if "/" not in repo_path:
                continue

            desc_el = article.select_one("p")
            description = desc_el.get_text(" ", strip=True) if desc_el else ""
            if len(description) > 140:
                description = description[:137] + "..."

            lang_el = article.select_one('[itemprop="programmingLanguage"]')
            language = lang_el.get_text(strip=True) if lang_el else "N/A"

            stars, forks = "N/A", "N/A"
            for a in article.select("a.Link--muted"):
                href = a.get("href", "")
                text = a.get_text(strip=True)
                if "/stargazers" in href:
                    stars = text
                elif "/forks" in href or "/network/members" in href:
                    forks = text

            growth_el = article.select_one("span.d-inline-block.float-sm-right")
            growth = growth_el.get_text(" ", strip=True) if growth_el else ""

            repos.append({
                "repo": repo_path,
                "url": f"https://github.com/{repo_path}",
                "description": description or "No description",
                "language": language,
                "stars": stars,
                "forks": forks,
                "growth": growth,
            })
        except Exception as e:
            print(f"[WARN] 解析条目失败: {e}", file=sys.stderr)
            continue

    return repos


def esc(text: str) -> str:
    return html.escape(text or "", quote=True)


# =========================
# PushPlus HTML 内容
# =========================
def build_pushplus_html(all_data: dict[str, list[dict]]) -> str:
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    parts = [
        f"""
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
                    max-width:780px;margin:0 auto;padding:8px;background:#f6f8fa;color:#24292f;">
          <h2 style="margin:0 0 4px 0;font-size:20px;color:#0f172a;">GitHub Trending · 每日推送</h2>
          <p style="margin:0 0 16px 0;font-size:12px;color:#57606a;">北京时间 {now_bj}</p>
        """
    ]

    for period_key, label_cn, label_en in PERIODS:
        repos = all_data.get(period_key, [])
        parts.append(
            f"""
            <div style="margin:18px 0 8px 0;">
              <span style="display:inline-block;padding:3px 12px;border-radius:999px;
                           background:#0969da;color:#ffffff;font-size:13px;font-weight:600;">
                {label_cn} / {label_en}
              </span>
            </div>
            """
        )

        if not repos:
            parts.append('<p style="font-size:13px;color:#57606a;margin:6px 0;">暂无数据</p>')
            continue

        parts.append(
            """
            <table style="width:100%;border-collapse:collapse;font-size:12px;
                          background:#ffffff;border:1px solid #d0d7de;border-radius:8px;overflow:hidden;">
              <thead>
                <tr style="background:#f0f3f6;color:#24292f;text-align:left;">
                  <th style="padding:9px 6px;border-bottom:1px solid #d0d7de;width:28px;">#</th>
                  <th style="padding:9px 6px;border-bottom:1px solid #d0d7de;">项目</th>
                  <th style="padding:9px 6px;border-bottom:1px solid #d0d7de;">语言</th>
                  <th style="padding:9px 6px;border-bottom:1px solid #d0d7de;">Star</th>
                  <th style="padding:9px 6px;border-bottom:1px solid #d0d7de;">本期增长</th>
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
                  <td style="padding:8px 6px;border-bottom:1px solid #eaeef2;color:#57606a;">{idx}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eaeef2;">
                    <a href="{esc(repo['url'])}" style="color:#0969da;text-decoration:none;font-weight:600;">
                      {esc(repo['repo'])}
                    </a>
                    <div style="color:#57606a;font-size:11px;line-height:1.35;margin-top:2px;">
                      {esc(repo['description'])}
                    </div>
                  </td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eaeef2;color:#24292f;">{esc(repo['language'])}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eaeef2;color:#24292f;">{esc(repo['stars'])}</td>
                  <td style="padding:8px 6px;border-bottom:1px solid #eaeef2;color:#1a7f37;">{esc(repo['growth'] or '-')}</td>
                </tr>
                """
            )

        parts.append("</tbody></table>")

    parts.append("</div>")
    return "".join(parts)


# =========================
# 企业微信 Markdown 内容
# =========================
def build_wecom_markdown(all_data: dict[str, list[dict]]) -> str:
    now_bj = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")
    lines = ["## GitHub Trending · 每日推送", f"> 北京时间 {now_bj}", ""]

    for period_key, label_cn, label_en in PERIODS:
        repos = all_data.get(period_key, [])
        lines.append(f"### {label_cn} / {label_en}")
        lines.append("")

        if not repos:
            lines.append("暂无数据")
            lines.append("")
            continue

        # 尝试使用 Markdown 表格语法。
        # 注意：企业微信智能机器人长连接的 markdown 消息可能不渲染表格，
        # 实际效果取决于客户端版本。如果不渲染，内容会退化为以 | 分隔的文本。
        lines.append("| # | 项目 | 语言 | Star | 本期增长 |")
        lines.append("| :-- | :-- | :-- | :-- | :-- |")
        for idx, repo in enumerate(repos, start=1):
            lines.append(
                f"| {idx} | [{repo['repo']}]({repo['url']}) | "
                f"{repo['language']} | {repo['stars']} | {repo['growth'] or '-'} |"
            )
        lines.append("")

    return "\n".join(lines)


# =========================
# PushPlus 推送
# =========================
def push_pushplus(content_html: str) -> bool:
    if not PUSHPLUS_TOKEN:
        print("[INFO] PUSHPLUS_TOKEN 未配置，跳过 PushPlus")
        return True

    url = "https://www.pushplus.plus/send"
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": "GitHub Trending 日/周/月榜",
        "content": content_html,
        "template": "html",
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
# 企业微信智能机器人推送 (WebSocket 长连接)
# =========================
async def push_wecom(markdown_content: str) -> bool:
    if not (WECOM_BOT_ID and WECOM_BOT_SECRET and WECOM_TARGET_ID):
        print("[INFO] 企业微信配置不完整 (需要 BOT_ID / BOT_SECRET / TARGET_ID)，跳过")
        return True

    options = WSClientOptions(
        bot_id=WECOM_BOT_ID,
        secret=WECOM_BOT_SECRET,
    )
    client = WSClient(options)

    authenticated = asyncio.Event()

    @client.on("authenticated")
    def on_authenticated():
        print("[OK] 企业微信智能机器人认证成功")
        authenticated.set()

    try:
        await client.connect()
        # 等待认证完成，最多 15 秒
        await asyncio.wait_for(authenticated.wait(), timeout=15)
        # 认证完成后稍等片刻，避免鉴权未就绪导致发送失败
        await asyncio.sleep(1.5)

        body = {
            "msgtype": "markdown",
            "markdown": {"content": markdown_content},
        }

        # 注意：send_message 的 chatid 对单聊而言就是 userid
        result = await client.send_message(WECOM_TARGET_ID, body)

        # SDK 返回 WsFrame，通常包含 errcode
        errcode = getattr(result, "errcode", None)
        if errcode is None and isinstance(result, dict):
            errcode = result.get("errcode")

        if errcode == 0:
            print("[OK] 企业微信智能机器人推送成功")
            return True
        else:
            print(f"[WARN] 企业微信推送返回异常: errcode={errcode}, result={result}", file=sys.stderr)
            return False

    except asyncio.TimeoutError:
        print("[ERROR] 企业微信认证超时", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] 企业微信推送异常: {e}", file=sys.stderr)
        return False
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass


# =========================
# 主流程
# =========================
async def main() -> int:
    if not PUSHPLUS_TOKEN and not (WECOM_BOT_ID and WECOM_BOT_SECRET and WECOM_TARGET_ID):
        print("[ERROR] 至少需要配置 PushPlus 或企业微信智能机器人凭证之一", file=sys.stderr)
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

    ok_pushplus = push_pushplus(build_pushplus_html(all_data))
    ok_wecom = await push_wecom(build_wecom_markdown(all_data))

    if ok_pushplus or ok_wecom:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

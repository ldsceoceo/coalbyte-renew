#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CoalByte 免费服务器自动续期（5 天一续）—— 纯 HTTP，免浏览器免过盾。

基座：eooce/Auto-Renew-HidenCloud（代理/TG/time.txt/三态 exit 码）
HTTP 客户端：curl_cffi impersonate="chrome"（同 eooce/Auto-Renew-MWS，避免 CI 上 CF 按 TLS 指纹拦裸 requests）

录制结论（agentscribe bundle 2026-11-26, session 46d8e6b4）：
  GET  /api/pelican/server?id=<serverId>&email=<email>
       -> server.renewal{expiresAt,remainingSeconds,canRenew,exempt}
       实测该 GET 自带续期副作用，expiresAt 恒等于请求时刻 + 5 天，无法据此判断是否该续。
  POST /api/pelican/renew  {"serverId","email","serverType"}
       -> {success,expiresAt,renewalDays,message}
两个接口均无 Authorization / Cookie（auth_classification: none）。
因此用 renew_state.json 记录上次续期时间做窗口门控。
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

from curl_cffi import requests

BASE_URL = os.environ.get("COAL_BASE_URL") or "https://coalbyte.com"
EMAIL = (os.environ.get("EMAIL") or "").strip()
SERVER_IDS = [s.strip() for s in (os.environ.get("SERVER_IDS") or os.environ.get("SERVER_ID") or "").split(",") if s.strip()]
RENEW_INTERVAL_HOURS = float(os.environ.get("RENEW_INTERVAL_HOURS") or "84")
STATE_FILE = os.environ.get("STATE_FILE") or "renew_state.json"
DRY_RUN = (os.environ.get("DRY_RUN") or "").lower() in ("1", "true", "yes")

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN") or ""
TG_CHAT_ID = os.environ.get("TG_CHAT_ID") or ""

IS_PROXY = (os.environ.get("IS_PROXY") or "false").lower() == "true"
PROXY_SERVER = os.environ.get("PROXY_SERVER") or "http://127.0.0.1:1081"

PLATFORM = "CoalByte"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def log(message):
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def build_proxies():
    if IS_PROXY:
        return {"http": PROXY_SERVER, "https": PROXY_SERVER}
    return None


def now_cn():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))


def mask_email(email):
    if not email:
        return "-"
    if "@" not in email:
        return email[:2] + "****"
    name, domain = email.split("@", 1)
    if len(name) > 4:
        return f"{name[:2]}****{name[-2:]}@{domain}"
    return f"{name}@{domain}"


def get_current_ip():
    try:
        resp = requests.get(
            "https://api.ip.sb/ip", timeout=15,
            impersonate="chrome", proxies=build_proxies(),
        )
        if resp.status_code == 200 and resp.text.strip():
            return resp.text.strip()
    except Exception as exc:
        log(f"获取出口 IP 失败: {exc}")
    return "获取失败"


def send_tg(status, old_due, new_due, current_ip=None):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        log("⚠️ Telegram 未配置，跳过通知")
        return False
    if current_ip is None:
        current_ip = get_current_ip()
    text = (
        f"🎉 {PLATFORM} 续期通知\n\n"
        f"{status}\n"
        f"👤 账号: {mask_email(EMAIL)}\n"
        f"📅 续期前到期：{old_due}\n"
        f"📅 续期后到期：{new_due}\n"
        f"🌐 续期使用IP: {current_ip}\n"
        f"🕒 续期时间：{now_cn()}"
    )
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "HTML"},
            timeout=10, impersonate="chrome", proxies=build_proxies(),
        )
        if resp.status_code == 200:
            log("✅ TG 通知发送成功")
            return True
        log(f"❌ TG 通知发送失败: {resp.text[:200]}")
    except Exception as exc:
        log(f"❌ TG 通知发送异常: {exc}")
    return False


def fmt_time(value):
    return str(value).replace("T", " ").replace("Z", " UTC") if value else "-"


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict) and isinstance(data.get("servers"), dict):
            return data
    except FileNotFoundError:
        pass
    except Exception as exc:
        log(f"状态文件读取失败（按未续期处理）: {exc}")
    return {"servers": {}}


def save_state(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def hours_since(iso_text):
    try:
        dt = datetime.fromisoformat(iso_text.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return None


def renew_one(sess, sid):
    url = f"{BASE_URL}/api/pelican/renew"
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = sess.post(
                url,
                json={"serverId": sid, "email": EMAIL, "serverType": "generic"},
                timeout=60, impersonate="chrome",
            )
            if resp.status_code >= 400:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return resp.json()
        except Exception as exc:
            last_err = exc
            if attempt < 3:
                log(f"续期请求失败（第 {attempt} 次）：{exc}，3s 后重试")
                time.sleep(3)
    raise last_err


def main():
    if not EMAIL or not SERVER_IDS:
        log("缺少 EMAIL 或 SERVER_IDS，无法继续")
        send_tg("❌ 续期失败：缺少 EMAIL 或 SERVER_IDS", "-", "-")
        return 1

    log(f"账号 {mask_email(EMAIL)} / 服务器 {','.join(SERVER_IDS)} / 间隔 {RENEW_INTERVAL_HOURS}h")
    state = load_state()
    servers = state["servers"]

    due, skipped = [], []
    for sid in SERVER_IDS:
        record = servers.get(sid) or {}
        elapsed = hours_since(record.get("last_renew_at")) if record.get("last_renew_at") else None
        if elapsed is not None and elapsed < RENEW_INTERVAL_HOURS:
            log(f"[{sid}] 距上次续期 {elapsed:.1f}h < {RENEW_INTERVAL_HOURS}h，本轮跳过")
            skipped.append(sid)
        else:
            log(f"[{sid}] 上次续期 {record.get('last_renew_at') or '无记录'}，进入续期")
            due.append(sid)

    if not due:
        log("未到续期窗口，静默退出（不发请求、不发 TG）")
        return 0

    if DRY_RUN:
        log(f"DRY_RUN：将对 {due} 发起续期（不发 TG）")
        return 0

    sess = requests.Session(impersonate="chrome")
    if IS_PROXY:
        sess.proxies = build_proxies()
        log(f"使用代理 {PROXY_SERVER}")

    results = []
    for sid in due:
        old_due = servers.get(sid, {}).get("expires_at")
        try:
            data = renew_one(sess, sid)
            log(f"[{sid}] 响应: {json.dumps(data, ensure_ascii=False)[:300]}")
            if not data.get("success"):
                raise RuntimeError(data.get("message") or data.get("error") or "未知错误")
            new_due = data.get("expiresAt")
            servers[sid] = {
                "last_renew_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": new_due,
                "renewal_days": data.get("renewalDays"),
            }
            results.append(("ok", sid, old_due, new_due))
            log(f"[{sid}] 续期成功，{data.get('renewalDays')} 天，到期 {new_due}")
        except Exception as exc:
            results.append(("fail", sid, old_due, str(exc)))
            log(f"[{sid}] 续期失败: {exc}")

    if any(r[0] == "ok" for r in results):
        try:
            save_state(state)
        except Exception as exc:
            log(f"状态文件写入失败（下轮可能重复续期）: {exc}")

    ok = [r for r in results if r[0] == "ok"]
    fail = [r for r in results if r[0] == "fail"]
    if not fail:
        status = "✅ 续期成功"
    elif ok:
        status = f"❌ 部分续期失败（成功 {len(ok)} / 失败 {len(fail)}）"
    else:
        status = "❌ 续期失败"

    first_ok = ok[0] if ok else None
    old_due = first_ok[2] if first_ok else (fail[0][2] if fail else "-")
    new_due = first_ok[3] if first_ok else "-"
    send_tg(status, fmt_time(old_due), fmt_time(new_due))

    return 1 if fail else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"执行异常: {exc}")
        send_tg(f"❌ 续期失败：{exc}", "-", "-")
        sys.exit(1)

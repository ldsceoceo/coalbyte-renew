# coalbyte-renew

CoalByte（https://coalbyte.com）免费服务器自动续期，5 天一续，GitHub Actions 每日巡检。纯 HTTP 调用，不需要浏览器、不需要过 reCAPTCHA。

基座：`eooce/Auto-Renew-HidenCloud`（代理 / TG / time.txt / 三态 exit 码）
HTTP 客户端：`curl_cffi` + `impersonate="chrome"`（同 `eooce/Auto-Renew-MWS`，避免 CI 上被按 TLS 指纹拦）

## 站点接口（录制 + 实调验证）

| 用途 | 请求 |
| --- | --- |
| 查询服务器 | `GET https://coalbyte.com/api/pelican/server?id=<SERVER_ID>&email=<EMAIL>` |
| 续期 | `POST https://coalbyte.com/api/pelican/renew`，body `{"serverId":"<SERVER_ID>","email":"<EMAIL>","serverType":"generic"}` |

两个接口都**不需要登录态 / Cookie / Authorization**（录制 `auth_classification: none`）。

⚠️ 实测注意：`GET /api/pelican/server` 本身带续期副作用，返回的 `expiresAt` 恒等于请求时刻 + 5 天，因此**无法用该接口判断是否该续**。脚本改用状态文件 `renew_state.json` 记录每个服务器的上次续期时间。

## 续期逻辑（三态）

1. 读 `renew_state.json` 的 `servers.<id>.last_renew_at`。
2. 距上次续期不足 `RENEW_INTERVAL_HOURS`（默认 84h ≈ 3.5 天）→ **静默退出**：不发任何网络请求（脚本本身纯 HTTP，无浏览器可启），不发 TG，退出码 0。
3. 到期则逐个 `POST /api/pelican/renew`；成功写回状态文件（workflow 自动提交）→ `✅ 续期成功`，退出码 0。
4. 任一失败 → `❌ 续期失败`，退出码 1。
5. 只有真正执行续期（成功/失败）才推 TG；未到窗口不通知。模板固定：

```
🎉 CoalByte 续期通知

{status}
👤 账号: {masked}
📅 续期前到期：{old_due}
📅 续期后到期：{new_due}
🌐 续期使用IP: {current_ip}
🕒 续期时间：{now}
```

## 配置 Secrets

`Settings → Secrets and variables → Actions`：

| 名称 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `EMAIL` | ✅ | 账号邮箱（接口按此定位用户） | `lds924494@gmail.com` |
| `SERVER_IDS` | ✅ | 服务器 identifier，页面 URL `?id=` 的值；多个用英文逗号分隔 | `d87e701c` |
| `SERVER_TYPE` | ⭕ | 服务器类型，默认 `generic` | `generic` |
| `TG_BOT_TOKEN` | ⭕ | Telegram Bot Token | |
| `TG_CHAT_ID` | ⭕ | Telegram Chat ID | |
| `NODE_LINK` | ⭕ | 代理分享链接，走 sing-box；不配则直连 | `vless://...` |

`RENEW_INTERVAL_HOURS` 可在 `Settings → Variables` 配置，默认 `84`。

## 本地演练

```bash
pip install curl_cffi
EMAIL=xxx SERVER_IDS=d87e701c DRY_RUN=true python -u app.py
```

## 免责声明

本脚本仅供学习交流，使用需遵守 CoalByte 服务条款，风险自负。
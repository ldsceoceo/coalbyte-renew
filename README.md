# coalbyte-renew

## 配置 Secrets

`Settings → Secrets and variables → Actions`：

| 名称 | 必填 | 说明 | 示例 |
| --- | --- | --- | --- |
| `EMAIL` | ✅ | 账号邮箱（接口按此定位用户） | `lds924494@gmail.com` |
| `SERVER_IDS` | ✅ | 服务器 identifier，页面 URL `?id=` 的值；多个用英文逗号分隔 | `d87e701c` |
| `TG_BOT_TOKEN` | ⭕ | Telegram Bot Token | |
| `TG_CHAT_ID` | ⭕ | Telegram Chat ID | |
| `NODE_LINK` | ⭕ | 代理分享链接，走 sing-box；不配则直连 | `vless://...` |

`RENEW_INTERVAL_HOURS` 可在 `Settings → Variables` 配置，默认 `84`（84 小时 ≈ 3.5 天，未到窗口静默跳过、不通知）。

## 免责声明

本脚本仅供学习交流，使用需遵守 CoalByte 服务条款，风险自负。

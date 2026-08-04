# WeChatOptimized — 微信桌面端 ⇄ AstrBot 桥接器

把微信桌面端接入 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 的 OneBot v11 桥接器：
消息接收来自 [WeFlow](https://weflow.top)（SSE 推送），消息发送通过 UIA 自动化操作微信界面完成。
支持文本、图片、视频/文件的完整收发闭环。

## 架构

```
微信桌面端 (WeChat 4.0+)
   │                                    ▲
   │ 消息钩子                            │ UIA 自动化
   ▼                                    │（搜索联系人/剪贴板粘贴/回车发送）
WeFlow ──SSE──▶ WeChatOptimized ──OneBot v11(WS)──▶ AstrBot ──▶ LLM / 插件
 (5031)           桥接器 (本项目)          (6199)
```

- **收**：WeFlow SSE → 消息缓冲合并（默认 5s）→ 多层去重 → OneBot v11 事件 → AstrBot
- **发**：AstrBot `send_private_msg` / `send_group_msg` → 发送器：搜索切换联系人 → 剪贴板写入 → Ctrl+V → Enter

## 特性

| 特性 | 说明 |
|---|---|
| OneBot v11 | 标准协议，AstrBot 原生支持（aiocqhttp 适配器） |
| 文件/视频发送 | `clipfile.exe` 用 .NET 写剪贴板（微信 4.0 只识别 .NET/OLE 格式） |
| 图片发送 | 同上，支持图片剪贴板 |
| 群聊 @ 识别 | `group_reply_mode: mention`，群消息需 @机器人 才响应 |
| Self-ID 稳定 | wxid → `zlib.crc32` 哈希，重启不变 |
| 鼠标漫游 | 贝塞尔曲线随机移动，模拟真人在线 |
| Web 控制面板 | http://127.0.0.1:8766 查看状态/改配置 |
| 消息缓冲合并 | 连续消息合并为一条推送，减少 AI 调用 |

## 环境要求

- Windows 10/11
- 微信桌面端 4.0+
- Python 3.10+
- [WeFlow](https://weflow.top) 已安装并登录（提供 SSE 消息源）
- [AstrBot](https://github.com/AstrBotDevs/AstrBot)（AI 引擎）
- .NET Framework 4.x（Windows 自带，用于编译 clipfile.exe）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 编译剪贴板助手（发文件/视频必需）

微信 4.0 只接受 .NET/OLE 写入的剪贴板，需要编译 `ClipFileHelper.cs`（源码已包含）：

```powershell
cd WeChatOptimized
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:winexe /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.dll /out:clipfile.exe ClipFileHelper.cs
```

### 3. 配置

复制 `config.example.json` 为 `config.json`，填写：

- `access_token`：WeFlow 设置页中的 token
- `astrbot_attachments`：微信文件接收目录（`xwechat_files\<wxid>\msg\file`）
- `bot_nicknames`：机器人昵称（群聊 @ 判定用）
- `bot_wxid`：机器人微信 wxid
- `astrbot_ob_url`：AstrBot 的 OneBot WebSocket 地址

### 4. 配置 AstrBot

添加 OneBot v11 平台（aiocqhttp 适配器），WebSocket 端口与 `astrbot_ob_url` 一致（本项目默认 `ws://127.0.0.1:6199/ws`）。

### 5. 启动

```bash
python main.py
# 或双击 启动.bat
```

启动顺序建议：微信 → WeFlow → AstrBot → 本桥接器。

## 项目结构

```
WeChatOptimized/
├── main.py              # 主入口（SSE 监听 + WS 连接 + 生命周期）
├── config.py            # 配置加载（config.json）
├── config.example.json  # 配置样例（复制为 config.json）
├── state.py             # 全局状态（Self-ID、wxid 映射）
├── bridge_core.py       # 消息组装与分发（收：WeFlow→OB11，发：OB11→发送器）
├── ob_protocol.py       # OneBot v11 协议处理（消息段解析、API 响应）
├── ob_client.py         # OB11 WebSocket 客户端
├── sender.py            # UIA 发送器（文本/图片/文件、联系人搜索切换）
├── ClipFileHelper.cs    # 剪贴板助手源码（编译为 clipfile.exe）
├── mouse_wanderer.py    # 鼠标漫游（贝塞尔曲线）
├── web_panel.py         # Web 控制面板
├── 启动.bat             # 一键启动
├── 显示窗口.bat          # 恢复被隐藏的控制台窗口（应急工具）
└── requirements.txt
```

## 已知注意事项

- **不要点击本桥接器/AstrBot 的控制台窗口内文字**：Windows 控制台"快速编辑模式"会冻结进程输出，导致事件循环卡死。
- **微信 4.0 粘贴文件是"即粘即发"**：Ctrl+V 后直接发送，没有确认框，发送器已适配此行为。
- 发送文件/视频时剪贴板会被占用，期间请勿手动复制文件。

## 许可证

MIT

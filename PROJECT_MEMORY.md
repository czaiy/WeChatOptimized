# PROJECT_MEMORY.md — 项目全局记忆

> 本文件是 AstrBot ⇄ 微信桥接器项目的"海马体"：记录已完成、待办、踩坑、关键决策。
> **新对话开启后，先读此文件即可重建上下文**，不要依赖聊天历史。
> 任何对本项目的修改完成后，都应在此文件追加摘要。

---

## 一、项目全景

### 项目定位
**AstrBot → 微信桌面端桥接器**：让 AI 助手（AstrBot）通过 OneBot v11 协议接入微信 4.0 桌面端，实现文本/图片/视频/文件的完整收发闭环。

### 链路拓扑
```
微信桌面端 (WeChat 4.0+)
   │                                    ▲
   │ 消息钩子                            │ UIA 自动化（搜索联系人/剪贴板粘贴/回车发送）
   ▼                                    │
WeFlow ──SSE──▶ WeChatOptimized ──OneBot v11(WS)──▶ AstrBot ──▶ LLM / 插件
 (5031)           桥接器 (本项目)          (6199)
```

### 涉及仓库
| 仓库 | 地址 | 说明 |
|---|---|---|
| WeChatOptimized | https://github.com/czaiy/WeChatOptimized | 桥接器主仓库（Python） |
| video-downloader-skill | https://github.com/czaiy/video-downloader-skill | AstrBot 视频下载技能 |

### 参考项目
- [KilincocomilK/WeeMessenger](https://github.com/KilincocomilK/WeeMessenger)
- [alingalingling/Akasha-WeChat](https://github.com/alingalingling/Akasha-WeChat)

---

## 二、已完成里程碑

### ✅ 阶段 1：基础链路贯通
- [x] WeFlow SSE 消息接收 + 缓冲合并（默认 5s）
- [x] OneBot v11 事件上报 AstrBot
- [x] AstrBot `send_private_msg` / `send_group_msg` 接收 + UIA 发送

### ✅ 阶段 2：顽疾根治（本会话重点）
| 问题 | 根因 | 修复 |
|---|---|---|
| 发视频时窗口被隐藏 | `powershell -WindowStyle Hidden` 触发 Windows conhost 竞态，误隐藏同会话其他控制台窗口 | 弃用 PowerShell，改纯 ctypes 写 CF_HDROP |
| ctypes 64 位句柄截漏 | ctypes 未显式声明 `restype`/`argtypes` | 显式声明后修复 |
| 微信收不到视频 | 纯 ctypes CF_HDROP 只写 1 个剪贴板格式，微信 4.0 只接受 .NET/OLE 写入的剪贴板（5 个格式：DataObject、CF_HDROP、FileNameW、FileName、Ole Private Data） | 编译 `clipfile.exe`（C# SetFileDropList/SetImage） |
| 误判"粘贴失败" | 微信 4.0 粘贴视频是"即粘即发"（无暂存、无确认框），检查输入框为空是错觉 | UIA 全树扫描发现消息列表里出现 `视频 0:10 @11:49` 才识破 |

### ✅ 阶段 3：关键组件
- [x] `clipfile.exe`（C# 4.6KB，WinExe 无控制台）—— 写剪贴板，支持文件+图片双模式，0.34s 完成（原 PowerShell 需 2-3s）
- [x] `ClipFileHelper.cs` 源码已包含，编译命令：`csc /nologo /target:winexe /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.dll /out:clipfile.exe ClipFileHelper.cs`
- [x] Self-ID 稳定：wxid → `zlib.crc32` 哈希，重启不变
- [x] 鼠标漫游（贝塞尔曲线随机移动）
- [x] Web 控制面板（http://127.0.0.1:8766）

### ✅ 阶段 4：GitHub 仓库整理
- [x] 敏感信息清理：`config.example.json` 真实 token/wxid → 占位符
- [x] `.gitignore` 排除 config.json/yaml、日志、缓存、exe
- [x] 双仓库本地提交 + SSH 推送
- [x] 修复 OpenSSH 9.5 KEX 不兼容（sntrup761x25519-sha512 无法执行）→ 锁定 curve25519

### ✅ 阶段 5：文档完善
- [x] WeChatOptimized README 重写（旧版 src/ 目录和 yaml 配置与实际不符）
- [x] README 补充参考项目归属
- [x] video-downloader-skill README + SKILL.md 补充"发送后自动清理本地文件"特性
- [x] video-downloader-skill 新增 README 和 .gitignore

---

## 三、待办 / 下一步

### 🔲 短期
- [ ] WeFlow token 重新生成（旧 token `f72001c11ed6be75029497692956baea` 曾混入 config.example.json，虽已清理但建议轮换）
- [ ] video-downloader-skill 清理规则实际验证（SKILL.md 第 6 步的 python os.remove 是否在发送后可靠执行）
- [ ] 桥接器 Web 控制面板截图补充到 README

### 🔲 中期
- [ ] 群聊 @mention 稳定性测试（不同群规模下的识别率）
- [ ] 桥接器重连机制优化（AstrBot 重启后的自动恢复）
- [ ] 多账号支持评估（单实例 → 多开）
- [ ] 单元测试 / 集成测试补充

### 🔲 长期
- [ ] 跨平台适配（macOS / Linux）
- 微信 4.0 API 变更追踪（微信桌面端大版本升级可能破坏 UIA）

---

## 四、踩过的坑（黄金教训）

### 🔴 剪贴板：纯 ctypes 写 CF_HDROP 微信不识别
- **现象**：ctypes 写入剪贴板成功，微信端无反应；.NET 写入同样路径同样文件成功
- **根因**：微信 4.0 只接受 .NET/OLE 写入的剪贴板（依赖 Ole Private Data 等 5 个格式），纯 CF_HDROP 被无视
- **解决**：编译 C# `clipfile.exe`，用 `SetFileDropList` / `SetImage`
- **教训**：**涉及微信剪贴板操作，一律走 .NET；不要相信"剪贴板写入成功=微信能收到"**

### 🔴 微信 4.0 粘贴视频是"即粘即发"
- **现象**：Ctrl+V 后检查输入框为空，误以为粘贴失败
- **根因**：微信 4.0 粘贴视频无暂存、无确认框、直接发送
- **教训**：**验证微信粘贴是否成功，要看消息列表里是否出现消息项，不要看输入框内容**

### 🔴 Windows conhost 竞态隐藏窗口
- **现象**：发文件/视频时 AstrBot 控制台窗口消失
- **根因**：`powershell -WindowStyle Hidden` 在 Windows 上有已知竞态，会误隐藏同会话其他控制台窗口
- **教训**：**不要用 `powershell -Hidden` 做后台操作；无控制台需求用 WinExe 或 ctypes**

### 🔴 OpenSSH 9.5 与 GitHub 的 KEX 不兼容
- **现象**：`ssh git@github.com` 报 Host key verification failed；keyscan 空返回
- **根因**：Windows 内建 OpenSSH 9.5 的 sntrup761x25519-sha512 算法实现不完整，GitHub 优先选此 KEX 时握手失败
- **解决**：在 `~/.ssh/config` 里给 github.com 指定 `KexAlgorithms curve25519-sha256,...`（不含 sntrup761）
- **教训**：**Windows SSH 连 GitHub 时，显式指定 KEX 算法曲线，别用默认列表**

### 🔴 控制台"快速编辑模式"冻结进程
- **现象**：点击控制台窗口文字后整个事件循环卡死
- **根因**：Windows 控制台快速编辑模式会暂停进程输出
- **教训**：**不要点击桥接器/AstrBot 控制台窗口内文字；已加应急工具 `显示窗口.bat`**

### 🔴 .NET Framework 版本
- **现象**：编译 clipfile.exe 时若用错 csc 路径会失败
- **教训**：**Windows 上 .NET 4.x 编译路径固定为 `C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe`**，不要用 .NET Core 的 dotnet

---

## 五、关键配置速查

### 文件路径
| 文件 | 用途 |
|---|---|
| `config.json` | 主配置（含真实 token，已 gitignore） |
| `config.example.json` | 配置样例（已清理敏感信息） |
| `clipfile.exe` | 剪贴板写入助手（已 gitignore） |
| `ClipFileHelper.cs` | clipfile.exe 源码 |
| `bridge.log` | 运行日志 |
| `ob_protocol.py` | OB11 协议：wxb_ 临时文件复制逻辑（tempfile 目录） |
| `config.py` | 配置加载：只加载 config.json（yaml 是遗留） |

### 端口
| 端口 | 服务 |
|---|---|
| 5031 | WeFlow SSE 源 |
| 6199 | AstrBot OneBot WebSocket |
| 8766 | 桥接器 Web 控制面板 |

### 重要常量
- 消息缓冲合并窗口：5s
- 默认视频下载：≤1080p，无水印
- Self-ID 算法：`zlib.crc32(wxid)`
- clipfile.exe 调用：`clipfile.exe <路径> [image]`

### 环境
- OS：Windows 10/11
- Python：3.12（系统 Python `C:\Program Files\Python312\pythonw.exe`）
- .NET Framework 4.x（Windows 自带）
- yt-dlp：pip 安装
- ffmpeg：`C:\ffmpeg\bin\ffmpeg.exe`

### Git 相关
- 远程：SSH (`git@github.com:czaiy/...`)
- SSH 密钥：`~/.ssh/id_ed25519`
- KEX 强制曲线：curve25519（配置在 `~/.ssh/config`）
- WeChatOptimized 最新 commit：`5a5d189`
- video-downloader-skill 最新 commit：`3ec0d22`

---

## 六、会话记录

| 日期 | 摘要 | 产出 |
|---|---|---|
| 2026-08-04 | 发视频窗口隐藏+视频发不出双顽疾根治；GitHub 双仓库整理上传；README 完善；建立项目记忆系统 | clipfile.exe 定稿、KEX 修复、PROJECT_MEMORY.md 建立 |

---

*本文件维护人：czaiy（AI 助手同步维护）*
*最后更新：2026-08-04*

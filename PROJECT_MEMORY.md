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
| 发送消息时窗口被关闭 | Escape 键会关闭整个微信窗口 | 移除 Escape 键，Enter 后直接进入聊天窗口 |
| 发送器未就绪 | `_ensure_window` 找到窗口后未设置 `_ready = True` | 找到窗口后设置 `_ready = True` |
| ValuePattern 属性错误 | uiautomation 库的 EditControl 没有 `IsValuePatternAvailable` 属性 | 改用 `GetValuePattern()` 方法 |
| 发送到错误联系人 | 复用当前聊天窗口时，用户手动切换微信聊天窗口导致发送错误 | 每次发送都强制搜索联系人 |

### ✅ 阶段 3：关键组件
- [x] `clipfile.exe`（C# 4.6KB，WinExe 无控制台）—— 写剪贴板，支持文件+图片双模式，0.34s 完成（原 PowerShell 需 2-3s）
- [x] `ClipFileHelper.cs` 源码已包含，编译命令：`csc /nologo /target:winexe /r:System.Windows.Forms.dll /r:System.Drawing.dll /r:System.dll /out:clipfile.exe ClipFileHelper.cs`
- [x] Self-ID 稳定：wxid → `zlib.crc32` 哈希，重启不变
- [x] 鼠标漫游（贝塞尔曲线随机移动）
- [x] Web 控制面板（http://127.0.0.1:8766）

### ✅ 阶段 4：文件发送功能
- [x] `sender.py` 新增 `send_file` 方法（复制文件到剪贴板 → 粘贴 → 发送）
- [x] `ob_protocol.py` 新增 `video` 和 `file` 消息类型处理
- [x] 文件路径支持：base64://、绝对路径、文件名模式
- [x] 剪贴板写入主路径为 `clipfile.exe`（C#），ctypes/PowerShell 为回退
- [x] video-downloader skill 下载后自动发送问题已修复（原 AstrBot 端问题，2026-08-04 用户确认）
- [x] video-downloader 清理规则实测通过（2026-08-04：真实下载→发送→第 6 步 os.remove→验证 0 残留）

### ✅ 阶段 5：GitHub 仓库整理
- [x] 敏感信息清理：`config.example.json` 真实 token/wxid → 占位符
- [x] `.gitignore` 排除 config.json/yaml、日志、缓存、exe
- [x] 双仓库本地提交 + SSH 推送
- [x] 修复 OpenSSH 9.5 KEX 不兼容（sntrup761x25519-sha512 无法执行）→ 锁定 curve25519

### ✅ 阶段 6：文档完善
- [x] WeChatOptimized README 重写（旧版 src/ 目录和 yaml 配置与实际不符）
- [x] README 补充参考项目归属
- [x] video-downloader-skill README + SKILL.md 补充"发送后自动清理本地文件"特性
- [x] video-downloader-skill 新增 README 和 .gitignore

---

## 三、待办 / 下一步

### 🔲 短期
- [x] ~~WeFlow token 轮换~~（2026-08-04 完成：新 token `7e7ee7...` 已写入 config.json，桥接器重启后 SSE 连接验证通过）

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

### 🔴 Escape 键关闭微信窗口
- **现象**：搜索联系人后按 Escape 关闭搜索栏，结果关闭了整个微信窗口
- **根因**：微信 4.0 中 Escape 键会关闭整个窗口，不是只关闭搜索栏
- **教训**：**不要在微信 4.0 中使用 Escape 键；Enter 后直接进入聊天窗口即可**

### 🔴 uiautomation 库 API 差异
- **现象**：`EditControl` 没有 `IsValuePatternAvailable` 属性，报错
- **根因**：uiautomation 库版本不同，API 有差异
- **教训**：**检查控件是否支持 ValuePattern 时，使用 `GetValuePattern()` 方法，不要使用 `IsValuePatternAvailable` 属性**

### 🔴 微信 4.0 窗口类名
- **现象**：按旧版 `WeChatMainWndForPC` 类名找不到微信窗口
- **根因**：微信 4.0 使用新的窗口类名 `mmui::MainWindow`
- **教训**：**查找微信窗口时，优先查找 `mmui::MainWindow`，后备查找 `WeChatMainWndForPC`**

### 🔴 UIA 遍历深度
- **现象**：找不到输入框控件
- **根因**：输入框在 UIA 树中的深度为 17，默认遍历深度不够
- **教训**：**UIA 遍历深度至少设置为 25**

### 🔴 坐标后备方案
- **现象**：微信窗口移动后，坐标后备方案失效
- **根因**：使用了绝对坐标而非相对坐标
- **教训**：**坐标后备方案必须使用窗口相对坐标（基于 `GetWindowRect`）**

### 🔴 快手图文帖（图集）解析
- **现象**：图文帖报"找不到 photo 对象/作品私密"，实际作品正常存在
- **根因**：图集帖 `mainMvUrls` 为空，图片在 `photo.ext_params.atlas.list`（相对路径），需拼 `https://{atlas.cdnList[0].cdn}{path}`；`photoType: HORIZONTAL_ATLAS` 是图集标志
- **教训**：**找 photo 对象按 `photoId`+`userName` 匹配，不能要求 mainMvUrls 非空；图集/单图/视频三种形态都要覆盖**

### 🔴 图片发成文件 / WS 1009 断连（两连击）
- **现象1**：图片到微信变成"文件"不能预览
- **根因1**：① 微信发图走 .NET `SetImage` 不认 webp；② AI 用 `file` 组件发图
- **解决1**：脚本直下 `.jpg`（快手 CDN 图集同路径换 `.jpg` 后缀直接可用，404 才回退 webp+PIL 转 jpeg）；SKILL.md 规则改为 jpg/png/gif 必须用 `{"type":"image"}` 组件
- **现象2**：改 image 组件后"没发出来"，日志 `1009 message too big ... 3435314 > 1048576`
- **根因2**：AstrBot OB11 客户端把本地图片转 base64 塞进 WS 帧，websockets 默认 max_size=1MB，桥接器侧拒收断连
- **解决2**：`ob_client.py` 的 `websockets.connect` 加 `max_size=64MB`（commit `0dffe35`，已重启桥接器）
- **教训**：**图片链路三关：格式（jpg/png/gif）→ 组件类型（image）→ 传输大小（WS 帧限制）；排查顺序先看桥接器日志**

### 🔴 图片发送 UIA 崩溃（第四关）
- **现象**：WS 帧问题解决后，日志 `[ERROR] 图片发送失败: 'EditControl' object has no attribute 'IsValuePatternAvailable'`，但 ob_protocol 仍打"图片已发送"，微信端 AI 误报成功
- **根因**：uiautomation 2.0.29 没有 `IsValuePatternAvailable` 属性（且原代码漏了括号，即使有也是恒真）；sender 捕获异常返回 False，ob_protocol 不检查返回值
- **解决**：改用 `ctrl.GetValuePattern() is not None` 探测（版本无关）；ob_protocol 检查 send_image 返回值如实记日志（commit `9549462`）
- **教训**：**sender 的返回值必须被上层检查；图片发送是全新代码路径（剪贴板 SetImage+Ctrl+V），首次启用才暴露 UIA API 不兼容；文本发送正常≠图片发送正常**

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
| `ob_protocol.py` | OB11 协议：消息类型处理（text/image/video/file）+ wxb_ 临时文件复制（tempfile 目录） |
| `config.py` | 配置加载：只加载 config.json（yaml 是遗留） |

### 微信 4.0 关键信息
- 窗口类名：`mmui::MainWindow`（旧版 `WeChatMainWndForPC`）
- UIA 遍历深度：>25（sender.py line 256）
- 发送流程：Ctrl+F 搜索联系人 → Enter 选中 → 等待 0.5s → Ctrl+V 粘贴 → Enter 发送

### 发送器关键逻辑
- 每次发送都强制搜索联系人（不复用当前聊天窗口，防止发送到错误联系人）
- 坐标后备方案使用窗口相对坐标（基于 `GetWindowRect`）
- 文件发送主路径：`clipfile.exe`（C# .NET）；ctypes 和 PowerShell 为回退
- 消息类型处理：text、image、face、video、file

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

### 运行环境
- OS：Windows 10/11
- Python：3.12（系统 Python `C:\Program Files\Python312\pythonw.exe`）
- .NET Framework 4.x（Windows 自带）
- yt-dlp：pip 安装
- ffmpeg：`C:\ffmpeg\bin\ffmpeg.exe`

### Git 相关
- 远程：SSH (`git@github.com:czaiy/...`)
- SSH 密钥：`~/.ssh/id_ed25519`
- KEX 强制曲线：curve25519（配置在 `~/.ssh/config`）
- WeChatOptimized 最新 commit：`b4d8eaf`
- video-downloader-skill 最新 commit：`2990de9`

---

## 六、会话记录

| 日期 | 摘要 | 产出 |
|---|---|---|
| 2026-08-04 | 发视频窗口隐藏+视频发不出双顽疾根治；GitHub 双仓库整理上传；README 完善；建立项目记忆系统 | clipfile.exe 定稿、KEX 修复、PROJECT_MEMORY.md 建立 |
| 2026-08-04 | 发送流程简化：移除 Escape 键、简化发送逻辑、修复 _ready 标志、添加文件发送功能 | sender.py/ob_protocol.py 更新、视频/文件消息类型支持 |
| 2026-08-04 | 用户确认 video-downloader 下载后发送问题已修复，从待办移除并记入已完成 | 待办清单更新 |
| 2026-08-04 | WeFlow token 轮换完成并重启桥接器（新 PID 5596，SSE/OB11 均连通）；清理规则实测通过（下载→发送→os.remove→0 残留）；README 截图待办按用户意愿移除 | config.json 新 token、PROJECT_MEMORY.md 更新 |
| 2026-08-04 | video-downloader skill 优化：新增快手无水印解析脚本 + 平台策略速查表 + 结尾评论风格规则，实测通过 | scripts/kuaishou.py、SKILL.md/README 更新，commit `2990de9` |
| 2026-08-04 | "还是不行"复盘：定位为旧对话上下文污染（非脚本问题），SKILL.md 加固第 0 步路由+绝对路径，需 /reset 后复测 | commit `e069221`，记忆更新 |
| 2026-08-04 | 快手图文帖（图集）支持：find_photo 按 photoId+userName 匹配 + atlas.list 多图下载，实测 JJrDdb2H 四图全下（1080×1500），视频无回归 | commit `1ecfff4`，SKILL.md 快手兜底节重写 |
| 2026-08-04 | 图片"发成文件"两连击修复：① webp 不被微信/.NET 识别→快手 CDN 同路径直下 .jpg（兜底 PIL 转 jpeg）+ SKILL.md 改 image 组件规则；② AstrBot base64 图片帧超 WS 1MB 默认限制→桥接器 max_size=64MB 并重启 | skill `7ef3963`、桥接器 `0dffe35`（新 PID 7732） |
| 2026-08-04 | 图片发送第四关：uiautomation 2.0.29 无 IsValuePatternAvailable 导致发送崩溃且被误报成功→改 GetValuePattern() 探测 + ob_protocol 如实记录失败 | commit `9549462`，桥接器重启 |
| 2026-08-04 | 图片积压输入栏（第五关）：控件定向 SendKeys 在暂存态丢 Enter + 暂存等待不足 + 发送按钮误匹配无名按钮→改全局按键(与 send_text 一致)+等待1.2s+按钮只认具名并记日志 | 桥接器重启（23:43），待用户复测 |

---

## video-downloader-skill

### 2026-08-04 快手支持 + 结尾风格优化（commit `2990de9`）
- 🆕 `scripts/kuaishou.py`（纯标准库，仿 douyin_note.py 接口）：快手短链 → 移动 UA → `v.m.chenzhongtech.com` 分享页 → 解析 `window.INIT_STATE` JSON → `photo.mainMvUrls[0].url` 无水印 mp4 直链（kwimgs/yximgs CDN）+ caption + userName；图文帖回退取 coverUrls
- 🔑 关键事实：INIT_STATE 的路由 key 是凯撒混淆的（tusjoh=string），但 value 完整可用，直接 raw_decode 递归找 mainMvUrls 即可
- ⚙️ yt-dlp 2026.07.04 平台现状：**无快手提取器**；小红书 XiaoHongShu 提取器可用但源画质已被官方限制；微博 WeiboVideo 可用
- ⚠️ 快手源画质封顶约 720p，平台限制，不用折腾
- 📝 SKILL.md 变更：新增「平台策略速查」表 + 快手兜底章节；第 5 步结尾规则——禁止机械后缀"无水印版"，必须加一句基于标题的作品评论（不编造细节）
- ✅ 实测：用户快手链接 K652nUq8（森川梨「我保证我是天使」）解析→下载 2.5MB→发送→清理 0 残留，全链路 4 秒

### 2026-08-04 晚 "还是不行" 复盘（commit `e069221`）
- 🔍 根因链：微信群旧对话上下文污染——AI 带着之前失败的旧记忆，违反 skill grounding 规则没重读 SKILL.md，绕过脚本自己 curl 短链，桌面 UA 被快手分流到 PC 页（www.kuaishou.com/short-video），白白耗尽 6 次工具调用放弃
- 🔑 脚本本身无问题：K652nUq8 和 ntczNFQ8 两条链接实测 100% 成功（2-4 秒）
- 🤖 趣闻：微信端 AI 自救时自己编辑了 SKILL.md 加「第 0 步平台路由」并 git 提交（85c606b），本次已保留其改动并加固
- 🛠 加固：快手兜底节补充本机绝对路径命令 + 明确"不要自己 curl 探测快手短链"
- ⚠️ 教训：**skill 修改后必须让用户 /reset 对话再测**——旧会话历史会让 AI 凭记忆行事，无视文件更新；快手短链按 UA 分流（移动 UA→chenzhongtech 可解析，桌面 UA→PC 页不可解析）

### 2026-08-04 深夜 快手图文帖（图集）支持（commit `1ecfff4`）
- 🐛 用户实测图文帖失败，微信端 AI 误报"作品私密/已删除"——实为脚本 `find_photo` 要求 `mainMvUrls` 非空，图集帖该字段为空被跳过
- 🔍 解剖 `JJrDdb2H` 的 INIT_STATE：`photoType: HORIZONTAL_ATLAS`，图片在 `ext_params.atlas.list`（如 `/ufile/atlas/xxx_0.webp`），配 `atlas.cdnList`/`atlas.cdn` 域名拼完整 URL；`size` 数组给出每张尺寸（1080×1500）；图集还可能带 `atlas.music`（背景音乐 m4a，暂不下载）
- 🛠 修复：find_photo 改按 `photoId`+`userName` 匹配；新增图集分支——逐张下载输出 `IMG_n:<path>`；视频帖逻辑不变（回归通过）
- 📝 SKILL.md 快手兜底节重写（微信端 AI 曾把该节改回旧版，本次覆盖为最终版）
- ✅ 实测：JJrDdb2H 四张 webp 原图全下（421-488KB/张），K652nUq8 视频回归正常，测试残留 0

---

*本文件维护人：czaiy（AI 助手同步维护）*
*最后更新：2026-08-04（快手支持上线 + "还是不行"复盘：上下文污染教训）*

"""
微信消息发送器
参考 Akasha-WeChat uia_sender.py + WeeMessenger mouse_wanderer.py

原理：
  微信 4.0 基于 Electron (Chromium)。通过 UIA ValuePattern 设置输入框文本，
  InvokePattern 点击发送按钮。全程无 DLL 注入，风控风险较低。

特性：
  - ValuePattern 直接设值（非键盘模拟）
  - 鼠标漫游防检测（发送时暂停）
  - 快速通道（同目标跳过搜索）
  - 坐标后备方案（兼容 Qt 界面）
"""

import ctypes
import logging
import os
import random
import subprocess
import threading
import time

log = logging.getLogger("sender")


class UiaSender:
    """
    基于 Windows UI Automation 的微信 4.0+ 发送器
    """

    WECHAT_TITLES = ["微信", "WeChat"]
    EXCLUDE_CLASSES = ["Chrome_WidgetWin_1", "CabinetWClass"]

    def __init__(self, search_enabled: bool = True, wanderer_enabled: bool = True,
                 wanderer_min_interval: float = 10.0, wanderer_max_interval: float = 30.0,
                 wanderer_times_min: int = 1, wanderer_times_max: int = 3):
        self._lock = threading.Lock()
        self._auto = None
        self._ready = False

        # 微信窗口
        self._window = None
        self._is_electron = False

        # 控件缓存
        self._input_control = None
        self._send_button = None
        self._last_contact = ""
        self._use_coord_fallback = False

        self.search_enabled = search_enabled

        # 鼠标漫游
        self._wanderer = None
        if wanderer_enabled:
            from mouse_wanderer import MouseWanderer
            self._wanderer = MouseWanderer(
                min_interval=wanderer_min_interval,
                max_interval=wanderer_max_interval,
                wander_times_range=(wanderer_times_min, wanderer_times_max),
            )
            self._wanderer.start()
            log.info("[发送器] 鼠标漫游已启用")

        # 统计
        self._send_count = 0

        self._init()

    def _init(self):
        """初始化 UIA 并定位窗口"""
        try:
            import uiautomation as auto
            self._auto = auto
        except ImportError:
            log.error("[发送器] 请先安装 uiautomation: pip install uiautomation")
            return

        # COM 初始化（uiautomation 需要）
        try:
            import ctypes
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass  # 已经初始化过会报错，忽略

        log.info("[发送器] 正在搜索微信窗口...")
        self._find_window()
        if self._window:
            log.info(f"[发送器] 微信窗口: '{self._window.Name}' ClassName={self._window.ClassName}")
            self._ready = True
        else:
            log.warning("[发送器] 未找到微信窗口，请确保微信已打开")

    def _find_window(self):
        """按标题搜索微信窗口"""
        auto = self._auto
        root = auto.GetRootControl()
        
        # 优先查找微信窗口类名
        for w in root.GetChildren():
            cls = w.ClassName
            if cls in ("mmui::MainWindow", "WeChatMainWndForPC"):
                self._window = w
                self._is_electron = (cls == "mmui::MainWindow")
                return
        
        # 后备：按标题搜索（排除控制台窗口）
        for w in root.GetChildren():
            cls = w.ClassName
            if cls in self.EXCLUDE_CLASSES or cls == "ConsoleWindowClass":
                continue
            for kw in self.WECHAT_TITLES:
                if kw in w.Name:
                    self._window = w
                    if cls != "WeChatMainWndForPC":
                        self._is_electron = True
                    return

    def _ensure_window(self) -> bool:
        """确保窗口可用"""
        if not self._ready:
            self._find_window()
            if self._window:
                self._ready = True
                log.info(f"[发送器] 微信窗口已找到: '{self._window.Name}'")
            return self._window is not None
        if self._window and self._window.Exists(0.2):
            return True
        self._find_window()
        if self._window:
            self._ready = True
        return self._window is not None

    def _activate(self):
        """激活微信窗口到前台"""
        try:
            self._window.SetActive()
            time.sleep(0.3)
        except Exception:
            try:
                self._window.SwitchToThisWindow()
                time.sleep(0.3)
            except Exception:
                pass
        # AttachThreadInput 绕过 Windows 前台限制
        try:
            import ctypes
            from ctypes import wintypes
            # 微信 4.0+ 使用 mmui::MainWindow，旧版使用 WeChatMainWndForPC
            hwnd = ctypes.windll.user32.FindWindowW('mmui::MainWindow', None)
            if not hwnd:
                hwnd = ctypes.windll.user32.FindWindowW('WeChatMainWndForPC', None)
            if not hwnd:
                hwnd = ctypes.windll.user32.FindWindowW('Qt51514QWindowIcon', None)
            if hwnd:
                WE_CHAT_TID = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
                CURRENT_TID = ctypes.windll.kernel32.GetCurrentThreadId()
                ctypes.windll.user32.AttachThreadInput(CURRENT_TID, WE_CHAT_TID, True)
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.BringWindowToTop(hwnd)
                ctypes.windll.user32.AttachThreadInput(CURRENT_TID, WE_CHAT_TID, False)
        except Exception:
            pass

    def _switch_contact(self, contact: str) -> bool:
        """切换到指定联系人/群聊的聊天窗口。Ctrl+F 搜索 → 粘贴 → Enter"""
        if not self._ensure_window():
            return False
        self._activate()

        try:
            import pyperclip
            import ctypes
            from ctypes import wintypes

            # 微信 4.0+ 使用 mmui::MainWindow，旧版使用 WeChatMainWndForPC
            hwnd = ctypes.windll.user32.FindWindowW('mmui::MainWindow', None)
            if not hwnd:
                hwnd = ctypes.windll.user32.FindWindowW('WeChatMainWndForPC', None)
            if not hwnd:
                hwnd = ctypes.windll.user32.FindWindowW('Qt51514QWindowIcon', None)
            if not hwnd:
                log.warning("[发送器] 找不到微信主窗口句柄")
                return False

            WE_CHAT_TID = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
            CURRENT_TID = ctypes.windll.kernel32.GetCurrentThreadId()
            ctypes.windll.user32.AttachThreadInput(CURRENT_TID, WE_CHAT_TID, True)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.BringWindowToTop(hwnd)
            time.sleep(0.3)

            try:
                # Ctrl+F 打开搜索
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)   # Ctrl
                ctypes.windll.user32.keybd_event(0x46, 0, 0, 0)   # F
                ctypes.windll.user32.keybd_event(0x46, 0, 2, 0)
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
                time.sleep(0.5)

                # Ctrl+A 清空
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x41, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x41, 0, 2, 0)
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
                time.sleep(0.15)

                # 粘贴联系人
                pyperclip.copy(contact)
                time.sleep(0.1)
                ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)   # V
                ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
                ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)
                time.sleep(0.3)

                # Enter 选中第一个结果（直接进入聊天窗口）
                ctypes.windll.user32.keybd_event(0x0D, 0, 0, 0)
                ctypes.windll.user32.keybd_event(0x0D, 0, 2, 0)
                time.sleep(0.5)  # 等待聊天窗口加载

                log.info(f"[发送器] 已切到联系人: {contact}")
                return True
            finally:
                ctypes.windll.user32.AttachThreadInput(CURRENT_TID, WE_CHAT_TID, False)

        except Exception as e:
            log.error(f"[发送器] 切换联系人失败: {e}")
            return False

    def _locate_input(self) -> bool:
        """定位聊天输入框和发送按钮"""
        if not self._ensure_window():
            log.warning("[发送器] _ensure_window 返回 False")
            return False

        if self._input_control is not None:
            try:
                self._input_control.GetCurrentPattern()
                log.info("[发送器] 使用缓存的输入控件")
                return True
            except Exception:
                log.info("[发送器] 缓存的输入控件失效，重新定位")
                self._input_control = None
                self._send_button = None

        auto = self._auto
        win_rect = self._window.BoundingRectangle
        win_center_y = win_rect.top + win_rect.height() / 2
        log.info(f"[发送器] 窗口: [{win_rect.left},{win_rect.top} {win_rect.width()}x{win_rect.height()}] center_y={win_center_y}")

        edits = []

        def walk(ctrl, depth=0):
            if depth > 25:  # 增加遍历深度
                return
            try:
                for child in ctrl.GetChildren():
                    try:
                        if child.ControlTypeName == "EditControl":
                            edits.append(child)
                        walk(child, depth + 1)
                    except Exception:
                        pass
            except Exception:
                pass

        try:
            walk(self._window)
        except Exception as e:
            log.error(f"[发送器] 遍历异常: {e}")

        log.info(f"[发送器] 找到 {len(edits)} 个 EditControl")

        if not edits:
            log.warning("[发送器] 未找到输入控件，使用坐标后备方案")
            self._use_coord_fallback = True
            return True

        # 过滤：聊天输入框在窗口下半部分，宽度大于 100
        candidates = [e for e in edits
                      if e.BoundingRectangle and
                      e.BoundingRectangle.top >= win_center_y - 20 and
                      e.BoundingRectangle.width() > 100]

        log.info(f"[发送器] 候选输入框: {len(candidates)} 个")
        for i, c in enumerate(candidates):
            rect = c.BoundingRectangle
            log.info(f"  [{i}] '{c.Name[:30]}' [{rect.left},{rect.top} {rect.width()}x{rect.height()}]")

        if not candidates:
            candidates = [e for e in edits if e.BoundingRectangle]

        # 按面积倒序
        candidates.sort(key=lambda e: e.BoundingRectangle.width() *
                        e.BoundingRectangle.height(), reverse=True)

        for ctrl in candidates:
            rect = ctrl.BoundingRectangle
            area = rect.width() * rect.height()
            if area < 200:
                continue
            if ctrl.IsValuePatternAvailable:
                self._input_control = ctrl
                log.info(f"[发送器] 输入框已定位 ({rect.width()}x{rect.height()} ValuePattern)")
                break

        if not self._input_control and candidates:
            self._input_control = candidates[0]
            log.warning("[发送器] 输入框无 ValuePattern，使用 SendKeys 后备")

        # 查找发送按钮
        try:
            buttons = []
            def find_buttons(ctrl, depth=0):
                if depth > 8:
                    return
                try:
                    for child in ctrl.GetChildren():
                        if child.ControlTypeName == "ButtonControl":
                            bn = child.Name or ""
                            if "发送" in bn or "Send" in bn or bn.strip() == "":
                                buttons.append(child)
                        find_buttons(child, depth + 1)
                except Exception:
                    pass
            find_buttons(self._window)
            if buttons:
                self._send_button = buttons[0]
        except Exception:
            pass

        return True

    def send_text(self, contact: str, text: str) -> bool:
        """
        发送文本消息（简化流程：切换联系人后直接粘贴发送）
        """
        with self._lock:
            if not self._ready:
                log.error("[发送器] 未就绪")
                return False

            if not self._ensure_window():
                return False

            # 安全检查：过滤 PIL 引用
            if "<PIL." in text or "PIL." in text:
                log.warning(f"[发送器] 跳过 PIL 引用消息: {text[:60]}")
                return False

            # 暂停鼠标漫游
            if self._wanderer:
                self._wanderer.pause()

            try:
                self._activate()

                # 切换联系人（每次发送都强制搜索，避免微信切换聊天窗口后发送到错误联系人）
                if self.search_enabled and contact:
                    log.info(f"[发送器] 搜索联系人: {contact}")
                    if not self._switch_contact(contact):
                        log.warning(f"[发送器] 无法切换到 '{contact}'，尝试在当前窗口发送")
                    self._last_contact = contact

                # 直接粘贴内容并发送（Enter 后输入框已自动获得焦点）
                import pyperclip
                pyperclip.copy(text)
                time.sleep(0.05)
                self._auto.SendKeys('{Ctrl}v')
                time.sleep(0.2)
                self._auto.SendKeys('{Enter}')

                self._send_count += 1
                log.info(f"[发送器] {contact}: {text[:50]}...")
                return True

            except Exception as e:
                log.error(f"[发送器] 发送失败: {e}")
                return False
            finally:
                # 恢复鼠标漫游
                if self._wanderer:
                    self._wanderer.resume()

    def send_image(self, contact: str, image_path: str) -> bool:
        """通过剪贴板发送图片"""
        with self._lock:
            if not self._ready:
                return False
            if not os.path.isfile(image_path):
                log.error(f"[发送器] 图片不存在: {image_path}")
                return False

            if self._wanderer:
                self._wanderer.pause()

            try:
                if not self._ensure_window():
                    return False
                self._activate()

                if self.search_enabled and contact:
                    if contact != self._last_contact:
                        self._switch_contact(contact)
                        self._last_contact = contact

                self._copy_image_to_clipboard(image_path)
                time.sleep(0.2)

                if not self._locate_input():
                    return False

                if self._use_coord_fallback:
                    import ctypes
                    from ctypes import wintypes
                    hwnd = ctypes.windll.user32.FindWindowW('Qt51514QWindowIcon', None)
                    if not hwnd:
                        hwnd = ctypes.windll.user32.FindWindowW('WeChatMainWndForPC', None)
                    if hwnd:
                        rect = wintypes.RECT()
                        ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
                        input_x = rect.left + int((rect.right - rect.left) * 0.3)
                        input_y = rect.top + int((rect.bottom - rect.top) * 0.92)
                        ctypes.windll.user32.SetCursorPos(input_x, input_y)
                        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)
                        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)
                    time.sleep(0.3)
                    self._auto.SendKeys('{Ctrl}v')
                    time.sleep(0.5)
                    self._auto.SendKeys('{Enter}')
                    self._send_count += 1
                    log.info(f"[发送器] 图片 → {contact}: {os.path.basename(image_path)}")
                    return True

                self._input_control.SendKeys('{Ctrl}v')
                time.sleep(0.5)

                if self._send_button:
                    self._send_button.Click()
                else:
                    self._input_control.SendKeys('{Enter}')

                self._send_count += 1
                log.info(f"[发送器] 图片 → {contact}: {os.path.basename(image_path)}")
                return True

            except Exception as e:
                log.error(f"[发送器] 图片发送失败: {e}")
                return False
            finally:
                if self._wanderer:
                    self._wanderer.resume()

    def _copy_image_to_clipboard(self, path: str):
        """复制图片到剪贴板（优先 clipfile.exe，回退 PowerShell）"""
        abs_path = os.path.abspath(path)
        helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clipfile.exe")
        if os.path.isfile(helper):
            try:
                r = subprocess.run([helper, abs_path, "image"], capture_output=True, timeout=20)
                if r.returncode == 0:
                    return
                log.warning(f"[发送器] clipfile.exe(image) 返回 {r.returncode}，回退 PowerShell")
            except Exception as e:
                log.warning(f"[发送器] clipfile.exe(image) 异常: {e}，回退 PowerShell")
        subprocess.run([
            "powershell", "-WindowStyle", "Hidden", "-Command",
            f"Add-Type -AssemblyName System.Windows.Forms;"
            f"$img = [System.Drawing.Image]::FromFile('{abs_path}');"
            f"[System.Windows.Forms.Clipboard]::SetImage($img);"
            f"$img.Dispose()"
        ], check=True, timeout=10)

    def _copy_file_to_clipboard(self, path: str):
        """复制文件到剪贴板（微信可识别的 .NET/OLE 格式）。

        主路径：clipfile.exe（.NET SetFileDropList，WinExe 无窗口）。
        微信 4.0 只认 .NET/OLE 写入的文件剪贴板（需要 Ole Private Data 等格式），
        纯 ctypes CF_HDROP 会被无视；旧的 powershell -WindowStyle Hidden 方案
        会因 conhost 竞态隐藏控制台窗口，已弃用。
        """
        abs_path = os.path.abspath(path)
        helper = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clipfile.exe")
        if os.path.isfile(helper):
            try:
                r = subprocess.run([helper, abs_path], capture_output=True, timeout=20)
                if r.returncode == 0:
                    return
                log.warning(f"[发送器] clipfile.exe 返回 {r.returncode}，回退 ctypes")
            except Exception as e:
                log.warning(f"[发送器] clipfile.exe 异常: {e}，回退 ctypes")
        self._copy_file_to_clipboard_ctypes(abs_path)

    def _copy_file_to_clipboard_ctypes(self, abs_path: str):
        """纯 ctypes 写入 CF_HDROP（备用方案，微信 4.0 可能不识别但聊胜于无）"""
        import struct

        # DROPFILES: pFiles=20, pt=(0,0), fWide=1（文件列表从偏移 20 开始）
        header = struct.pack("<IiiI", 20, 0, 0, 1) + b"\x00" * 4
        # UTF-16LE 路径，双 null 结尾
        payload = (abs_path + "\x00").encode("utf-16-le") + b"\x00\x00"
        data = header + payload

        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        # 64 位系统必须显式声明句柄类型，否则句柄被截断为 32 位
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        GMEM_MOVEABLE = 0x0002
        CF_HDROP = 15

        # 剪贴板可能被其他进程占用，重试若干次
        last_err = None
        for attempt in range(20):
            if user32.OpenClipboard(None):
                try:
                    user32.EmptyClipboard()
                    h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                    if not h:
                        raise OSError("GlobalAlloc failed")
                    p = kernel32.GlobalLock(h)
                    try:
                        ctypes.memmove(p, data, len(data))
                    finally:
                        kernel32.GlobalUnlock(h)
                    if not user32.SetClipboardData(CF_HDROP, h):
                        kernel32.GlobalFree(h)
                        raise ctypes.WinError()
                    return  # 成功：hGlobal 所有权已移交给剪贴板
                finally:
                    user32.CloseClipboard()
            last_err = ctypes.WinError()
            time.sleep(0.1)
        raise OSError(f"无法打开剪贴板: {last_err}")

    def send_file(self, contact: str, file_path: str) -> bool:
        """通过剪贴板发送文件（视频、文档等）"""
        with self._lock:
            if not self._ready:
                return False
            if not os.path.isfile(file_path):
                log.error(f"[发送器] 文件不存在: {file_path}")
                return False

            if self._wanderer:
                self._wanderer.pause()

            try:
                if not self._ensure_window():
                    return False
                self._activate()

                # 切换联系人（每次发送都强制搜索）
                if self.search_enabled and contact:
                    log.info(f"[发送器] 搜索联系人: {contact}")
                    if not self._switch_contact(contact):
                        log.warning(f"[发送器] 无法切换到 '{contact}'，尝试在当前窗口发送")
                    self._last_contact = contact

                # 复制文件到剪贴板
                self._copy_file_to_clipboard(file_path)
                time.sleep(0.2)

                # 直接粘贴并发送
                self._auto.SendKeys('{Ctrl}v')
                time.sleep(0.5)
                self._auto.SendKeys('{Enter}')

                self._send_count += 1
                log.info(f"[发送器] 文件 → {contact}: {os.path.basename(file_path)}")
                return True

            except Exception as e:
                log.error(f"[发送器] 文件发送失败: {e}")
                return False
            finally:
                if self._wanderer:
                    self._wanderer.resume()

    def get_stats(self) -> dict:
        """获取发送统计"""
        return {
            "total_sent": self._send_count,
            "last_target": self._last_contact,
        }

    def shutdown(self):
        """安全关闭"""
        log.info("[发送器] 正在关闭...")
        if self._wanderer:
            self._wanderer.stop()
        log.info(f"[发送器] 已关闭 (共发送 {self._send_count} 条)")


def create_sender(search_enabled: bool = True, wanderer_enabled: bool = True,
                  wanderer_min_interval: float = 10.0, wanderer_max_interval: float = 30.0,
                  wanderer_times_min: int = 1, wanderer_times_max: int = 3) -> UiaSender:
    """创建发送器实例"""
    return UiaSender(
        search_enabled=search_enabled,
        wanderer_enabled=wanderer_enabled,
        wanderer_min_interval=wanderer_min_interval,
        wanderer_max_interval=wanderer_max_interval,
        wanderer_times_min=wanderer_times_min,
        wanderer_times_max=wanderer_times_max,
    )

# 显示窗口.py - 找回被隐藏的 AstrBot / WeChatOptimized 控制台窗口
import ctypes
from ctypes import wintypes

user32 = ctypes.windll.user32
found = 0


@ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
def cb(hwnd, lparam):
    global found
    n = user32.GetWindowTextLengthW(hwnd)
    if n > 0:
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        t = buf.value
        if ("WeChatOptimized" in t) or ("Astrbot" in t and "cmd.exe" in t):
            user32.ShowWindow(hwnd, 9)   # SW_RESTORE
            user32.ShowWindow(hwnd, 5)   # SW_SHOW
            user32.BringWindowToTop(hwnd)
            print("已恢复:", t.strip())
            found += 1
    return True


user32.EnumWindows(cb, 0)
print("完成！" if found else "没有找到对应窗口（后台进程可能已退出）")

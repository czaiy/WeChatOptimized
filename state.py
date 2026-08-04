"""
全局共享状态模块
参考 Akasha-WeChat state.py，使用模块级变量而非类单例。
所有模块通过 import state 访问这些变量。
"""

import threading
import zlib
from typing import Optional

# ============ 状态控制 ============

running = False
paused = threading.Event()
paused.clear()
run_lock = threading.Lock()
bridge_thread = None

# ============ OneBot WebSocket 客户端管理 ============

_ob_ws = None          # WebSocket 连接实例
_ob_ws_loop = None     # 事件循环
_ob_ws_ready = threading.Event()
_self_id_int = 0       # 启动时从 config 初始化


def _wxid_to_int(wxid: str) -> int:
    """将微信 wxid 映射为稳定的整数 ID。

    使用 crc32 而非 hash()：hash() 受 Python 哈希随机化影响，
    每次进程重启结果都会变，会导致 AstrBot 端会话/联系人 ID 漂移。
    """
    return zlib.crc32(str(wxid).encode("utf-8")) % (2**31)


# ============ 桥接实例 / 发送器 ============

bridge_instance = None
bridge_lock = threading.Lock()
sender_instance = None
_ob_id_to_contact: dict[int, str] = {}  # OneBot user_id/group_id → 微信联系名
ob_client_started = False

# 群聊回复模式（运行时可变，启动时从 config 初始化）
group_reply_mode = "mention"

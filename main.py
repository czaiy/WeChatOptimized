"""
入口与生命周期管理模块
参考 Akasha-WeChat main.py

负责桥接的启动、停止、主循环重连逻辑，以及命令行入口。
"""

import json
import logging
import os
import sys
import threading
import time

import requests

import state
import config
from sender import create_sender
from ob_client import _run_ob_client
from bridge_core import WeFlowBridge
from web_panel import WebHandler, PAGE
from http.server import HTTPServer

log = logging.getLogger("main")


# ============ 启动 / 停止 ============


def _start_bridge():
    """启动桥接组件"""
    with state.run_lock:
        if state.running:
            log.warning("[启动] 已在运行中")
            return
        state.running = True

    state.paused.clear()
    state.sender_instance = create_sender(
        search_enabled=config.SENDER_SEARCH_ENABLED,
        wanderer_enabled=config.WANDERER_ENABLED,
        wanderer_min_interval=config.WANDERER_MIN_INTERVAL,
        wanderer_max_interval=config.WANDERER_MAX_INTERVAL,
        wanderer_times_min=config.WANDERER_TIMES_MIN,
        wanderer_times_max=config.WANDERER_TIMES_MAX,
    )

    if not state.ob_client_started:
        t = threading.Thread(target=_run_ob_client, daemon=True, name="ob11-client")
        t.start()
        state.ob_client_started = True

    state.bridge_thread = threading.Thread(target=_bridge_loop, daemon=True, name="bridge")
    state.bridge_thread.start()
    log.info("[启动] 桥接已启动")


def _stop_bridge():
    """停止桥接组件"""
    with state.run_lock:
        state.running = False

    # 切断 SSE 长连接，让 _bridge_loop 的 listen_sse() 从阻塞中退出
    with state.bridge_lock:
        if state.bridge_instance and state.bridge_instance._sse_session:
            try:
                state.bridge_instance._sse_session.close()
                log.info("[停止] SSE 连接已断开")
            except Exception as e:
                log.warning(f"[停止] 断开 SSE 异常: {e}")

    # 关闭 WebSocket 连接，让 _ob_client_main 从 async for 中退出
    _ws = state._ob_ws
    _loop = state._ob_ws_loop
    if _ws:
        try:
            if _loop and _loop.is_running():
                import asyncio
                asyncio.run_coroutine_threadsafe(_ws.close(), _loop)
                log.info("[停止] WebSocket 连接已关闭")
        except Exception as e:
            log.warning(f"[停止] 关闭 WebSocket 异常: {e}")

    state._ob_ws_ready.clear()

    # 重置启动标记，让下次 start 能重新拉起 WebSocket 客户端线程
    state.ob_client_started = False
    state._ob_ws_loop = None

    log.info("[停止] 桥接已停止")


def _bridge_loop():
    """
    桥接主循环：连接 WeFlow SSE，断线自动重连
    参考 Akasha-WeChat main.py 的 _bridge_loop
    """
    import ctypes
    ctypes.windll.ole32.CoInitialize(None)

    if not config.ACCESS_TOKEN:
        log.error("❌ 未配置 access_token")
        state.running = False
        return

    log.info(f"Bridge | WeFlow: {config.WE_FLOW_BASE_URL} | OB11: {config.ASTRBOT_OB_URL} | 发送: {config.SEND_METHOD}")

    bridge = WeFlowBridge(state.sender_instance)
    with state.bridge_lock:
        state.bridge_instance = bridge

    try:
        # WeFlow 连接检查（使用正确的 SSE 端点）
        sse_url = f"{config.WE_FLOW_BASE_URL}/api/v1/push/messages?access_token={config.ACCESS_TOKEN}"
        try:
            r = requests.get(sse_url, headers={"Accept": "text/event-stream"}, stream=True, timeout=8)
            if r.status_code == 200:
                log.info("✅ WeFlow 连接正常")
                r.close()
            elif r.status_code == 401:
                log.error("❌ Access Token 无效")
                state.running = False
                return
            else:
                log.warning(f"WeFlow 返回 HTTP {r.status_code}，尝试继续...")
                r.close()
        except requests.exceptions.ConnectionError:
            log.error(f"❌ 无法连接 WeFlow @ {config.WE_FLOW_BASE_URL}")
            state.running = False
            return

        # 主循环：断线重连
        while state.running:
            try:
                bridge.listen_sse()
            except Exception as e:
                log.error(f"SSE: {e}")

            if not state.running:
                break

            log.warning("⚠️ SSE 断开，10s 后重连")
            for _ in range(10):
                if not state.running:
                    break
                time.sleep(1)

    finally:
        with state.bridge_lock:
            state.bridge_instance = None


def start_web():
    """启动 Web 面板"""
    server = HTTPServer(("127.0.0.1", config.WEB_PORT), WebHandler)
    log.info(f"Web: http://127.0.0.1:{config.WEB_PORT}")
    server.serve_forever()


# ============ 入口 ============

def main():
    # 从 config 初始化 state 中需要计算的值
    state._self_id_int = state._wxid_to_int(config.BOT_WXID or "wechat_bot")
    state.group_reply_mode = config.GROUP_REPLY_MODE

    PID_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bridge.pid")

    def pid_exists(pid):
        try:
            import ctypes
            from ctypes import wintypes
            h = ctypes.windll.kernel32.OpenProcess(0x0400, False, pid)
            if h:
                ctypes.windll.kernel32.CloseHandle(h)
                return True
            return False
        except Exception:
            return True

    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r") as f:
                old_pid = int(f.read().strip())
            if pid_exists(old_pid):
                log.error("⚠️ bridge.pid 已存在")
                sys.exit(1)
            else:
                os.remove(PID_FILE)
        except (ValueError, OSError):
            os.remove(PID_FILE)

    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))

    try:
        log.info("=" * 50)
        log.info(" WeChatOptimized - 微信智能桥接")
        log.info("=" * 50)
        log.info(f"WeFlow: {config.WE_FLOW_BASE_URL}")
        log.info(f"AstrBot: {config.ASTRBOT_OB_URL}")
        log.info(f"Web: http://127.0.0.1:{config.WEB_PORT}")
        log.info(f"Token: {'已配置 (' + config.ACCESS_TOKEN[:8] + '...)' if config.ACCESS_TOKEN else '❌ 未配置'}")
        log.info("")
        log.info("  1. 打开 Web 面板填写配置（如已配置请跳过）")
        log.info("  2. 点击「启动」开始桥接")
        log.info("  3. 或直接在命令行按回车立即启动")
        log.info("")

        # 如果 Token 已配置，自动启动桥接
        if config.ACCESS_TOKEN:
            _start_bridge()

        # 启动 Web 面板（阻塞）
        start_web()
    finally:
        _stop_bridge()
        try:
            os.remove(PID_FILE)
        except Exception:
            pass


if __name__ == "__main__":
    main()

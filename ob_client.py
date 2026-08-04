"""
OneBot WebSocket 客户端模块
参考 Akasha-WeChat ob_client.py

维护到 AstrBot aiocqhttp 服务端的 WebSocket 长连接，
推送事件并从 AstrBot 接收 API 请求。

关键修复：
- 添加 X-Self-ID / X-Client-Role / User-Agent 等必要 Headers
- 添加心跳保活（每 15 秒 ping）
- 使用 asyncio.create_task 异步处理 API 请求
"""

import asyncio
import json
import logging
import threading

import websockets
import state
import config
from ob_protocol import handle_api_call

log = logging.getLogger("ob_client")


def _run_ob_client():
    """后台线程：维护到 AstrBot 的 WebSocket 连接。"""
    _loop = asyncio.new_event_loop()
    state._ob_ws_loop = _loop
    asyncio.set_event_loop(_loop)
    try:
        _loop.run_until_complete(_ob_client_main())
    finally:
        try:
            _loop.close()
        except Exception:
            pass
        if state._ob_ws_loop is _loop:
            state._ob_ws_loop = None


async def _ob_client_main():
    """
    WebSocket 客户端主协程：连接 AstrBot，发送事件，接收 API 响应。
    
    关键：必须添加以下 Headers 才能被 AstrBot 接受：
    - X-Self-ID: 机器人 ID
    - X-Client-Role: Universal
    - User-Agent: OneBot/11
    """
    while state.running:
        try:
            log.info(f"[OB11] 正在连接 AstrBot: {config.ASTRBOT_OB_URL}")
            log.info(f"[OB11] Self-ID: {state._self_id_int}")

            # 关键修复：添加 AstrBot aiocqhttp 所需的 Headers
            async with websockets.connect(
                config.ASTRBOT_OB_URL,
                additional_headers={
                    "X-Self-ID": str(state._self_id_int),
                    "X-Client-Role": "Universal",
                    "User-Agent": "OneBot/11",
                },
                ping_interval=15,       # 内置心跳
                ping_timeout=10,        # ping 超时
                close_timeout=5,        # 关闭超时
            ) as ws:
                state._ob_ws = ws
                state._ob_ws_ready.set()
                log.info(f"[OB11] 已连接到 AstrBot @ {config.ASTRBOT_OB_URL}")

                try:
                    # 持续接收 API 请求（异步处理，不阻塞）
                    async for raw in ws:
                        if not state.running:
                            break
                        if state.paused.is_set():
                            continue
                        try:
                            data = json.loads(raw)
                            # 用 create_task 异步处理，不阻塞消息循环
                            asyncio.create_task(_handle_ob_api(data))
                        except json.JSONDecodeError:
                            log.warning(f"[OB11] 收到无效 JSON")
                        except Exception as e:
                            log.error(f"[OB11] 处理 API 异常: {e}")
                finally:
                    pass  # websockets 库自动处理 ping/pong

        except websockets.exceptions.ConnectionClosed as e:
            log.warning(f"[OB11] 连接被关闭: {e}，5 秒后重连")
        except (ConnectionRefusedError, OSError) as e:
            log.warning(f"[OB11] 无法连接 AstrBot: {e}，5 秒后重试")
            log.warning(f"[OB11] 请确认 AstrBot 已启动且 OneBot 端口为 {config.ASTRBOT_OB_URL}")
        except Exception as e:
            log.error(f"[OB11] 连接异常: {e}")

        state._ob_ws = None
        state._ob_ws_ready.clear()

        if not state.running:
            break
        await asyncio.sleep(5)

    state._ob_ws = None


async def _handle_ob_api(data: dict):
    """处理 AstrBot 发来的 API 请求"""
    import state as state_module
    try:
        await handle_api_call(data, None, state_module, state_module.sender_instance, config.config)
    except Exception:
        log.exception(f"[OB11] 处理 API 请求异常: action={data.get('action', '')}")

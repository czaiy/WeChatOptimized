"""
OneBot v11 协议处理模块
参考 Akasha-WeChat ob_protocol.py

包括：
- make_message_event() — 构造 OneBot 消息事件 JSON
- push_event() — 通过 WebSocket 推送事件给 AstrBot
- handle_api_call() — 处理 AstrBot 发来的 API 请求（send_msg 等）
"""

import asyncio
import base64
import json
import logging
import os
import re
import tempfile
import time
from urllib.parse import unquote, urlparse

log = logging.getLogger("ob_protocol")


# ============ 辅助函数 ============

CQ_RE = re.compile(r"\[CQ:([a-zA-Z]+)((?:,[a-zA-Z0-9_]+=[^,\]]*)*)\]")


def _cq_unescape(text: str) -> str:
    return (
        text.replace("&#44;", ",")
        .replace("&#91;", "[")
        .replace("&#93;", "]")
        .replace("&amp;", "&")
    )


def _parse_cq_string(raw: str) -> list:
    """把 CQ 码字符串解析成 OneBot segment 数组。"""
    segs = []
    pos = 0
    for m in CQ_RE.finditer(raw):
        if m.start() > pos:
            text = _cq_unescape(raw[pos:m.start()])
            if text:
                segs.append({"type": "text", "data": {"text": text}})
        seg_type = m.group(1)
        data = {}
        if m.group(2):
            for kv in m.group(2).lstrip(",").split(","):
                if "=" in kv:
                    k, v = kv.split("=", 1)
                    data[k] = _cq_unescape(v)
        segs.append({"type": seg_type, "data": data})
        pos = m.end()
    if pos < len(raw):
        text = _cq_unescape(raw[pos:])
        if text:
            segs.append({"type": "text", "data": {"text": text}})
    return segs


def _file_uri_to_path(uri: str) -> str:
    """file:///C:/xxx -> C:\\xxx（兼容 /C:/ 与 //server/share 形式）"""
    p = urlparse(uri)
    path = unquote(p.path)
    if len(path) >= 3 and path.startswith("/") and path[2] == ":":
        path = path[1:]
    return os.path.normpath(path)


def _download_url_sync(url: str, suffix: str = ".bin") -> str:
    """同步下载 URL 到临时文件（在 to_thread 里调用）。"""
    import requests as _rq

    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.close()
    with _rq.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        with open(tmp.name, "wb") as f:
            for chunk in r.iter_content(1024 * 256):
                f.write(chunk)
    return tmp.name


# ============ OneBot 协议处理 ============


def make_message_event(message_type: str, user_id: int, message: list,
                       group_id: int = 0, group_name: str = "",
                       nickname: str = "", self_id: int = 0) -> dict:
    """构造 OneBot v11 消息事件"""
    event = {
        "time": int(time.time()),
        "self_id": self_id,
        "post_type": "message",
    }
    if message_type == "group":
        event["message_type"] = "group"
        event["group_id"] = group_id
        event["user_id"] = user_id
        event["message"] = message
        event["raw_message"] = "".join(
            seg.get("data", {}).get("text", "") for seg in message
            if seg.get("type") == "text"
        )
        event["sender"] = {"user_id": user_id, "nickname": nickname or str(user_id)}
        event["group_name"] = group_name or str(group_id)
    else:
        event["message_type"] = "private"
        event["user_id"] = user_id
        event["message"] = message
        event["raw_message"] = "".join(
            seg.get("data", {}).get("text", "") for seg in message
            if seg.get("type") == "text"
        )
        event["sender"] = {"user_id": user_id, "nickname": nickname or str(user_id)}
    return event


async def handle_api_call(data: dict, ws, state, sender, config):
    """
    处理 AstrBot 发来的 API 请求。
    参考 Akasha-WeChat ob_protocol.py 的 _handle_ob_api
    """
    import state as state_module

    action = data.get("action", "")
    params = data.get("params", {})
    echo = data.get("echo", "")
    log.info(f"[OB11] API: {action} echo={echo}")

    # 先回响应（必须在处理消息前回，否则 AstrBot 超时）
    resp_sent = False
    resp_data = {"status": "ok", "retcode": 0, "data": {}}
    if echo:
        resp_data["echo"] = echo

    # 重试发送响应
    for retry in range(10):
        try:
            if state_module._ob_ws:
                await state_module._ob_ws.send(json.dumps(resp_data, ensure_ascii=False))
                resp_sent = True
                log.info(f"[OB11] 已回响应: {action}")
                break
            if retry < 9:
                await asyncio.sleep(0.5)
        except Exception as e:
            log.warning(f"[OB11] 回响应失败 (重试 {retry}/10): {e}")
            if retry < 9:
                await asyncio.sleep(0.5)

    if not resp_sent:
        log.warning(f"[OB11] 无法回响应（WS 未连接），消息仍尝试本地处理: {action}")

    if action in ("send_msg", "send_private_msg", "send_group_msg"):
        is_group = action == "send_group_msg"
        target_id = params.get("group_id" if is_group else "user_id", 0)
        message = params.get("message", [])
        contact = state_module._ob_id_to_contact.get(target_id, str(target_id))

        # 字符串消息（CQ 码）统一转成 segment 数组
        if isinstance(message, str):
            message = _parse_cq_string(message)
        if not isinstance(message, list):
            log.warning(f"[OB11] 未知 message 类型: {type(message).__name__}")
            message = []

        # 记录消息段概览，便于排查"收到但没发出去"的问题
        try:
            overview = [
                seg.get("type", "?") if isinstance(seg, dict) else type(seg).__name__
                for seg in message
            ]
            log.info(f"[OB11] 消息段: {overview}")
        except Exception:
            pass

        # 逐段处理：文字和图片分别发送
        for seg in message:
            try:
                await _dispatch_segment(seg, contact, sender, config)
            except Exception:
                log.exception(f"[OB11] 处理消息段异常: {seg}")

    else:
        log.debug(f"[OB11] 未处理 API: {action}")


async def _dispatch_segment(seg, contact, sender, config):
    """处理单个消息段：text / image / face / video / file / record。"""
    if not isinstance(seg, dict):
        return
    seg_type = seg.get("type", "")
    seg_data = seg.get("data", {})

    if seg_type == "text":
        text = seg_data.get("text", "")
        if text:
            # 过滤 PIL 引用
            if "<PIL." in text:
                log.warning(f"[OB11] 跳过 PIL 引用: {text[:60]}")
                return

            await asyncio.to_thread(sender.send_text, contact, text)
            log.info(f"[OB11] 文字已发送至 {contact}: {text[:50]}")

    elif seg_type == "image":
        file_val = seg_data.get("file", "")
        if not file_val:
            return

        img_path = None

        # base64:// 格式
        if file_val.startswith("base64://"):
            try:
                b64_data = file_val[9:]
                img_path = await asyncio.to_thread(_decode_base64_image, b64_data)
                if img_path:
                    log.info(f"[OB11] 图片已解码: {os.path.basename(img_path)}")
            except Exception as e:
                log.warning(f"[OB11] base64 图片解码失败: {e}")
        elif file_val.startswith("file://"):
            cand = _file_uri_to_path(file_val)
            if os.path.exists(cand):
                img_path = cand
            else:
                log.warning(f"[OB11] 图片 file URI 不存在: {cand}")
        elif file_val.startswith(("http://", "https://")):
            try:
                img_path = await asyncio.to_thread(_download_url_sync, file_val, ".img")
                log.info(f"[OB11] 图片已下载: {os.path.basename(img_path)}")
            except Exception as e:
                log.warning(f"[OB11] 图片 URL 下载失败: {e}")
        else:
            # 文件名模式 / 绝对路径
            if os.path.isabs(file_val) and os.path.exists(file_val):
                img_path = file_val
            else:
                attachments = config.get("astrbot_attachments", "")
                if attachments:
                    candidates = [
                        os.path.join(attachments, file_val),
                        os.path.join(attachments, "wechat_images", file_val),
                    ]
                    for p in candidates:
                        if os.path.exists(p):
                            img_path = p
                            break
                    if not img_path:
                        log.warning(f"[OB11] 图片文件未找到: {file_val}")

        if img_path:
            try:
                ok = await asyncio.to_thread(sender.send_image, contact, img_path)
                if ok:
                    log.info(f"[OB11] 图片已发送至 {contact}")
                else:
                    log.warning(f"[OB11] 图片发送失败(sender返回False): {contact} <- {img_path}")
            finally:
                if img_path and "tmp" in img_path:
                    try:
                        os.unlink(img_path)
                    except Exception:
                        pass

    elif seg_type == "face":
        await asyncio.to_thread(sender.send_text, contact, "[表情]")
        log.info(f"[OB11] 表情已发送至 {contact}")

    elif seg_type in ("video", "file", "record"):
        # AstrBot 可能把本地路径转成 file:/// URI 或 http 文件服务 URL
        file_val = (
            seg_data.get("file", "")
            or seg_data.get("url", "")
            or seg_data.get("path", "")
        )
        if not file_val:
            log.warning(f"[OB11] {seg_type} 段缺少 file/url 字段: {seg_data}")
            return

        log.info(f"[OB11] 收到 {seg_type} 段: {str(file_val)[:200]}")
        suffix = ".mp4" if seg_type == "video" else (".silk" if seg_type == "record" else ".dat")
        file_path = None

        # base64:// 格式
        if file_val.startswith("base64://"):
            try:
                b64_data = file_val[9:]
                file_path = await asyncio.to_thread(_decode_base64_file, b64_data, seg_type)
                if file_path:
                    log.info(f"[OB11] {seg_type} 已解码: {os.path.basename(file_path)}")
            except Exception as e:
                log.warning(f"[OB11] base64 {seg_type} 解码失败: {e}")
        elif file_val.startswith("file://"):
            cand = _file_uri_to_path(file_val)
            if os.path.exists(cand):
                file_path = cand
                log.info(f"[OB11] {seg_type} file URI 解析: {file_path}")
            else:
                log.warning(f"[OB11] {seg_type} file URI 路径不存在: {cand}")
        elif file_val.startswith(("http://", "https://")):
            try:
                file_path = await asyncio.to_thread(_download_url_sync, file_val, suffix)
                log.info(f"[OB11] {seg_type} URL 已下载: {file_path}")
            except Exception as e:
                log.warning(f"[OB11] {seg_type} URL 下载失败: {e}")
        elif os.path.isabs(file_val) and os.path.exists(file_val):
            # 绝对路径（video-downloader skill 下载的文件）
            file_path = file_val
            log.info(f"[OB11] {seg_type} 文件路径: {file_path}")
        else:
            # 文件名模式
            attachments = config.get("astrbot_attachments", "")
            if attachments:
                candidates = [
                    os.path.join(attachments, file_val),
                    os.path.join(attachments, "wechat_files", file_val),
                ]
                for p in candidates:
                    if os.path.exists(p):
                        file_path = p
                        break
                if not file_path:
                    log.warning(f"[OB11] {seg_type} 文件未找到: {file_val}")
            else:
                log.warning(f"[OB11] {seg_type} 无法解析: {file_val}")

        if file_path:
            try:
                # 先复制到桥接专用临时副本，避免 skill 清理步骤抢先删除源文件
                import shutil
                import uuid

                ext = os.path.splitext(file_path)[1] or suffix
                priv = os.path.join(tempfile.gettempdir(), f"wxb_{uuid.uuid4().hex[:8]}{ext}")
                await asyncio.to_thread(shutil.copyfile, file_path, priv)
                file_path = priv

                ok = await asyncio.to_thread(sender.send_file, contact, file_path)
                log.info(f"[OB11] {seg_type} {'已发送' if ok else '发送失败'}至 {contact}: {os.path.basename(file_path)}")
            finally:
                # 清理桥接自己的临时副本
                if file_path and os.path.basename(file_path).startswith("wxb_"):
                    try:
                        os.unlink(file_path)
                    except Exception:
                        pass
        else:
            log.warning(f"[OB11] {seg_type} 最终未获得可用文件路径")


def _decode_base64_image(b64_data: str) -> str:
    """解码 base64 图片并保存为临时文件"""
    img_data = base64.b64decode(b64_data)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp.write(img_data)
    tmp.close()
    return tmp.name


def _decode_base64_file(b64_data: str, file_type: str = "file") -> str:
    """解码 base64 文件并保存为临时文件"""
    file_data = base64.b64decode(b64_data)
    suffix = ".mp4" if file_type == "video" else ".dat"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(file_data)
    tmp.close()
    return tmp.name

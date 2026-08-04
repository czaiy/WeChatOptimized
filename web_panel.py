"""
Web 控制面板模块
参考 Akasha-WeChat web_panel.py

提供可视化控制页面（http://127.0.0.1:WEB_PORT），
支持启停/暂停/恢复桥接，显示运行状态和日志，
以及在线编辑 config.json 配置。
"""

import json
import logging
import os
from http.server import HTTPServer, BaseHTTPRequestHandler

import state
import config

log = logging.getLogger("web_panel")


PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>WeChatOptimized</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><text y='28' font-size='28'>&#x1F4E8;</text></svg>">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,'Segoe UI','PingFang SC',sans-serif;background:linear-gradient(135deg,#f0f4f8,#e8edf5,#f0f0fa);height:100vh;color:#2c3e50;display:flex;margin:0;overflow:hidden}

.container{display:flex;width:100vw;height:100vh;background:rgba(255,255,255,0.82);backdrop-filter:blur(16px);overflow:hidden}

.sidebar{width:130px;min-width:130px;background:linear-gradient(180deg,#f7f9fc,#eef1f8);display:flex;flex-direction:column;align-items:center;padding:28px 0;gap:4px;border-right:1px solid rgba(100,120,160,0.08);height:100vh}
.sidebar .logo{font-size:15px;font-weight:800;color:#4a6fa5;margin-bottom:28px;letter-spacing:2px}
.sidebar .nav-item{width:108px;height:46px;border-radius:12px;display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .25s;color:#7a8ba8;font-size:13px;font-weight:600;gap:6px;border:none;background:transparent;padding:0 10px;user-select:none}
.sidebar .nav-item:hover{background:rgba(74,111,165,0.06);color:#4a6fa5}
.sidebar .nav-item.active{background:linear-gradient(135deg,#6c9bd2,#4a6fa5);color:#fff;box-shadow:0 3px 10px rgba(74,111,165,0.25)}
.sidebar .nav-item.active:hover{color:#fff}

.content{flex:1;padding:28px 32px;overflow-y:auto;display:flex;flex-direction:column;gap:16px;height:100vh}
.content::-webkit-scrollbar{width:5px}
.content::-webkit-scrollbar-thumb{background:#d0d8e8;border-radius:4px}

.tab-page{display:none;flex-direction:column;gap:16px;height:100%}
.tab-page.active{display:flex}

.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:2px}
.header h1{font-size:24px;font-weight:700;color:#2c3e50}
.header .badge{font-size:11px;color:#7a8ba8;background:#eef1f8;padding:3px 10px;border-radius:20px;font-weight:500}

.status-row{display:flex;gap:10px;flex-wrap:wrap}
.status-card{flex:1;min-width:100px;background:#fff;border-radius:14px;padding:14px 16px;text-align:center;box-shadow:0 1px 4px rgba(0,0,0,0.03);border:1px solid #e8edf5}
.status-card .label{font-size:11px;color:#7a8ba8;margin-bottom:4px}
.status-card .value{font-size:17px;font-weight:700}
.status-card .value.on{color:#27ae60}
.status-card .value.off{color:#bdc3c7}

.btn-row{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:9px 18px;border:none;border-radius:10px;font-size:13px;font-weight:600;cursor:pointer;transition:all .2s;display:inline-flex;align-items:center;gap:5px}
.btn:disabled{opacity:.35;cursor:not-allowed}
.btn:active:not(:disabled){transform:scale(.97)}
.btn-blue{background:linear-gradient(135deg,#6c9bd2,#4a6fa5);color:#fff;box-shadow:0 2px 8px rgba(74,111,165,0.18)}
.btn-blue:hover:not(:disabled){box-shadow:0 4px 14px rgba(74,111,165,0.28)}
.btn-red{background:linear-gradient(135deg,#e88b8b,#d35f5f);color:#fff;box-shadow:0 2px 8px rgba(211,95,95,0.18)}
.btn-red:hover:not(:disabled){box-shadow:0 4px 14px rgba(211,95,95,0.28)}
.btn-green{background:linear-gradient(135deg,#7dcea0,#27ae60);color:#fff;box-shadow:0 2px 8px rgba(39,174,96,0.18)}
.btn-amber{background:linear-gradient(135deg,#f7c873,#f39c12);color:#fff;box-shadow:0 2px 8px rgba(243,156,18,0.18)}
.btn-outline{background:#fff;color:#4a6fa5;border:1.5px solid #d0d8e8}
.btn-outline:hover:not(:disabled){background:#f0f4fa;border-color:#4a6fa5}

.mode-row{display:flex;align-items:center;gap:10px;font-size:13px;color:#7a8ba8;flex-wrap:wrap}
.mode-row .mode-value{font-weight:600;color:#4a6fa5}

.log-box{flex:1;min-height:120px;background:#1e2a3a;border:1px solid #2c3e50;border-radius:12px;padding:14px;font-size:12px;font-family:'Cascadia Code','Fira Code',monospace;color:#7dcea0;overflow-y:auto;line-height:1.7;white-space:pre-wrap}
.log-box:empty::before{content:'等待连接...';color:#5a6a7a}
.log-box::-webkit-scrollbar{width:4px}
.log-box::-webkit-scrollbar-thumb{background:#3a4a5a;border-radius:4px}

.settings-scroll{flex:1;overflow-y:auto;padding-right:6px}
.settings-scroll::-webkit-scrollbar{width:5px}
.settings-scroll::-webkit-scrollbar-thumb{background:#d0d8e8;border-radius:4px}
.settings-group{margin-bottom:20px;background:#fff;border-radius:14px;padding:16px 18px;border:1px solid #e8edf5}
.settings-group h3{font-size:14px;font-weight:600;color:#4a6fa5;margin-bottom:10px;padding-bottom:6px;border-bottom:1.5px solid #eef1f8}
.settings-group .group-desc{font-size:11px;color:#95a5b8;margin-bottom:10px}
.settings-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:8px}
.settings-field{flex:1;min-width:180px}
.settings-field label{display:block;font-size:11px;color:#7a8ba8;margin-bottom:3px;font-weight:500}
.settings-field input,.settings-field select,.settings-field textarea{width:100%;padding:8px 12px;border:1.5px solid #d8e0ec;border-radius:9px;font-size:12px;outline:none;transition:border .2s;background:#fafbfd;color:#2c3e50;font-family:inherit}
.settings-field input:focus,.settings-field select:focus,.settings-field textarea:focus{border-color:#4a6fa5;box-shadow:0 0 0 3px rgba(74,111,165,0.08)}
.settings-field textarea{resize:vertical;min-height:40px}
.settings-field select{cursor:pointer;appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%237a8ba8'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 10px center;padding-right:28px}

.save-bar{display:flex;justify-content:flex-end;align-items:center;gap:12px;padding-top:12px;border-top:1px solid #e8edf5;margin-top:4px}
.save-bar .save-msg{font-size:12px;color:#27ae60;opacity:0;transition:opacity .4s}
.save-bar .save-msg.show{opacity:1}

.toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:10px 24px;border-radius:12px;font-size:13px;font-weight:500;z-index:99;opacity:0;transition:opacity .3s;pointer-events:none;box-shadow:0 4px 16px rgba(0,0,0,0.08)}
.toast.show{opacity:1}
.toast.ok{background:#eafaf1;color:#1e8449;border:1px solid #a9dfbf}
.toast.err{background:#fdedec;color:#922b21;border:1px solid #f5b7b1}
</style>
</head>
<body>

<div class="toast" id="toast"></div>

<div class="container">

<div class="sidebar">
  <div class="logo">WeOpt</div>
  <button class="nav-item active" data-tab="dashboard" onclick="switchTab('dashboard')">
    <span>控制面板</span>
  </button>
  <button class="nav-item" data-tab="settings" onclick="switchTab('settings')">
    <span>基础设置</span>
  </button>
</div>

<div class="content">

  <div class="tab-page active" id="page-dashboard">
    <div class="header">
      <h1>WeChatOptimized</h1>
      <div class="badge" id="statusBadge">加载中...</div>
    </div>

    <div class="status-row">
      <div class="status-card"><div class="label">桥接状态</div><div class="value" id="s-bridge">-</div></div>
      <div class="status-card"><div class="label">WeFlow</div><div class="value" id="s-weflow">-</div></div>
      <div class="status-card"><div class="label">AstrBot</div><div class="value" id="s-astrbot">-</div></div>
      <div class="status-card"><div class="label">已发送</div><div class="value" id="s-sent">-</div></div>
    </div>

    <div class="btn-row">
      <button class="btn btn-blue" id="b-start" onclick="act('start')">&#9654; 启动</button>
      <button class="btn btn-red" id="b-stop" onclick="act('stop')" disabled>&#9632; 停止</button>
      <button class="btn btn-amber" id="b-pause" onclick="act('pause')" disabled>&#9208; 暂停</button>
      <button class="btn btn-green" id="b-resume" onclick="act('resume')" style="display:none" disabled>&#9654; 恢复</button>
    </div>

    <div class="mode-row">
      群聊模式: <span class="mode-value" id="s-mode">-</span>
      <button class="btn btn-outline" id="b-mode" style="padding:5px 14px;font-size:12px">切换</button>
    </div>

    <div style="font-size:13px;font-weight:600;color:#4a6fa5;margin-top:4px">实时日志</div>
    <div class="log-box" id="log"></div>
  </div>

  <div class="tab-page" id="page-settings">
    <div class="header">
      <h1>基础设置</h1>
      <div class="badge">config.json</div>
    </div>

    <div class="settings-scroll" id="settingsForm">
    </div>

    <div class="save-bar">
      <span class="save-msg" id="saveMsg"></span>
      <button class="btn btn-blue" onclick="saveConfig()">保存配置</button>
    </div>
  </div>

</div>
</div>

<script>
var modeMap = {mention:'仅 @ 回复', all:'全部回复', batch:'批处理'};

function toast(msg, type) {
  var t = document.getElementById('toast');
  t.textContent = msg;
  t.className = 'toast ' + (type || 'ok') + ' show';
  setTimeout(function(){ t.className = 'toast'; }, 2200);
}

function showSaveMsg(text, ok) {
  var el = document.getElementById('saveMsg');
  el.textContent = text;
  el.style.color = ok ? '#27ae60' : '#e74c3c';
  el.className = 'save-msg show';
  setTimeout(function(){ el.className = 'save-msg'; }, 2500);
}

function switchTab(name) {
  document.querySelectorAll('.tab-page').forEach(function(p){ p.classList.remove('active'); });
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.nav-item').forEach(function(n){ n.classList.remove('active'); });
  document.querySelector('[data-tab="' + name + '"]').classList.add('active');
  if (name === 'settings') loadConfig();
}

function refreshDashboard() {
  fetch('/api/status').then(function(r){ return r.json(); }).then(function(s){
    var be = document.getElementById('s-bridge');
    if (!s.running) { be.textContent = '未运行'; be.className = 'value off'; }
    else if (s.paused) { be.textContent = '已暂停'; be.className = 'value warn'; }
    else { be.textContent = '运行中'; be.className = 'value on'; }

    document.getElementById('statusBadge').textContent = s.running ? (s.paused ? '已暂停' : '运行中') : '未运行';

    var we = document.getElementById('s-weflow');
    we.textContent = s.weflow ? '已连接' : '未连接';
    we.className = 'value ' + (s.weflow ? 'on' : 'off');

    var ae = document.getElementById('s-astrbot');
    ae.textContent = s.astrbot ? '已连接' : '未连接';
    ae.className = 'value ' + (s.astrbot ? 'on' : 'off');

    document.getElementById('s-sent').textContent = s.sent || 0;
    document.getElementById('s-mode').textContent = modeMap[s.mode] || s.mode;

    document.getElementById('b-start').disabled = s.running;
    document.getElementById('b-stop').disabled = !s.running;
    document.getElementById('b-pause').disabled = !s.running || s.paused;
    document.getElementById('b-pause').style.display = s.running && !s.paused ? 'inline-flex' : 'none';
    document.getElementById('b-resume').style.display = s.running && s.paused ? 'inline-flex' : 'none';
    document.getElementById('b-resume').disabled = !(s.running && s.paused);

    var logEl = document.getElementById('log');
    var atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 50;
    logEl.textContent = s.log || '';
    if (atBottom) logEl.scrollTop = logEl.scrollHeight;
  }).catch(function(){});
}

function act(cmd) {
  fetch('/api/' + cmd, {method:'POST'}).then(function(r){ return r.json(); }).then(function(d){
    toast(d.msg || '操作已执行');
    setTimeout(refreshDashboard, 600);
  });
}

document.getElementById('b-mode').onclick = function() {
  fetch('/api/toggle-mode', {method:'POST'}).then(function(){ setTimeout(refreshDashboard, 500); });
};

function loadConfig() {
  fetch('/api/config').then(function(r){ return r.json(); }).then(function(cfg){
    renderSettings(cfg);
  }).catch(function(e){
    document.getElementById('settingsForm').innerHTML = '<p style="color:#e74c3c;font-size:13px;">加载配置失败: ' + e.message + '</p>';
  });
}

function renderSettings(cfg) {
  var groups = [
    {title: 'WeFlow 连接', fields: [
      {key:'weflow_base_url', label:'WeFlow API 地址', type:'text', ph:'http://127.0.0.1:5031'},
      {key:'access_token', label:'Access Token', type:'password', ph:'粘贴你的 WeFlow Token'},
    ]},
    {title: 'AstrBot / OneBot v11', fields: [
      {key:'astrbot_ob_url', label:'反向 WebSocket 地址', type:'text', ph:'ws://127.0.0.1:11229/ws'},
      {key:'astrbot_attachments', label:'附件目录', type:'text', ph:'AstrBot 存放图片等附件的路径'},
    ]},
    {title: '机器人身份', fields: [
      {key:'bot_nicknames', label:'机器人昵称（多个用逗号隔开）', type:'text', ph:'例如: 小助手,AI酱'},
      {key:'bot_wxid', label:'机器人 wxid', type:'text', ph:'wxid_xxxxxxxx（可选）'},
    ]},
    {title: '发送器', fields: [
      {key:'send_method', label:'发送方式', type:'select', opts:[{v:'uia',l:'UIA 自动化'},{v:'weflow_api',l:'WeFlow API'}]},
      {key:'sender_search_enabled', label:'自动搜索联系人', type:'select', opts:[{v:'true',l:'启用'},{v:'false',l:'禁用（手动切换）'}]},
    ]},
    {title: '消息缓冲', fields: [
      {key:'buffer_seconds', label:'缓冲时间(秒)', type:'number', ph:'5'},
    ]},
    {title: '群聊设置', fields: [
      {key:'group_reply_mode', label:'群聊回复模式', type:'select', opts:[{v:'mention',l:'仅 @ 回复'},{v:'all',l:'全部回复'},{v:'batch',l:'批处理'}]},
    ]},
    {title: '鼠标漫游', fields: [
      {key:'wanderer_enabled', label:'鼠标漫游', type:'select', opts:[{v:'true',l:'启用'},{v:'false',l:'禁用'}]},
      {key:'wanderer_min_interval', label:'漫游最小间隔(秒)', type:'number', ph:'10'},
      {key:'wanderer_max_interval', label:'漫游最大间隔(秒)', type:'number', ph:'30'},
    ]},
    {title: 'Web 面板', fields: [
      {key:'web_port', label:'Web 面板端口', type:'number', ph:'8766'},
    ]},
    {title: '图片识别', fields: [
      {key:'image_caption_provider', label:'描述服务', type:'select', opts:[{v:'ollama',l:'Ollama 本地'},{v:'openai',l:'OpenAI 兼容 API'}]},
      {key:'image_caption_model', label:'模型名称', type:'text', ph:'llava:7b / gpt-4o'},
      {key:'ollama_base_url', label:'Ollama 地址', type:'text', ph:'http://127.0.0.1:11434'},
      {key:'image_caption_api_base', label:'OpenAI API 地址', type:'text', ph:'https://api.moonshot.cn/v1'},
      {key:'image_caption_api_key', label:'OpenAI API Key', type:'password', ph:'sk-xxx'},
    ]},
  ];

  var html = '';
  groups.forEach(function(g) {
    html += '<div class="settings-group">';
    html += '<h3>' + g.title + '</h3>';
    html += '<div class="settings-row">';
    g.fields.forEach(function(f) {
      var val = cfg[f.key];
      if (val === undefined || val === null) val = '';
      if (Array.isArray(val)) val = val.join(', ');
      if (typeof val === 'boolean') val = String(val);
      html += '<div class="settings-field">';
      html += '<label>' + f.label + '</label>';
      if (f.type === 'select') {
        html += '<select id="cfg_' + f.key + '">';
        f.opts.forEach(function(o){ html += '<option value="' + o.v + '"' + (String(val) === o.v ? ' selected' : '') + '>' + o.l + '</option>'; });
        html += '</select>';
      } else if (f.type === 'number') {
        html += '<input type="number" id="cfg_' + f.key + '" value="' + val + '" placeholder="' + (f.ph||'') + '" step="any">';
      } else {
        html += '<input type="' + f.type + '" id="cfg_' + f.key + '" value="' + String(val).replace(/"/g,'&quot;') + '" placeholder="' + (f.ph||'') + '">';
      }
      html += '</div>';
    });
    html += '</div></div>';
  });

  document.getElementById('settingsForm').innerHTML = html;
}

function collectConfig() {
  var data = {};
  var fields = document.querySelectorAll('#settingsForm [id^="cfg_"]');
  fields.forEach(function(el) {
    var key = el.id.replace('cfg_', '');
    var val = el.value.trim();
    if (key === 'bot_nicknames') {
      val = val ? val.split(/[,，]\s*/).filter(Boolean) : [];
    } else if (el.type === 'number') {
      val = Number(val) || 0;
    } else if (val === 'true') {
      val = true;
    } else if (val === 'false') {
      val = false;
    }
    data[key] = val;
  });
  return data;
}

function saveConfig() {
  var data = collectConfig();
  fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(data),
  }).then(function(r){ return r.json(); }).then(function(res){
    if (res.ok) {
      showSaveMsg('已保存（部分更改需重启生效）', true);
    } else {
      showSaveMsg('保存失败: ' + (res.error || ''), false);
    }
  }).catch(function(e){
    showSaveMsg('保存失败: ' + e.message, false);
  });
}

refreshDashboard();
setInterval(refreshDashboard, 3000);
</script>
</body>
</html>"""


class WebHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/status":
            self._send_status()
        elif self.path == "/api/config":
            self._send_config()
        else:
            self._send_html()

    def do_POST(self):
        if self.path == "/api/start":
            self._do_start()
        elif self.path == "/api/stop":
            self._do_stop()
        elif self.path == "/api/pause":
            self._do_pause()
        elif self.path == "/api/resume":
            self._do_resume()
        elif self.path == "/api/toggle-mode":
            self._toggle_mode()
        elif self.path == "/api/config":
            self._save_config()
        else:
            self._json({"error": "not found"}, 404)

    def _send_html(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(PAGE.encode("utf-8"))

    def _send_status(self):
        ob_connected = state._ob_ws is not None and state._ob_ws_ready.is_set()
        weflow_connected = state.bridge_instance is not None and state.bridge_instance._sse_session is not None

        log_lines = []
        try:
            with open("bridge.log", encoding="utf-8", errors="replace") as f:
                log_lines = f.read().splitlines()[-200:]
        except Exception:
            pass

        sent = 0
        if state.sender_instance:
            try:
                sent = state.sender_instance.get_stats().get("total_sent", 0)
            except Exception:
                pass

        data = {
            "running": state.running,
            "paused": state.paused.is_set(),
            "weflow": weflow_connected,
            "astrbot": ob_connected,
            "mode": state.group_reply_mode,
            "sent": sent,
            "log": "\n".join(log_lines),
        }
        self._json(data)

    def _send_config(self):
        """读取当前 config.json 并返回"""
        try:
            with open(config.CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            self._json(cfg)
        except Exception as e:
            self._json({"error": str(e)}, 500)

    def _save_config(self):
        """保存配置到 config.json 并热更新运行时"""
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            new_cfg = json.loads(body)

            # 读取当前配置，仅覆盖前端传来的字段
            with open(config.CONFIG_FILE, "r", encoding="utf-8") as f:
                current = json.load(f)
            current.update(new_cfg)

            with open(config.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=4)
                f.write("\n")

            # 运行时同步
            if "group_reply_mode" in new_cfg:
                state.group_reply_mode = new_cfg["group_reply_mode"]

            # 重新加载配置
            global_cfg = config.load_config()
            config.config.update(global_cfg)

            log.info("[Web] 配置已保存")
            self._json({"ok": True})

        except Exception as e:
            log.error(f"[Web] 保存配置异常: {e}")
            self._json({"ok": False, "error": str(e)}, 500)

    def _do_start(self):
        from main import _start_bridge
        _start_bridge()
        self._json({"ok": True, "msg": "启动中..."})

    def _do_stop(self):
        from main import _stop_bridge
        _stop_bridge()
        self._json({"ok": True, "msg": "停止中..."})

    def _do_pause(self):
        state.paused.set()
        log.info("[Web] 已暂停")
        self._json({"ok": True, "msg": "已暂停"})

    def _do_resume(self):
        state.paused.clear()
        log.info("[Web] 已恢复")
        self._json({"ok": True, "msg": "已恢复"})

    def _toggle_mode(self):
        mode_order = ["mention", "all", "batch"]
        idx = mode_order.index(state.group_reply_mode) if state.group_reply_mode in mode_order else 0
        new_mode = mode_order[(idx + 1) % len(mode_order)]
        state.group_reply_mode = new_mode

        # 保存到配置文件
        try:
            with open(config.CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            cfg["group_reply_mode"] = new_mode
            with open(config.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=4)
                f.write("\n")
        except Exception as e:
            log.error(f"[Web] 保存配置失败: {e}")

        self._json({"ok": True, "mode": new_mode})

    def _json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass

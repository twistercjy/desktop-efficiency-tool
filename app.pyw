import sys
import json
import os
import threading
import time
import ctypes

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOCK_FILE = os.path.join(SCRIPT_DIR, ".lock")

try:
    import webview
except ImportError:
    ctypes.windll.user32.MessageBoxW(
        0,
        "缺少 pywebview 模块。\n\n请在命令行执行：\npip install pywebview\n\n"
        f"当前 Python 路径：{sys.executable}",
        "桌面效率小工具 - 启动失败",
        0x10,
    )
    sys.exit(1)

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

APP_VERSION = "1.1.0"
GITHUB_REPO = "twistercjy/desktop-efficiency-tool"
UPDATE_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
DATA_FILE = os.path.join(os.path.expanduser("~"), ".desktop_tool_data.json")
CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".desktop_tool_config.json")


def _acquire_lock():
    try:
        if os.path.exists(LOCK_FILE):
            try:
                with open(LOCK_FILE, "r") as f:
                    old_pid = int(f.read().strip())
                import signal
                os.kill(old_pid, 0)
                ctypes.windll.user32.MessageBoxW(
                    0, "桌面效率小工具已在运行中。", "提示", 0x40,
                )
                sys.exit(0)
            except (OSError, ValueError):
                pass
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        pass


def _release_lock():
    try:
        os.remove(LOCK_FILE)
    except Exception:
        pass


def load_json(path, default=None):
    if default is None:
        default = {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class Api:
    def __init__(self, window_ref):
        self._window_ref = window_ref

    def save_data(self, data_json):
        save_json(DATA_FILE, json.loads(data_json))

    def load_data(self):
        return json.dumps(load_json(DATA_FILE, {}))

    def save_config(self, key, value):
        cfg = load_json(CONFIG_FILE, {})
        cfg[key] = value
        save_json(CONFIG_FILE, cfg)

    _BUILTIN_DEFAULTS = {
        "deepseek_api_key": "sk-ef6975b8e985477d9e1c7cd3694bcf97",
    }

    def load_config(self, key):
        cfg = load_json(CONFIG_FILE, {})
        return cfg.get(key, "") or self._BUILTIN_DEFAULTS.get(key, "")

    def play_sound(self):
        if HAS_WINSOUND:
            def _beep():
                for _ in range(3):
                    try:
                        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                    except Exception:
                        break
                    time.sleep(1.2)
            threading.Thread(target=_beep, daemon=True).start()

    def show_alert(self, title, message):
        def _notify():
            try:
                from winrt.windows.ui.notifications import (
                    ToastNotificationManager, ToastNotification,
                )
                from winrt.windows.data.xml.dom import XmlDocument
                xml = XmlDocument()
                xml.load_xml(
                    f'<toast duration="long"><visual><binding template="ToastGeneric">'
                    f'<text>{title}</text>'
                    f'<text>{message}</text>'
                    f'</binding></visual>'
                    f'<audio src="ms-winsoundevent:Notification.Default"/>'
                    f'</toast>'
                )
                notifier = ToastNotificationManager.create_toast_notifier("桌面效率小工具")
                notifier.show(ToastNotification(xml))
                return
            except Exception:
                pass
            try:
                FLASHW_ALL = 0x03
                FLASHW_TIMERNOFG = 0x0C
                class FLASHWINFO(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", ctypes.c_uint),
                        ("hwnd", ctypes.c_void_p),
                        ("dwFlags", ctypes.c_uint),
                        ("uCount", ctypes.c_uint),
                        ("dwTimeout", ctypes.c_uint),
                    ]
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                finfo = FLASHWINFO(
                    cbSize=ctypes.sizeof(FLASHWINFO),
                    hwnd=hwnd,
                    dwFlags=FLASHW_ALL | FLASHW_TIMERNOFG,
                    uCount=5,
                    dwTimeout=0,
                )
                ctypes.windll.user32.FlashWindowEx(ctypes.byref(finfo))
            except Exception:
                pass
        threading.Thread(target=_notify, daemon=True).start()

    def get_version(self):
        return APP_VERSION

    def check_update(self):
        import urllib.request
        try:
            req = urllib.request.Request(UPDATE_URL, headers={
                "User-Agent": "DesktopTool/" + APP_VERSION,
                "Accept": "application/vnd.github.v3+json"
            })
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
            remote_ver = data.get("tag_name", "").lstrip("v")
            if remote_ver and remote_ver != APP_VERSION:
                local_parts = [int(x) for x in APP_VERSION.split(".")]
                remote_parts = [int(x) for x in remote_ver.split(".")]
                if remote_parts > local_parts:
                    download_url = ""
                    for asset in data.get("assets", []):
                        if asset.get("name", "").endswith(".zip"):
                            download_url = asset["browser_download_url"]
                            break
                    if not download_url:
                        download_url = data.get("html_url", "")
                    return json.dumps({
                        "has_update": True,
                        "version": remote_ver,
                        "url": download_url,
                        "changelog": data.get("body", "")
                    })
            return json.dumps({"has_update": False})
        except Exception:
            return json.dumps({"has_update": False})

    def open_url(self, url):
        import webbrowser
        webbrowser.open(url)

    _DEFAULT_RULES = (
        "- q1（紧急且重要）：有明确截止日期且对目标有重大影响的任务\n"
        "- q2（重要不紧急）：对长期目标重要但没有紧迫时间压力的任务\n"
        "- q3（紧急不重要）：有时间压力但对核心目标影响不大的任务\n"
        "- q4（不紧急不重要）：既不紧急也不重要的事务性任务"
    )

    def call_deepseek(self, api_key, user_text, custom_rules=""):
        import urllib.request
        import urllib.error

        rules = custom_rules.strip() if custom_rules else self._DEFAULT_RULES
        prompt = (
            "\u4f60\u662f\u4e00\u4e2a\u4efb\u52a1\u5206\u6790\u52a9\u624b\u3002"
            "\u8bf7\u4ece\u4ee5\u4e0b\u6587\u672c\u4e2d\u63d0\u53d6\u6240\u6709\u4efb\u52a1/\u5f85\u529e\u4e8b\u9879\uff0c"
            "\u5e76\u6309\u7167\u300c\u7d27\u6025\u91cd\u8981\u56db\u8c61\u9650\u300d\u8fdb\u884c\u5206\u7c7b\u3002\n\n"
            "\u5206\u7c7b\u89c4\u5219\uff1a\n" + rules + "\n\n"
            "\u63d0\u53d6\u8981\u6c42\uff1a\n"
            "- \u63d0\u53d6\u4efb\u52a1\u65f6\uff0c\u53bb\u6389\u53e3\u8bed\u5316\u7684\u4fee\u9970\u8bcd\u548c\u8fde\u63a5\u8bcd"
            "\uff08\u5982\u300c\u60f3\u8981\u300d\u300c\u9700\u8981\u300d\u300c\u8fd8\u6709\u300d\u300c\u7136\u540e\u300d\u300c\u8bb0\u5f97\u300d\u7b49\uff09\uff0c"
            "\u53ea\u4fdd\u7559\u6838\u5fc3\u52a8\u4f5c\u548c\u5bf9\u8c61\n"
            "- \u4f8b\u5982\u300c\u60f3\u8981\u62c9\u5c4e\u300d\u5e94\u63d0\u53d6\u4e3a\u300c\u62c9\u5c4e\u300d\uff0c"
            "\u300c\u8fd8\u6709\u5403\u996d\u300d\u5e94\u63d0\u53d6\u4e3a\u300c\u5403\u996d\u300d\uff0c"
            "\u300c\u8bb0\u5f97\u4e70\u83dc\u300d\u5e94\u63d0\u53d6\u4e3a\u300c\u4e70\u83dc\u300d\n"
            "- \u4efb\u52a1\u540d\u79f0\u5c3d\u91cf\u7b80\u6d01\uff0c\u63a7\u5236\u57282-8\u4e2a\u5b57\n\n"
            "\u8bf7\u4e25\u683c\u4ee5JSON\u683c\u5f0f\u8fd4\u56de\uff0c\u4e0d\u8981\u5305\u542b\u4efb\u4f55\u5176\u4ed6\u6587\u5b57\uff0c\u53ea\u8fd4\u56deJSON\uff1a\n"
            '{"q1":["\u4efb\u52a11","\u4efb\u52a12"],"q2":[],"q3":[],"q4":[]}\n\n'
            "\u7528\u6237\u8f93\u5165\u7684\u6587\u672c\uff1a\n" + user_text
        )

        body = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个任务分析助手，只返回JSON，不要返回其他任何文字。"},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.3,
            "max_tokens": 2000,
        }).encode("utf-8")

        req = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode("utf-8"))
            content = result["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            tasks = json.loads(content)
            return json.dumps({"ok": True, "data": tasks})
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8", errors="replace")[:200]
            except Exception:
                pass
            return json.dumps({"ok": False, "error": f"API 请求失败 ({e.code}): {err_body}"})
        except json.JSONDecodeError:
            return json.dumps({"ok": False, "error": "AI 返回的格式无法解析，请重试"})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)[:200]})


HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>桌面效率小工具</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  :root {
    --bg: #f5f5f7; --surface: rgba(255,255,255,0.8); --surface2: #ffffff;
    --border: rgba(0,0,0,0.06); --text: #1d1d1f; --text-dim: #86868b;
    --accent: #0071e3; --accent-light: #2997ff;
    --red: #ff3b30; --red-bg: rgba(255,59,48,0.06);
    --orange: #ff9500; --orange-bg: rgba(255,149,0,0.06);
    --blue: #5ac8fa; --blue-bg: rgba(90,200,250,0.06);
    --green: #34c759; --green-bg: rgba(52,199,89,0.06);
    --glass: rgba(255,255,255,0.72); --shadow: 0 4px 24px rgba(0,0,0,0.06);
    --transition: all 0.3s cubic-bezier(0.25,0.1,0.25,1);
  }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Display', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    background: var(--bg); color: var(--text); height: 100vh; overflow: hidden;
    display: flex; flex-direction: column;
  }
  .tab-bar {
    display: flex; justify-content: center; gap: 4px; position: relative;
    padding: 16px 24px 12px; flex-shrink: 0;
    background: var(--glass); backdrop-filter: blur(20px); border-bottom: 1px solid var(--border);
  }
  .tab-btn {
    padding: 8px 28px; border: none; background: transparent;
    color: var(--text-dim); border-radius: 980px; cursor: pointer; font-size: 14px;
    font-weight: 500; transition: var(--transition);
  }
  .tab-btn:hover { background: rgba(0,0,0,0.04); color: var(--text); }
  .tab-btn.active { background: var(--accent); color: #fff; box-shadow: 0 2px 8px rgba(0,113,227,0.25); }
  .tab-content { display: none; flex: 1; overflow-y: auto; padding: 0 16px 16px; }
  .tab-content.active { display: flex; flex-direction: column; }

  .ai-section {
    background: var(--glass); backdrop-filter: blur(20px); border: 1px solid var(--border);
    border-radius: 18px; padding: 14px 16px; margin-bottom: 12px; flex-shrink: 0;
    box-shadow: var(--shadow);
  }
  .ai-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
  .ai-title { font-size: 13px; font-weight: 600; color: var(--accent); }
  .ai-key-btn {
    font-size: 11px; color: var(--text-dim); background: rgba(0,0,0,0.04); border: none;
    border-radius: 980px; padding: 4px 12px; cursor: pointer; transition: var(--transition);
  }
  .ai-key-btn:hover { background: rgba(0,0,0,0.08); color: var(--text); }
  .ai-body { display: flex; gap: 8px; align-items: stretch; }
  .ai-textarea {
    flex: 1; min-height: 50px; max-height: 80px; padding: 10px 12px; background: var(--surface2);
    color: var(--text); border: 1px solid var(--border); border-radius: 12px; font-size: 14px;
    font-family: inherit; resize: none; outline: none; transition: var(--transition);
  }
  .ai-textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,113,227,0.15); }
  .ai-textarea::placeholder { color: var(--text-dim); }
  .ai-parse-btn {
    padding: 10px 20px; background: var(--accent); color: #fff; border: none; border-radius: 980px;
    font-size: 13px; font-weight: 500; cursor: pointer; transition: var(--transition); white-space: nowrap;
    align-self: center;
  }
  .ai-parse-btn:hover { filter: brightness(1.1); transform: scale(1.02); }
  .ai-parse-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; filter: none; }
  .ai-status { font-size: 12px; color: var(--text-dim); margin-top: 8px; min-height: 16px; }
  .ai-rules-panel {
    max-height: 0; overflow: hidden; transition: max-height 0.35s cubic-bezier(0.25,0.1,0.25,1), margin 0.35s;
    margin-top: 0;
  }
  .ai-rules-panel.open { max-height: 420px; margin-top: 10px; }
  .ai-rules-inner { display: flex; flex-direction: column; gap: 8px; }
  .ai-rules-inner select {
    padding: 8px 12px; border: 1px solid var(--border); border-radius: 10px;
    background: var(--surface2); color: var(--text); font-size: 13px; outline: none;
    appearance: none; -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2386868b' d='M2 4l4 4 4-4'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 12px center; padding-right: 32px;
    transition: var(--transition);
  }
  .ai-rules-inner select:focus { border-color: var(--accent); }
  .ai-rules-inner select option { background: #fff; color: var(--text); }
  .ai-rules-inner textarea {
    min-height: 140px; max-height: 220px; padding: 10px 12px; background: var(--surface2);
    color: var(--text); border: 1px solid var(--border); border-radius: 10px; font-size: 13px;
    font-family: inherit; resize: none; outline: none; transition: var(--transition); line-height: 1.5;
  }
  .ai-rules-inner textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,113,227,0.12); }
  .ai-rules-bar { display: flex; justify-content: flex-end; gap: 8px; }
  .ai-rules-bar button {
    padding: 6px 16px; border: none; border-radius: 980px; font-size: 12px;
    font-weight: 500; cursor: pointer; transition: var(--transition);
  }
  .ai-rules-save { background: var(--accent); color: #fff; }
  .ai-rules-save:hover { filter: brightness(1.1); }
  .ai-rules-close { background: rgba(0,0,0,0.05); color: var(--text-dim); }
  .ai-rules-close:hover { background: rgba(0,0,0,0.08); color: var(--text); }

  .matrix { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }
  .quadrant {
    border: 1px solid var(--border); border-radius: 18px; padding: 14px;
    display: flex; flex-direction: column; min-height: 0; overflow: hidden;
    backdrop-filter: blur(20px); box-shadow: var(--shadow); transition: var(--transition);
  }
  .q1 { background: linear-gradient(135deg, rgba(255,59,48,0.05), rgba(255,59,48,0.02)); }
  .q2 { background: linear-gradient(135deg, rgba(255,149,0,0.05), rgba(255,149,0,0.02)); }
  .q3 { background: linear-gradient(135deg, rgba(90,200,250,0.05), rgba(90,200,250,0.02)); }
  .q4 { background: linear-gradient(135deg, rgba(52,199,89,0.05), rgba(52,199,89,0.02)); }
  .q-header { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
  .q-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
  .q1 .q-dot { background: var(--red); } .q2 .q-dot { background: var(--orange); }
  .q3 .q-dot { background: var(--blue); } .q4 .q-dot { background: var(--green); }
  .q-title { font-size: 14px; font-weight: 600; letter-spacing: -0.2px; }
  .q-subtitle { font-size: 12px; color: var(--text-dim); margin-left: auto; }
  .q-tasks { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 4px; min-height: 0; }
  .task-item {
    display: flex; align-items: center; gap: 10px; padding: 8px 10px;
    background: rgba(255,255,255,0.6); border-radius: 12px; cursor: grab;
    transition: var(--transition); user-select: none; border: 1px solid transparent;
  }
  .task-item:active { cursor: grabbing; }
  .task-item.dragging { opacity: 0.4; }
  .task-item:hover { background: rgba(255,255,255,0.9); border-color: var(--border); box-shadow: 0 2px 8px rgba(0,0,0,0.04); }
  .q-tasks.drag-over { background: rgba(0,113,227,0.06); border-radius: 12px; outline: 2px dashed var(--accent); outline-offset: -2px; }
  .task-check {
    width: 20px; height: 20px; border: 2px solid #c7c7cc; border-radius: 50%;
    flex-shrink: 0; display: flex; align-items: center; justify-content: center; transition: var(--transition);
  }
  .task-item.done .task-check { background: var(--accent); border-color: var(--accent); }
  .task-item.done .task-check::after { content: '\2713'; color: #fff; font-size: 11px; font-weight: 700; }
  .task-text { flex: 1; font-size: 14px; line-height: 1.4; transition: var(--transition); }
  .task-item.done .task-text { text-decoration: line-through; color: var(--text-dim); opacity: 0.5; }
  .task-time {
    font-size: 11px; color: var(--accent); background: rgba(0,113,227,0.08);
    padding: 2px 8px; border-radius: 980px; white-space: nowrap; flex-shrink: 0;
  }
  .task-item.done .task-time { opacity: 0.4; }
  .q-add { display: flex; gap: 6px; margin-top: 10px; flex-shrink: 0; align-items: center; }
  .q-add input[type="text"] {
    flex: 1; padding: 8px 12px; border: 1px solid var(--border); border-radius: 12px;
    background: var(--surface2); color: var(--text); font-size: 13px; outline: none; transition: var(--transition);
  }
  .q-add input[type="text"]:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,113,227,0.12); }
  .q-add input[type="text"]::placeholder { color: var(--text-dim); }
  .q-add input[type="datetime-local"] {
    width: 130px; padding: 6px 8px; border: 1px solid var(--border); border-radius: 10px;
    background: var(--surface2); color: var(--text); font-size: 11px; outline: none;
    transition: var(--transition); flex-shrink: 0;
  }
  .q-add input[type="datetime-local"]:focus { border-color: var(--accent); }
  .task-actions {
    display: flex; align-items: center; gap: 2px; flex-shrink: 0;
  }
  .task-move, .task-del {
    opacity: 0; cursor: pointer; font-size: 12px; padding: 2px 4px;
    border-radius: 6px; transition: var(--transition); background: none; border: none;
    color: var(--text-dim); line-height: 1;
  }
  .task-item:hover .task-move, .task-item:hover .task-del { opacity: 0.5; }
  .task-move:hover { opacity: 1 !important; background: rgba(0,0,0,0.06); color: var(--text); }
  .task-del { color: var(--red); font-size: 14px; }
  .task-del:hover { opacity: 1 !important; background: rgba(255,59,48,0.1); }
  .task-edit-input {
    flex: 1; padding: 4px 8px; font-size: 14px; font-family: inherit; background: var(--surface2);
    color: var(--text); border: 1px solid var(--accent); border-radius: 8px; outline: none;
    box-shadow: 0 0 0 3px rgba(0,113,227,0.15);
  }
  .q-add button {
    padding: 8px 14px; background: var(--accent); color: #fff; border: none; border-radius: 980px;
    cursor: pointer; font-size: 13px; font-weight: 500; transition: var(--transition); white-space: nowrap; flex-shrink: 0;
  }
  .q-add button:hover { filter: brightness(1.1); transform: scale(1.02); }

  .task-select-wrap { display: flex; flex-direction: column; gap: 8px; }
  .task-select-wrap select {
    appearance: none; -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12'%3E%3Cpath fill='%2386868b' d='M2 4l4 4 4-4'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 12px center; padding-right: 32px;
  }
  .task-select-wrap select option { background: #fff; color: var(--text); }
  .mode-toggle { display: flex; gap: 0; background: rgba(0,0,0,0.06); border-radius: 980px; padding: 3px; }
  .mode-btn {
    flex: 1; padding: 8px 16px; background: transparent; color: var(--text-dim);
    border: none; cursor: pointer; font-size: 13px; font-weight: 500; transition: var(--transition);
    border-radius: 980px;
  }
  .mode-btn.active { background: #fff; color: var(--text); box-shadow: 0 1px 4px rgba(0,0,0,0.1); }
  .mode-btn:hover:not(.active) { color: var(--text); }
  #tab-timer { align-items: center; }
  .timer-card {
    background: var(--glass); backdrop-filter: blur(20px); border: 1px solid var(--border);
    border-radius: 24px; padding: 32px; text-align: center; width: 100%; max-width: 440px;
    box-shadow: var(--shadow);
  }
  .timer-form { display: flex; flex-direction: column; gap: 12px; margin-bottom: 24px; }
  .timer-form label { font-size: 13px; color: var(--text-dim); text-align: left; margin-bottom: -6px; font-weight: 500; }
  .timer-input {
    padding: 12px 16px; border: 1px solid var(--border); border-radius: 12px;
    background: var(--surface2); color: var(--text); font-size: 15px; outline: none;
    transition: var(--transition);
  }
  .timer-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,113,227,0.12); }
  .timer-input::placeholder { color: var(--text-dim); }
  .time-inputs { display: flex; gap: 12px; }
  .time-group { flex: 1; display: flex; flex-direction: column; gap: 4px; align-items: center; }
  .time-group input {
    width: 100%; text-align: center; padding: 12px 6px; border: 1px solid var(--border);
    border-radius: 14px; background: var(--surface2); color: var(--text); font-size: 22px;
    font-weight: 500; outline: none; transition: var(--transition);
  }
  .time-group input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,113,227,0.12); }
  .time-group label { font-size: 12px; color: var(--text-dim); }
  .timer-buttons { display: flex; gap: 12px; justify-content: center; }
  .timer-btn {
    padding: 12px 28px; border: none; border-radius: 980px; font-size: 15px;
    font-weight: 500; cursor: pointer; transition: var(--transition);
  }
  .btn-start { background: var(--accent); color: #fff; box-shadow: 0 2px 12px rgba(0,113,227,0.25); }
  .btn-start:hover { filter: brightness(1.1); transform: scale(1.02); }
  .btn-pause { background: var(--orange); color: #fff; }
  .btn-resume { background: var(--accent); color: #fff; }
  .btn-reset { background: rgba(0,0,0,0.05); color: var(--text-dim); }
  .btn-reset:hover { background: rgba(0,0,0,0.08); color: var(--text); }

  .progress-ring { position: relative; width: 200px; height: 200px; margin: 0 auto; }
  .progress-ring svg { transform: rotate(-90deg); }
  .progress-ring .bg-c { fill: none; stroke: rgba(0,0,0,0.06); stroke-width: 6; }
  .progress-ring .fg-c { fill: none; stroke: var(--accent); stroke-width: 6; stroke-linecap: round; transition: stroke-dashoffset 0.5s ease; }
  .timer-center { position: absolute; top: 50%; left: 50%; transform: translate(-50%,-50%); text-align: center; }
  .timer-display { font-size: 42px; font-weight: 200; color: var(--text); font-variant-numeric: tabular-nums; letter-spacing: -1px; }
  .timer-task-label { font-size: 17px; color: var(--text); margin-bottom: 8px; font-weight: 500; }

  .timer-history {
    background: var(--glass); backdrop-filter: blur(20px); border: 1px solid var(--border);
    border-radius: 18px; padding: 16px; margin-top: 16px; width: 100%; max-width: 440px;
    box-shadow: var(--shadow);
  }
  .timer-history h3 { font-size: 13px; font-weight: 600; color: var(--text-dim); margin-bottom: 10px; }
  .history-item {
    display: flex; justify-content: space-between; align-items: center; padding: 8px 12px;
    background: rgba(0,0,0,0.02); border-radius: 10px; font-size: 13px; margin-bottom: 4px;
  }
  .h-task { color: var(--text); font-weight: 500; }
  .h-time { color: var(--text-dim); }
  .h-done { color: var(--green); font-size: 12px; }
  .history-empty { color: var(--text-dim); font-size: 13px; text-align: center; padding: 12px; }

  .modal-overlay {
    display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.3); backdrop-filter: blur(20px); z-index: 1000;
    align-items: center; justify-content: center;
  }
  .modal-overlay.show { display: flex; }
  .modal {
    background: var(--glass); backdrop-filter: blur(40px); border: 1px solid var(--border);
    border-radius: 24px; padding: 36px; text-align: center; max-width: 340px; width: 90%;
    box-shadow: 0 8px 40px rgba(0,0,0,0.12); animation: modalIn 0.3s cubic-bezier(0.25,0.1,0.25,1);
  }
  @keyframes modalIn { from { transform: scale(0.92); opacity: 0; } to { transform: scale(1); opacity: 1; } }
  .modal-icon { font-size: 44px; margin-bottom: 12px; }
  .modal h2 { font-size: 20px; margin-bottom: 8px; color: var(--text); font-weight: 600; letter-spacing: -0.3px; }
  .modal p { font-size: 15px; color: var(--text-dim); margin-bottom: 20px; line-height: 1.5; }
  .modal-btn {
    padding: 12px 32px; background: var(--accent); color: #fff; border: none; border-radius: 980px;
    font-size: 15px; font-weight: 500; cursor: pointer; transition: var(--transition);
  }
  .modal-btn:hover { filter: brightness(1.1); transform: scale(1.02); }

  .report-card {
    background: var(--glass); backdrop-filter: blur(20px); border: 1px solid var(--border);
    border-radius: 18px; padding: 24px; width: 100%; max-width: 560px;
    box-shadow: var(--shadow);
  }
  .report-card h2 { font-size: 18px; font-weight: 600; margin-bottom: 4px; letter-spacing: -0.3px; }
  .report-date { font-size: 13px; color: var(--text-dim); margin-bottom: 16px; }
  .report-section { margin-bottom: 16px; }
  .report-section h3 { font-size: 14px; font-weight: 600; margin-bottom: 8px; display: flex; align-items: center; gap: 6px; }
  .report-section ul { list-style: none; padding: 0; }
  .report-section li {
    padding: 6px 10px; font-size: 13px; background: rgba(0,0,0,0.02);
    border-radius: 8px; margin-bottom: 4px; display: flex; justify-content: space-between;
  }
  .report-section li .r-time { color: var(--text-dim); font-size: 12px; }
  .report-empty { color: var(--text-dim); font-size: 13px; padding: 6px 10px; }
  .report-actions { display: flex; gap: 10px; justify-content: center; margin-top: 20px; }
  .report-actions button {
    padding: 10px 24px; border: none; border-radius: 980px; font-size: 14px;
    font-weight: 500; cursor: pointer; transition: var(--transition);
  }
  .report-copy { background: var(--accent); color: #fff; }
  .report-copy:hover { filter: brightness(1.1); transform: scale(1.02); }
  #tab-report { align-items: center; padding-top: 16px; }
  .report-date-nav { display:flex; align-items:center; gap:10px; justify-content:center; margin-bottom:14px; }
  .report-nav-btn { width:32px; height:32px; border-radius:50%; border:none; background:rgba(0,122,255,0.1); color:#007aff; font-size:16px; font-weight:700; cursor:pointer; transition:all .2s; display:flex; align-items:center; justify-content:center; }
  .report-nav-btn:hover { background:rgba(0,122,255,0.2); }
  .report-nav-label { font-size:15px; font-weight:600; color:#1d1d1f; min-width:140px; text-align:center; }
  .report-nav-today { border:none; background:#007aff; color:#fff; border-radius:14px; padding:4px 14px; font-size:13px; font-weight:600; cursor:pointer; transition:all .2s; }
  .report-nav-today:hover { filter:brightness(1.1); }
  ::-webkit-scrollbar { width: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: rgba(0,0,0,0.15); border-radius: 3px; }
  ::-webkit-scrollbar-thumb:hover { background: rgba(0,0,0,0.25); }
</style>
</head>
<body>

<div class="tab-bar">
  <button class="tab-btn active" onclick="switchTab('matrix')">四象限任务</button>
  <button class="tab-btn" onclick="switchTab('timer')">计时提醒器</button>
  <button class="tab-btn" onclick="switchTab('report')">工作日报</button>
  <span id="app-version" style="position:absolute;right:18px;font-size:11px;color:rgba(0,0,0,0.28);font-weight:400;letter-spacing:0.5px"></span>
</div>

<div id="tab-matrix" class="tab-content active">
  <div class="ai-section">
    <div class="ai-header">
      <span class="ai-title">AI 智能解析</span>
      <div style="display:flex;gap:6px">
        <button class="ai-key-btn" onclick="toggleRulePanel()">设置规则</button>
        <button class="ai-key-btn" onclick="setApiKey()">设置 Key</button>
      </div>
    </div>
    <div class="ai-body">
      <textarea class="ai-textarea" id="ai-text" placeholder="粘贴会议纪要、工作计划或任意文本，AI 自动分类到四象限..."></textarea>
      <button class="ai-parse-btn" id="ai-btn" onclick="aiParse()">AI 解析</button>
    </div>
    <div class="ai-status" id="ai-status"></div>
    <div class="ai-rules-panel" id="ai-rules-panel">
      <div class="ai-rules-inner">
        <select id="ai-preset" onchange="applyPreset(this.value)">
          <option value="">自定义</option>
          <option value="default">默认规则</option>
          <option value="work">工作场景</option>
          <option value="project">项目管理</option>
          <option value="study">学习计划</option>
          <option value="life">生活场景</option>
        </select>
        <textarea id="ai-rules-text" placeholder="输入你的分类规则，例如：&#10;- q1（紧急且重要）：描述...&#10;- q2（重要不紧急）：描述..."></textarea>
        <div class="ai-rules-bar">
          <button class="ai-rules-close" onclick="toggleRulePanel()">收起</button>
          <button class="ai-rules-save" onclick="saveRules()">保存规则</button>
        </div>
      </div>
    </div>
  </div>
  <div class="matrix">
    <div class="quadrant q1">
      <div class="q-header"><span class="q-dot"></span><span class="q-title">紧急且重要</span><span class="q-subtitle">立即执行</span></div>
      <div class="q-tasks" id="tasks-q1"></div>
      <div class="q-add"><input type="text" placeholder="添加任务..." onkeydown="if(event.key==='Enter')addTaskFromUI('q1',this)"><input type="datetime-local" class="q-time-input"><button onclick="addTaskFromUI('q1',this.parentElement.querySelector('input[type=text]'))">添加</button></div>
    </div>
    <div class="quadrant q2">
      <div class="q-header"><span class="q-dot"></span><span class="q-title">重要不紧急</span><span class="q-subtitle">计划安排</span></div>
      <div class="q-tasks" id="tasks-q2"></div>
      <div class="q-add"><input type="text" placeholder="添加任务..." onkeydown="if(event.key==='Enter')addTaskFromUI('q2',this)"><input type="datetime-local" class="q-time-input"><button onclick="addTaskFromUI('q2',this.parentElement.querySelector('input[type=text]'))">添加</button></div>
    </div>
    <div class="quadrant q3">
      <div class="q-header"><span class="q-dot"></span><span class="q-title">紧急不重要</span><span class="q-subtitle">委托他人</span></div>
      <div class="q-tasks" id="tasks-q3"></div>
      <div class="q-add"><input type="text" placeholder="添加任务..." onkeydown="if(event.key==='Enter')addTaskFromUI('q3',this)"><input type="datetime-local" class="q-time-input"><button onclick="addTaskFromUI('q3',this.parentElement.querySelector('input[type=text]'))">添加</button></div>
    </div>
    <div class="quadrant q4">
      <div class="q-header"><span class="q-dot"></span><span class="q-title">不紧急不重要</span><span class="q-subtitle">尽量减少</span></div>
      <div class="q-tasks" id="tasks-q4"></div>
      <div class="q-add"><input type="text" placeholder="添加任务..." onkeydown="if(event.key==='Enter')addTaskFromUI('q4',this)"><input type="datetime-local" class="q-time-input"><button onclick="addTaskFromUI('q4',this.parentElement.querySelector('input[type=text]'))">添加</button></div>
    </div>
  </div>
</div>

<div id="tab-timer" class="tab-content">
  <div class="timer-card" id="timer-setup">
    <div class="timer-form">
      <label>任务名称</label>
      <div class="task-select-wrap">
        <select class="timer-input" id="timer-task-select" onchange="onTaskSelect()">
          <option value="">选择任务</option>
        </select>
        <input class="timer-input" type="text" id="timer-task" placeholder="或手动输入任务名称...">
      </div>
      <label>计时模式</label>
      <div class="mode-toggle">
        <button class="mode-btn active" id="mode-down" onclick="setTimerMode('down')">倒计时</button>
        <button class="mode-btn" id="mode-up" onclick="setTimerMode('up')">正计时</button>
      </div>
      <div id="countdown-inputs">
        <label>倒计时时长</label>
        <div class="time-inputs">
          <div class="time-group"><input type="number" id="t-h" value="0" min="0" max="23"><label>小时</label></div>
          <div class="time-group"><input type="number" id="t-m" value="25" min="0" max="59"><label>分钟</label></div>
          <div class="time-group"><input type="number" id="t-s" value="0" min="0" max="59"><label>秒</label></div>
        </div>
      </div>
    </div>
    <div class="timer-buttons"><button class="timer-btn btn-start" onclick="startTimer()">开始计时</button></div>
  </div>
  <div class="timer-card" id="timer-running" style="display:none">
    <div class="timer-task-label" id="run-task"></div>
    <div class="progress-ring">
      <svg width="200" height="200">
        <circle class="bg-c" cx="100" cy="100" r="90"></circle>
        <circle class="fg-c" id="progress-c" cx="100" cy="100" r="90" stroke-dasharray="565.49" stroke-dashoffset="0"></circle>
      </svg>
      <div class="timer-center"><div class="timer-display" id="timer-disp">25:00</div></div>
    </div>
    <div class="timer-buttons" style="margin-top:20px">
      <button class="timer-btn btn-pause" id="pause-btn" onclick="togglePause()">暂停</button>
      <button class="timer-btn btn-start" id="stop-up-btn" onclick="stopUp()" style="display:none">完成</button>
      <button class="timer-btn btn-reset" onclick="resetTimer()">取消</button>
    </div>
  </div>
  <div class="timer-history">
    <h3>完成记录</h3>
    <div id="history-list"><div class="history-empty">暂无记录</div></div>
  </div>
</div>

<div id="tab-report" class="tab-content">
  <div class="report-date-nav" id="report-date-nav">
    <button class="report-nav-btn" onclick="navReport(-1)">&lt;</button>
    <span class="report-nav-label" id="report-date-label"></span>
    <button class="report-nav-btn" onclick="navReport(1)">&gt;</button>
    <button class="report-nav-today" onclick="navReportToday()">今天</button>
  </div>
  <div class="report-card" id="report-content"></div>
  <div class="report-actions">
    <button class="report-copy" onclick="copyReport()">复制日报文本</button>
  </div>
</div>

<div class="modal-overlay" id="modal-overlay">
  <div class="modal">
    <div class="modal-icon">⏰</div>
    <h2>时间到！</h2>
    <p id="modal-msg"></p>
    <button class="modal-btn" onclick="closeModal()">知道了</button>
  </div>
</div>

<script>
let timerInterval=null, timerTotal=0, timerRemaining=0, timerPaused=false, currentTask='';
let timerMode='down', timerElapsed=0;

function esc(s){let d=document.createElement('div');d.textContent=s;return d.innerHTML;}

function switchTab(t){
  var tabs=['matrix','timer','report'];
  document.querySelectorAll('.tab-btn').forEach((b,i)=>b.classList.toggle('active',i===tabs.indexOf(t)));
  document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
  document.getElementById('tab-'+t).classList.add('active');
  if(t==='timer') refreshTaskSelect();
  if(t==='report') generateReport(_reportDate);
}

function addTaskFromUI(q,inp){
  let t=inp.value.trim(); if(!t)return;
  let timeInp=inp.parentElement.querySelector('.q-time-input');
  let tm=timeInp?timeInp.value:'';
  renderTask(q,t,false,tm); inp.value=''; saveAll(); setDefaultTimes();
}
function addTask(q,text,done,tm){
  renderTask(q,text,done||false,tm||'');
}

function editTask(e){
  e.stopPropagation();
  let span=this, old=span.textContent, item=span.closest('.task-item');
  item.draggable=false;
  let inp=document.createElement('input');
  inp.type='text'; inp.value=old; inp.className='task-edit-input';
  span.style.display='none';
  span.parentElement.insertBefore(inp,span);
  inp.focus(); inp.select();
  let committed=false;
  function commit(){
    if(committed)return; committed=true;
    let nv=inp.value.trim()||old;
    span.textContent=nv;
    span.style.display='';
    inp.remove();
    item.draggable=true;
    saveAll();
  }
  inp.addEventListener('blur',commit);
  inp.addEventListener('keydown',function(ev){if(ev.key==='Enter')this.blur();if(ev.key==='Escape'){this.value=old;this.blur();}});
}

function fmtTime(dt){
  if(!dt)return '';
  let d=new Date(dt);
  if(isNaN(d))return dt;
  return (d.getMonth()+1)+'/'+d.getDate()+' '+p(d.getHours())+':'+p(d.getMinutes());
}
function todayStr(){var d=new Date();return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());}
function renderTask(q,text,done,tm,doneDate,atEnd){
  let c=document.getElementById('tasks-'+q);
  let el=document.createElement('div');
  el.className='task-item'+(done?' done':'');
  el.draggable=true;
  if(tm)el.dataset.time=tm;
  if(doneDate)el.dataset.doneDate=doneDate;
  let timeHtml=tm?'<span class="task-time">'+esc(fmtTime(tm))+'</span>':'';
  el.innerHTML='<div class="task-check" onclick="toggleTask(this)"></div><span class="task-text">'+esc(text)+'</span>'+timeHtml+'<div class="task-actions"><button class="task-move" onclick="event.stopPropagation();moveTask(this,\'up\')">\u25B2</button><button class="task-move" onclick="event.stopPropagation();moveTask(this,\'down\')">\u25BC</button><button class="task-del" onclick="event.stopPropagation();this.closest(\'.task-item\').remove();saveAll()">\u2715</button></div>';
  var ts=el.querySelector('.task-text'), _ct=null;
  ts.addEventListener('click',function(e){e.stopPropagation();if(_ct){clearTimeout(_ct);_ct=null;return;}_ct=setTimeout(function(){_ct=null;toggleTask(ts.previousElementSibling);},250);});
  ts.addEventListener('dblclick',function(e){if(_ct){clearTimeout(_ct);_ct=null;}editTask.call(this,e);});
  el.addEventListener('dragstart',function(e){
    e.dataTransfer.effectAllowed='move';
    this.classList.add('dragging');
    window._dragEl=this;
  });
  el.addEventListener('dragend',function(){
    this.classList.remove('dragging');
    document.querySelectorAll('.q-tasks').forEach(t=>t.classList.remove('drag-over'));
    window._dragEl=null;
  });
  if(atEnd){c.appendChild(el);}
  else{c.insertBefore(el,c.firstChild);}
}

function getDragAfter(zone,y){
  let els=Array.from(zone.querySelectorAll('.task-item:not(.dragging)'));
  let closest=null,closestOff=Number.NEGATIVE_INFINITY;
  els.forEach(el=>{
    let box=el.getBoundingClientRect();
    let off=y-box.top-box.height/2;
    if(off<0 && off>closestOff){closestOff=off;closest=el;}
  });
  return closest;
}
document.querySelectorAll('.q-tasks').forEach(zone=>{
  zone.addEventListener('dragover',function(e){
    e.preventDefault();
    e.dataTransfer.dropEffect='move';
    this.classList.add('drag-over');
  });
  zone.addEventListener('dragleave',function(){
    this.classList.remove('drag-over');
  });
  zone.addEventListener('drop',function(e){
    e.preventDefault();
    this.classList.remove('drag-over');
    if(!window._dragEl)return;
    let after=getDragAfter(this,e.clientY);
    if(after){this.insertBefore(window._dragEl,after);}
    else{this.appendChild(window._dragEl);}
    saveAll();
  });
});

function toggleTask(ch){
  let item=ch.closest('.task-item');
  item.classList.toggle('done');
  if(item.classList.contains('done')){
    item.dataset.doneDate=todayStr();
    item.parentElement.appendChild(item);
  } else {
    delete item.dataset.doneDate;
  }
  saveAll();
}

function saveAll(){
  let d={};
  ['q1','q2','q3','q4'].forEach(q=>{
    let items=document.getElementById('tasks-'+q).querySelectorAll('.task-item');
    d[q]=Array.from(items).map(el=>({text:el.querySelector('.task-text').textContent,done:el.classList.contains('done'),time:el.dataset.time||'',doneDate:el.dataset.doneDate||''}));
  });
  d.history=window._history||[];
  pywebview.api.save_data(JSON.stringify(d));
}

async function loadAll(){
  let raw=await pywebview.api.load_data();
  let d=JSON.parse(raw);
  ['q1','q2','q3','q4'].forEach(q=>{(d[q]||[]).forEach(t=>renderTask(q,t.text,t.done,t.time||'',t.doneDate||'',true));});
  window._history=d.history||[];
  (d.history||[]).forEach(h=>addHistoryUI(h.task,h.time,h.date));
}

function setTimerMode(mode){
  timerMode=mode;
  document.getElementById('mode-down').classList.toggle('active',mode==='down');
  document.getElementById('mode-up').classList.toggle('active',mode==='up');
  document.getElementById('countdown-inputs').style.display=mode==='down'?'':'none';
}

function refreshTaskSelect(){
  let sel=document.getElementById('timer-task-select');
  let cur=sel.value;
  sel.innerHTML='<option value="">\u9009\u62e9\u4efb\u52a1</option>';
  let dots={q1:'\u{1F534}',q2:'\u{1F7E0}',q3:'\u{1F535}',q4:'\u{1F7E2}'};
  ['q1','q2','q3','q4'].forEach(q=>{
    document.getElementById('tasks-'+q).querySelectorAll('.task-item:not(.done)').forEach(el=>{
      let text=el.querySelector('.task-text').textContent;
      let opt=document.createElement('option');
      opt.value=text;
      opt.textContent=dots[q]+' '+text;
      sel.appendChild(opt);
    });
  });
  if(cur)sel.value=cur;
}

function onTaskSelect(){
  let v=document.getElementById('timer-task-select').value;
  if(v) document.getElementById('timer-task').value=v;
}

function startTimer(){
  currentTask=document.getElementById('timer-task').value.trim()||'\u4e13\u6ce8\u4efb\u52a1';
  timerPaused=false; timerElapsed=0;
  if(timerMode==='down'){
    let h=parseInt(document.getElementById('t-h').value)||0;
    let m=parseInt(document.getElementById('t-m').value)||0;
    let s=parseInt(document.getElementById('t-s').value)||0;
    let total=h*3600+m*60+s;
    if(total<=0){alert('\u8bf7\u8bbe\u7f6e\u6709\u6548\u65f6\u95f4');return;}
    timerTotal=total; timerRemaining=total;
  } else {
    timerTotal=0; timerRemaining=0;
  }
  document.getElementById('timer-setup').style.display='none';
  document.getElementById('timer-running').style.display='block';
  document.getElementById('run-task').textContent=currentTask+(timerMode==='up'?' (\u6b63\u8ba1\u65f6)':'');
  document.getElementById('pause-btn').textContent='\u6682\u505c';
  document.getElementById('pause-btn').className='timer-btn btn-pause';
  document.getElementById('stop-up-btn').style.display='';
  updateDisp();
  timerInterval=setInterval(tick,1000);
}

function tick(){
  if(timerPaused)return;
  if(timerMode==='down'){
    timerRemaining--;
    updateDisp();
    if(timerRemaining<=0){clearInterval(timerInterval);timerInterval=null;onDone();}
  } else {
    timerElapsed++;
    updateDisp();
  }
}

function updateDisp(){
  let secs=timerMode==='down'?Math.max(0,timerRemaining):timerElapsed;
  let hh=Math.floor(secs/3600),mm=Math.floor((secs%3600)/60),ss=secs%60;
  let t=hh>0?p(hh)+':'+p(mm)+':'+p(ss):p(mm)+':'+p(ss);
  document.getElementById('timer-disp').textContent=t;
  let circ=document.getElementById('progress-c'),C=2*Math.PI*90;
  if(timerMode==='down'){
    let prog=timerTotal>0?(timerTotal-timerRemaining)/timerTotal:0;
    circ.style.strokeDashoffset=C*(1-prog);
  } else {
    let cycle=1800;
    let prog=(timerElapsed%cycle)/cycle;
    circ.style.strokeDashoffset=C*(1-prog);
  }
  document.title=t+' - '+currentTask;
}

function p(n){return n.toString().padStart(2,'0');}

function togglePause(){
  timerPaused=!timerPaused;
  let btn=document.getElementById('pause-btn');
  btn.textContent=timerPaused?'\u7ee7\u7eed':'\u6682\u505c';
  btn.className='timer-btn '+(timerPaused?'btn-resume':'btn-pause');
}

function resetTimer(){
  clearInterval(timerInterval);timerInterval=null;timerPaused=false;timerElapsed=0;
  document.getElementById('timer-setup').style.display='block';
  document.getElementById('timer-running').style.display='none';
  document.title='\u684c\u9762\u6548\u7387\u5c0f\u5de5\u5177';
  refreshTaskSelect();
}

function stopUp(){
  clearInterval(timerInterval);timerInterval=null;
  let secs=timerMode==='down'?(timerTotal-timerRemaining):timerElapsed;
  let hh=Math.floor(secs/3600),mm=Math.floor((secs%3600)/60),ss=secs%60;
  let ts='';if(hh>0)ts+=hh+'\u5c0f\u65f6';if(mm>0)ts+=mm+'\u5206\u949f';
  if(ss>0||!ts)ts+=ss+'\u79d2';
  let now=new Date(),ds=p(now.getHours())+':'+p(now.getMinutes());
  addHistoryUI(currentTask,ts,ds);
  if(!window._history)window._history=[];
  window._history.unshift({task:currentTask,time:ts,date:ds,dateStr:todayStr()});
  saveAll();
  resetTimer();
}

function onDone(){
  pywebview.api.play_sound();
  pywebview.api.show_alert('\u65f6\u95f4\u5230',currentTask+' \u2014 \u8ba1\u65f6\u5df2\u7ed3\u675f');
  document.getElementById('modal-msg').textContent=currentTask;
  document.getElementById('modal-overlay').classList.add('show');
  let hh=Math.floor(timerTotal/3600),mm=Math.floor((timerTotal%3600)/60);
  let ts='';if(hh>0)ts+=hh+'\u5c0f\u65f6';if(mm>0)ts+=mm+'\u5206\u949f';if(!ts)ts=timerTotal+'\u79d2';
  let now=new Date(),ds=p(now.getHours())+':'+p(now.getMinutes());
  addHistoryUI(currentTask,ts,ds);
  if(!window._history)window._history=[];
  window._history.unshift({task:currentTask,time:ts,date:ds,dateStr:todayStr()});
  saveAll();
}

function addHistoryUI(task,time,date){
  let l=document.getElementById('history-list');
  let em=l.querySelector('.history-empty');if(em)em.remove();
  let el=document.createElement('div');el.className='history-item';
  el.innerHTML='<span class="h-task">'+esc(task)+'</span><span class="h-time">'+esc(time)+'</span><span class="h-done">'+esc(date)+' \u2713</span>';
  l.insertBefore(el,l.firstChild);
}

function closeModal(){document.getElementById('modal-overlay').classList.remove('show');resetTimer();}

var _rulePresets={
  'default':"- q1\uff08\u7d27\u6025\u4e14\u91cd\u8981\uff09\uff1a\u6709\u660e\u786e\u622a\u6b62\u65e5\u671f\u4e14\u5bf9\u76ee\u6807\u6709\u91cd\u5927\u5f71\u54cd\u7684\u4efb\u52a1\n- q2\uff08\u91cd\u8981\u4e0d\u7d27\u6025\uff09\uff1a\u5bf9\u957f\u671f\u76ee\u6807\u91cd\u8981\u4f46\u6ca1\u6709\u7d27\u8feb\u65f6\u95f4\u538b\u529b\u7684\u4efb\u52a1\n- q3\uff08\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u6709\u65f6\u95f4\u538b\u529b\u4f46\u5bf9\u6838\u5fc3\u76ee\u6807\u5f71\u54cd\u4e0d\u5927\u7684\u4efb\u52a1\n- q4\uff08\u4e0d\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u65e2\u4e0d\u7d27\u6025\u4e5f\u4e0d\u91cd\u8981\u7684\u4e8b\u52a1\u6027\u4efb\u52a1",
  'work':"- q1\uff08\u7d27\u6025\u4e14\u91cd\u8981\uff09\uff1a\u9886\u5bfc\u4ea4\u529e\u7684\u7d27\u6025\u4efb\u52a1\u3001\u5f53\u5929\u5fc5\u987b\u5b8c\u6210\u7684\u5de5\u4f5c\n- q2\uff08\u91cd\u8981\u4e0d\u7d27\u6025\uff09\uff1a\u9879\u76ee\u89c4\u5212\u3001\u56e2\u961f\u5efa\u8bbe\u3001\u6280\u80fd\u63d0\u5347\u7b49\u957f\u671f\u4ef7\u503c\u4efb\u52a1\n- q3\uff08\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u4e34\u65f6\u4f1a\u8bae\u3001\u56de\u590d\u6d88\u606f\u3001\u65e5\u5e38\u6c9f\u901a\u534f\u8c03\n- q4\uff08\u4e0d\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u6574\u7406\u6587\u6863\u3001\u53ef\u63a8\u8fdf\u7684\u884c\u653f\u4e8b\u52a1",
  'project':"- q1\uff08\u7d27\u6025\u4e14\u91cd\u8981\uff09\uff1a\u963b\u585e\u6027Bug\u3001\u5373\u5c06\u5230\u671f\u7684\u91cc\u7a0b\u7891\u4efb\u52a1\n- q2\uff08\u91cd\u8981\u4e0d\u7d27\u6025\uff09\uff1a\u67b6\u6784\u8bbe\u8ba1\u3001\u4ee3\u7801\u91cd\u6784\u3001\u6280\u672f\u50a8\u5907\n- q3\uff08\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u4ee3\u7801\u8bc4\u5ba1\u3001\u534f\u4f5c\u6c9f\u901a\u3001\u7b2c\u4e09\u65b9\u5bf9\u63a5\n- q4\uff08\u4e0d\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u6587\u6863\u6574\u7406\u3001\u5de5\u5177\u4f18\u5316\u3001\u975e\u5173\u952e\u4f18\u5316",
  'study':"- q1\uff08\u7d27\u6025\u4e14\u91cd\u8981\uff09\uff1a\u8003\u8bd5\u590d\u4e60\u3001\u4f5c\u4e1a\u622a\u6b62\u3001\u8bba\u6587\u63d0\u4ea4\n- q2\uff08\u91cd\u8981\u4e0d\u7d27\u6025\uff09\uff1a\u6280\u80fd\u5b66\u4e60\u3001\u8bc1\u4e66\u5907\u8003\u3001\u77e5\u8bc6\u62d3\u5c55\n- q3\uff08\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u7b7e\u5230\u6253\u5361\u3001\u7ed9\u7ec4\u5458\u53cd\u9988\u3001\u4e34\u65f6\u4efb\u52a1\n- q4\uff08\u4e0d\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u8bfe\u5916\u9605\u8bfb\u3001\u5a31\u4e50\u6d3b\u52a8\u3001\u793e\u4ea4\u5a92\u4f53",
  'life':"- q1\uff08\u7d27\u6025\u4e14\u91cd\u8981\uff09\uff1a\u5065\u5eb7\u5c31\u533b\u3001\u8d26\u5355\u7f34\u8d39\u3001\u5b89\u5168\u95ee\u9898\n- q2\uff08\u91cd\u8981\u4e0d\u7d27\u6025\uff09\uff1a\u953b\u70bc\u8ba1\u5212\u3001\u5b66\u4e60\u6210\u957f\u3001\u5bb6\u5ead\u5173\u7cfb\u7ef4\u62a4\n- q3\uff08\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u5feb\u9012\u53d6\u4ef6\u3001\u56de\u590d\u6d88\u606f\u3001\u4e34\u65f6\u7ea6\u4f1a\n- q4\uff08\u4e0d\u7d27\u6025\u4e0d\u91cd\u8981\uff09\uff1a\u5a31\u4e50\u4f11\u95f2\u3001\u522b\u5237\u624b\u673a\u3001\u8d2d\u7269\u6d88\u8d39"
};

function toggleRulePanel(){
  document.getElementById('ai-rules-panel').classList.toggle('open');
}
function applyPreset(v){
  if(v && _rulePresets[v]) document.getElementById('ai-rules-text').value=_rulePresets[v];
}
async function saveRules(){
  let r=document.getElementById('ai-rules-text').value.trim();
  await pywebview.api.save_config('ai_parse_rules',r);
  document.getElementById('ai-status').textContent='\u89c4\u5219\u5df2\u4fdd\u5b58';
  document.getElementById('ai-status').style.color='var(--green)';
  toggleRulePanel();
}
async function loadRules(){
  let r=await pywebview.api.load_config('ai_parse_rules');
  if(r) document.getElementById('ai-rules-text').value=r;
}

var _reportDate=todayStr();

function fmtReportDate(ds){
  var parts=ds.split('-');
  return parts[0]+'\u5e74'+parseInt(parts[1])+'\u6708'+parseInt(parts[2])+'\u65e5';
}
function weekDayOf(ds){
  return ['\u661f\u671f\u65e5','\u661f\u671f\u4e00','\u661f\u671f\u4e8c','\u661f\u671f\u4e09','\u661f\u671f\u56db','\u661f\u671f\u4e94','\u661f\u671f\u516d'][new Date(ds+'T00:00:00').getDay()];
}
function shiftDate(ds,delta){
  var d=new Date(ds+'T00:00:00');
  d.setDate(d.getDate()+delta);
  return d.getFullYear()+'-'+p(d.getMonth()+1)+'-'+p(d.getDate());
}
function navReport(delta){
  _reportDate=shiftDate(_reportDate,delta);
  generateReport(_reportDate);
}
function navReportToday(){
  _reportDate=todayStr();
  generateReport(_reportDate);
}
function updateDateLabel(ds){
  var label=fmtReportDate(ds)+' '+weekDayOf(ds);
  if(ds===todayStr()) label+='\uff08\u4eca\u5929\uff09';
  document.getElementById('report-date-label').textContent=label;
}

function generateReport(dateStr){
  if(!dateStr) dateStr=todayStr();
  _reportDate=dateStr;
  var isToday=(dateStr===todayStr());
  updateDateLabel(dateStr);
  var qNames={q1:'\u{1F534} \u7d27\u6025\u4e14\u91cd\u8981',q2:'\u{1F7E0} \u91cd\u8981\u4e0d\u7d27\u6025',q3:'\u{1F535} \u7d27\u6025\u4e0d\u91cd\u8981',q4:'\u{1F7E2} \u4e0d\u7d27\u6025\u4e0d\u91cd\u8981'};
  var html='<h2>\u5de5\u4f5c\u65e5\u62a5</h2>';
  var totalDone=0,totalPending=0;
  ['q1','q2','q3','q4'].forEach(function(q){
    var items=document.getElementById('tasks-'+q).querySelectorAll('.task-item');
    if(!items.length)return;
    var doneList=[],pendList=[];
    items.forEach(function(el){
      var text=el.querySelector('.task-text').textContent;
      var tm=el.dataset.time?fmtTime(el.dataset.time):'';
      if(el.classList.contains('done')){
        var dd=el.dataset.doneDate||'';
        if(dd===dateStr){doneList.push({text:text,time:tm});totalDone++;}
      } else {
        if(isToday){pendList.push({text:text,time:tm});totalPending++;}
      }
    });
    if(!doneList.length && !pendList.length)return;
    html+='<div class="report-section"><h3>'+qNames[q]+'</h3><ul>';
    doneList.forEach(function(t){html+='<li>\u2705 '+esc(t.text)+(t.time?' <span class="r-time">'+esc(t.time)+'</span>':'')+'</li>';});
    pendList.forEach(function(t){html+='<li>\u23F3 '+esc(t.text)+(t.time?' <span class="r-time">'+esc(t.time)+'</span>':'')+'</li>';});
    html+='</ul></div>';
  });
  var hist=(window._history||[]).filter(function(h){return (h.dateStr||'')===dateStr;});
  if(hist.length){
    html+='<div class="report-section"><h3>\u23F1 \u8ba1\u65f6\u8bb0\u5f55</h3><ul>';
    hist.forEach(function(h){html+='<li>'+esc(h.task)+' <span class="r-time">'+esc(h.time)+' | '+esc(h.date)+'</span></li>';});
    html+='</ul></div>';
  }
  if(!totalDone && !totalPending && !hist.length){
    html+='<div class="report-empty">\u8be5\u65e5\u6682\u65e0\u8bb0\u5f55</div>';
  } else {
    html+='<div class="report-section" style="text-align:center;color:var(--text-dim);font-size:13px">';
    html+='\u5df2\u5b8c\u6210 <b style="color:var(--green)">'+totalDone+'</b> \u9879';
    if(isToday) html+=' \u00b7 \u5f85\u5b8c\u6210 <b style="color:var(--orange)">'+totalPending+'</b> \u9879';
    html+='</div>';
  }
  document.getElementById('report-content').innerHTML=html;
}

function copyReport(){
  var dateStr=_reportDate;
  var isToday=(dateStr===todayStr());
  var qNames={q1:'\u7d27\u6025\u4e14\u91cd\u8981',q2:'\u91cd\u8981\u4e0d\u7d27\u6025',q3:'\u7d27\u6025\u4e0d\u91cd\u8981',q4:'\u4e0d\u7d27\u6025\u4e0d\u91cd\u8981'};
  var lines=['\u3010\u5de5\u4f5c\u65e5\u62a5\u3011'+fmtReportDate(dateStr)+' '+weekDayOf(dateStr),''];
  ['q1','q2','q3','q4'].forEach(function(q){
    var items=document.getElementById('tasks-'+q).querySelectorAll('.task-item');
    if(!items.length)return;
    var sectionLines=[];
    items.forEach(function(el){
      var text=el.querySelector('.task-text').textContent;
      var tm=el.dataset.time?fmtTime(el.dataset.time):'';
      if(el.classList.contains('done')){
        var dd=el.dataset.doneDate||'';
        if(dd===dateStr) sectionLines.push('  \u2705 '+text+(tm?' ('+tm+')':''));
      } else {
        if(isToday) sectionLines.push('  \u23F3 '+text+(tm?' ('+tm+')':''));
      }
    });
    if(sectionLines.length){
      lines.push('\u25a0 '+qNames[q]);
      lines=lines.concat(sectionLines);
      lines.push('');
    }
  });
  var hist=(window._history||[]).filter(function(h){return (h.dateStr||'')===dateStr;});
  if(hist.length){
    lines.push('\u25a0 \u8ba1\u65f6\u8bb0\u5f55');
    hist.forEach(function(h){lines.push('  - '+h.task+' '+h.time+' @'+h.date);});
    lines.push('');
  }
  var txt=lines.join('\n');
  navigator.clipboard.writeText(txt).then(function(){
    var btn=document.querySelector('.report-copy');
    btn.textContent='\u5df2\u590d\u5236\uff01';
    setTimeout(function(){btn.textContent='\u590d\u5236\u65e5\u62a5\u6587\u672c';},1500);
  });
}

function moveTask(btn,dir){
  let item=btn.closest('.task-item'), parent=item.parentElement;
  if(dir==='up' && item.previousElementSibling){
    parent.insertBefore(item,item.previousElementSibling);
  } else if(dir==='down' && item.nextElementSibling){
    parent.insertBefore(item.nextElementSibling,item);
  }
  saveAll();
}

async function setApiKey(){
  let cur=await pywebview.api.load_config('deepseek_api_key');
  let k=prompt('\u8bf7\u8f93\u5165 DeepSeek API Key\uff1a\n(\u6ce8\u518c: platform.deepseek.com)',cur||'');
  if(k!==null){await pywebview.api.save_config('deepseek_api_key',k.trim());document.getElementById('ai-status').textContent='API Key \u5df2\u4fdd\u5b58';document.getElementById('ai-status').style.color='var(--green)';}
}

async function aiParse(){
  let text=document.getElementById('ai-text').value.trim();
  if(!text){document.getElementById('ai-status').textContent='\u8bf7\u5148\u8f93\u5165\u6587\u672c';document.getElementById('ai-status').style.color='var(--orange)';return;}
  let key=await pywebview.api.load_config('deepseek_api_key');
  if(!key){document.getElementById('ai-status').textContent='\u8bf7\u5148\u8bbe\u7f6e API Key';document.getElementById('ai-status').style.color='var(--orange)';return;}
  let btn=document.getElementById('ai-btn');
  btn.disabled=true;btn.textContent='\u89e3\u6790\u4e2d...';
  document.getElementById('ai-status').textContent='\u6b63\u5728\u8c03\u7528 AI \u5206\u6790...';document.getElementById('ai-status').style.color='var(--accent)';
  let rules=document.getElementById('ai-rules-text').value.trim();
  let raw=await pywebview.api.call_deepseek(key,text,rules);
  let res=JSON.parse(raw);
  btn.disabled=false;btn.textContent='AI \u89e3\u6790';
  if(res.ok){
    let cnt=0;
    ['q1','q2','q3','q4'].forEach(q=>{(res.data[q]||[]).forEach(t=>{if(t){renderTask(q,t.trim(),false,'');cnt++;}});});
    saveAll();
    document.getElementById('ai-status').textContent='\u89e3\u6790\u5b8c\u6210\uff01\u5df2\u6dfb\u52a0 '+cnt+' \u4e2a\u4efb\u52a1';document.getElementById('ai-status').style.color='var(--green)';
    document.getElementById('ai-text').value='';
  } else {
    document.getElementById('ai-status').textContent='\u9519\u8bef\uff1a'+res.error;document.getElementById('ai-status').style.color='var(--red)';
  }
}

function setDefaultTimes(){
  var now=new Date();
  now.setMinutes(now.getMinutes()-now.getTimezoneOffset());
  var v=now.toISOString().slice(0,16);
  document.querySelectorAll('.q-time-input').forEach(function(inp){inp.value=v;});
}
async function checkUpdate(){
  try{
    var r=await pywebview.api.check_update();
    var d=JSON.parse(r);
    if(d.has_update){
      var msg='发现新版本 v'+d.version+'！\n\n';
      if(d.changelog)msg+='更新内容：'+d.changelog+'\n\n';
      msg+='是否立即下载更新？';
      if(confirm(msg)){
        pywebview.api.open_url(d.url);
      }
    }
  }catch(e){}
}
async function showVersion(){
  try{
    var v=await pywebview.api.get_version();
    var el=document.getElementById('app-version');
    if(el)el.textContent='v'+v;
  }catch(e){}
}
window.addEventListener('pywebviewready',()=>{loadAll();loadRules();setDefaultTimes();showVersion();setTimeout(checkUpdate,2000);});
</script>
</body>
</html>"""


def main():
    _acquire_lock()
    try:
        window = None
        api = Api(lambda: window)
        window = webview.create_window(
            "桌面效率小工具",
            html=HTML,
            js_api=api,
            width=920,
            height=720,
            min_size=(700, 500),
            background_color="#f5f5f7",
        )
        webview.start()
    except Exception as e:
        ctypes.windll.user32.MessageBoxW(
            0,
            f"启动失败：\n{e}\n\n请截图反馈此信息。",
            "桌面效率小工具 - 错误",
            0x10,
        )
    finally:
        _release_lock()


if __name__ == "__main__":
    main()

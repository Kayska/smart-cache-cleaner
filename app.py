# -*- coding: utf-8 -*-
"""
智能缓存清理器 - 应用入口（pywebview + WebView2）
后端逻辑在 core.py，界面在 web/ 目录。前端通过 window.pywebview.api 调用这里的方法，
后端通过 window.__push(...) 把扫描进度和日志推给前端。
"""

import base64
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

import webview

import core

APP_NAME = "智能缓存清理器"
APP_VER = "2.1"
THEMES = ("aurora", "violet", "glacier", "ember", "daylight")


def base_dir():
    return getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.abspath(__file__))


WEB_INDEX = os.path.join(base_dir(), "web", "index.html")
SETTINGS_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "SmartCacheCleaner")
SETTINGS_FILE = os.path.join(SETTINGS_DIR, "settings.json")
BG_PREFIX = os.path.join(SETTINGS_DIR, "background")
BG_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".bmp": "image/bmp", ".avif": "image/avif", ".gif": "image/gif",
}


def disk_info():
    out = []
    for code in range(ord("C"), ord("Z") + 1):
        drive = chr(code) + ":\\"
        if not os.path.isdir(drive):
            continue
        try:
            usage = shutil.disk_usage(drive)
        except OSError:
            continue
        out.append({
            "drive": chr(code),
            "total": usage.total,
            "free": usage.free,
            "used": usage.used,
        })
    return out


class Api:
    """前端可调用的方法集合（window.pywebview.api.*）。"""

    def __init__(self):
        self._window = None
        self._q = queue.Queue()
        self._stop_event = threading.Event()
        self._scanning = False
        self._cleaning = False
        self._files = {}
        self._seq = 0
        self._recycled_bytes = 0
        self._last_roots = []
        self._presets = core.build_presets()
        self._custom = []
        self._idle_days = 7
        self._prune_empty = True
        self._theme = "aurora"
        self.load_settings()

    # ---------- 基础设施 ----------
    def attach(self, window):
        self._window = window
        threading.Thread(target=self._dispatch, daemon=True).start()

    def emit(self, kind, payload):
        self._q.put((kind, payload))

    def _dispatch(self):
        """把事件攒一小段再推给前端，避免上千个文件时刷爆 JS 桥。"""
        while True:
            try:
                first = self._q.get(timeout=3600)
            except queue.Empty:
                continue
            time.sleep(0.06)
            items = [first]
            while True:
                try:
                    items.append(self._q.get_nowait())
                except queue.Empty:
                    break
            batch = {}
            for kind, payload in items:
                if kind == "files":
                    batch.setdefault("files", []).extend(payload)
                elif kind == "log":
                    batch.setdefault("log", []).append({"t": int(time.time()), "text": payload})
                else:
                    batch[kind] = payload
            if not self._window:
                continue
            try:
                self._window.evaluate_js("window.__push(" + json.dumps(batch, ensure_ascii=False) + ")")
            except Exception:
                pass  # 窗口关闭等情况

    def _log(self, text):
        self.emit("log", text)

    # ---------- 设置 ----------
    def load_settings(self):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            return
        try:
            self._idle_days = max(1, int(s.get("idle_days", 7)))
            self._prune_empty = bool(s.get("prune_empty", True))
            if s.get("theme") in THEMES:
                self._theme = s["theme"]
            self._custom = [p for p in s.get("custom_folders", []) if isinstance(p, str)]
            saved = s.get("presets", {})
            for p in self._presets:
                if p["key"] in saved:
                    p["on"] = bool(saved[p["key"]])
        except Exception:
            pass

    def save_settings(self, data):
        try:
            data = data or {}
            if "idle_days" in data:
                self._idle_days = max(1, int(data["idle_days"]))
            if "prune_empty" in data:
                self._prune_empty = bool(data["prune_empty"])
            if data.get("theme") in THEMES:
                self._theme = data["theme"]
            if "custom" in data:
                self._custom = [str(p) for p in data["custom"]]
            if "presets" in data:
                for p in self._presets:
                    if p["key"] in data["presets"]:
                        p["on"] = bool(data["presets"][p["key"]])
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._settings_dict(), f, ensure_ascii=False, indent=2)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _settings_dict(self):
        return {
            "idle_days": self._idle_days,
            "prune_empty": self._prune_empty,
            "theme": self._theme,
            "custom_folders": self._custom,
            "presets": {p["key"]: p["on"] for p in self._presets},
        }

    # ---------- 背景 ----------
    def _bg_file(self):
        if not os.path.isdir(SETTINGS_DIR):
            return None
        for fn in os.listdir(SETTINGS_DIR):
            full = os.path.join(SETTINGS_DIR, fn)
            if os.path.basename(full).startswith(os.path.basename(BG_PREFIX)) and os.path.isfile(full):
                return full
        return None

    def _bg_data_url(self):
        path = self._bg_file()
        if not path:
            return ""
        ext = os.path.splitext(path)[1].lower()
        mime = BG_TYPES.get(ext, "image/jpeg")
        try:
            with open(path, "rb") as f:
                return f"data:{mime};base64," + base64.b64encode(f.read()).decode("ascii")
        except OSError:
            return ""

    def choose_background(self):
        try:
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG, allow_multiple=False,
                file_types=("图片 (*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.avif;*.gif)",),
            )
            if not result:
                return {"ok": False, "reason": "cancel"}
            src = result[0]
            ext = os.path.splitext(src)[1].lower()
            if ext not in BG_TYPES:
                return {"ok": False, "reason": "type"}
            os.makedirs(SETTINGS_DIR, exist_ok=True)
            old = self._bg_file()
            if old:
                try:
                    os.remove(old)
                except OSError:
                    pass
            dst = BG_PREFIX + ext
            shutil.copyfile(src, dst)
            self._log(f"已更换背景：{os.path.basename(src)}")
            return {"ok": True, "bg": self._bg_data_url(), "name": os.path.basename(src)}
        except Exception as exc:
            return {"ok": False, "reason": "error", "error": str(exc)}

    def clear_background(self):
        old = self._bg_file()
        if old:
            try:
                os.remove(old)
            except OSError:
                pass
        return {"ok": True}

    # ---------- 前端状态 ----------
    def get_state(self):
        return {
            "presets": [dict(p, exists=os.path.isdir(p["path"] or "")) for p in self._presets],
            "custom": self._custom,
            "idle_days": self._idle_days,
            "prune_empty": self._prune_empty,
            "theme": self._theme,
            "bg": self._bg_data_url(),
            "disk": disk_info(),
            "scanning": self._scanning,
            "cleaning": self._cleaning,
            "max_items": core.MAX_ITEMS,
            "version": APP_VER,
        }

    def refresh_disk(self):
        return disk_info()

    def add_folder(self):
        try:
            result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            if not result:
                return {"ok": False}
            path = os.path.normpath(result if isinstance(result, str) else result[0])
            return {"ok": True, "path": path}
        except Exception:
            return {"ok": False}

    # ---------- 扫描 ----------
    def start_scan(self):
        if self._scanning or self._cleaning:
            return {"ok": False, "error": "busy"}
        roots = [(p["key"], p["path"]) for p in self._presets if p["on"] and p["path"] and os.path.isdir(p["path"])]
        roots += [("custom", d) for d in self._custom if os.path.isdir(d)]
        # 同一路径可能被两个预设指向，去重
        uniq, seen = [], set()
        for key, path in roots:
            norm = os.path.normcase(os.path.abspath(path))
            if norm in seen:
                continue
            seen.add(norm)
            uniq.append((key, path))
        roots = uniq
        if not roots:
            return {"ok": False, "error": "noroots"}

        self._files.clear()
        self._seq = 0
        self._last_roots = [path for _, path in roots]
        self._stop_event.clear()
        self._scanning = True
        threading.Thread(target=self._scan, args=(roots, self._idle_days), daemon=True).start()
        return {"ok": True, "roots": len(roots)}

    def _scan(self, roots, idle_days):
        skip = (
            os.path.normcase(os.path.abspath(os.path.dirname(sys.executable))) + os.sep,
            os.path.normcase(os.path.abspath(base_dir())) + os.sep,
            os.path.normcase(os.path.abspath(SETTINGS_DIR)) + os.sep,
        )
        self._log(f"开始扫描 {len(roots)} 个位置，闲置阈值 {idle_days} 天")
        count = 0
        total = 0
        capped = False
        pending = []
        try:
            for key, path in roots:
                self._log(f"扫描 {path}")
                for item in core.scan_roots([(key, path)], idle_days, self._stop_event, skip):
                    if "__error__" in item:
                        self._log(f"出错：{item['__error__']}")
                        continue
                    if count >= core.MAX_ITEMS:
                        capped = True
                        break
                    self._seq += 1
                    item["id"] = self._seq
                    self._files[self._seq] = item
                    pending.append(item)
                    count += 1
                    total += item["size"]
                    if len(pending) >= 80:
                        self.emit("files", pending)
                        pending = []
                if capped or self._stop_event.is_set():
                    break
            if pending:
                self.emit("files", pending)
        except Exception as exc:
            self.emit("error", str(exc))
        self._scanning = False
        stopped = self._stop_event.is_set()
        if capped:
            self._log(f"结果达到上限 {core.MAX_ITEMS} 项，已停止扫描。清理后可再次扫描。")
        elif stopped:
            self._log("扫描已停止。")
        else:
            self._log(f"扫描完成：{count} 个候选文件，共 {core.human_size(total)}。请核对后清理。")
        self.emit("done", {"stopped": stopped, "count": count, "bytes": total, "capped": capped})

    def stop_scan(self):
        if self._scanning:
            self._stop_event.set()
        return {"ok": True}

    # ---------- 清理 ----------
    def clean(self, ids):
        if self._cleaning or self._scanning:
            return {"ok": [], "failed": [], "error": "busy"}
        try:
            ids = [int(i) for i in (ids or [])]
        except (TypeError, ValueError):
            return {"ok": [], "failed": [], "error": "badids"}
        ids = [i for i in ids if i in self._files]
        if not ids:
            return {"ok": [], "failed": [], "error": "empty"}
        self._cleaning = True
        ok, failed = [], []
        dirs_removed = 0
        try:
            drive = os.path.splitdrive(self._files[ids[0]]["path"])[0] + "\\"
            before, _ = core.query_recycle_bin(drive)
            total_batches = (len(ids) + core.BATCH_SIZE - 1) // core.BATCH_SIZE
            self._log(f"开始清理 {len(ids)} 个文件（共 {core.human_size(sum(self._files[i]['size'] for i in ids))}），分 {total_batches} 批")
            for batch_no in range(total_batches):
                batch = ids[batch_no * core.BATCH_SIZE:(batch_no + 1) * core.BATCH_SIZE]
                paths = [self._files[i]["path"] for i in batch]
                rc, aborted = core.recycle_paths(paths)
                batch_failed = False
                for iid, path in zip(batch, paths):
                    if os.path.exists(path):
                        failed.append({"id": iid, "path": path,
                                       "why": "操作被中止" if aborted else f"文件可能正被占用 (rc={rc})"})
                        batch_failed = True
                    else:
                        ok.append(iid)
                self._log(f"第 {batch_no + 1}/{total_batches} 批：已移入 {len(batch) - sum(1 for f in failed if f['id'] in batch)} 个，残留 {sum(1 for f in failed if f['id'] in batch)} 个")
                if batch_failed:
                    self._log("检测到残留文件，已停止后续批次。")
                    break
            if ok and self._prune_empty:
                dirs_removed = core.prune_empty_dirs(
                    [os.path.dirname(self._files[i]["path"]) for i in ok], self._last_roots
                )
                if dirs_removed:
                    self._log(f"已移除 {dirs_removed} 个清空后的空文件夹")
            after, _ = core.query_recycle_bin(drive)
            verify = ""
            if before is not None and after is not None:
                verify = f"{drive} 回收站项目数 {before} → {after}"
            freed = sum(self._files[i]["size"] for i in ok)
            self._recycled_bytes += freed
            for iid in ok:
                self._files.pop(iid, None)
            self._log(f"清理结束：{len(ok)} 个已移入回收站（{core.human_size(freed)}），{len(failed)} 个失败。{verify}")
            self._log("提醒：文件进入回收站后仍占用磁盘空间，确认无误后清空回收站才会真正释放。")
            return {"ok": ok, "failed": failed, "freed": freed, "dirs_removed": dirs_removed, "verify": verify}
        except Exception as exc:
            self._log(f"清理过程异常：{exc}")
            return {"ok": ok, "failed": failed, "error": str(exc), "freed": 0, "dirs_removed": dirs_removed}
        finally:
            self._cleaning = False

    def reveal(self, iid):
        try:
            item = self._files.get(int(iid))
        except (TypeError, ValueError):
            return {"ok": False}
        if not item or not os.path.exists(item["path"]):
            return {"ok": False}
        subprocess.Popen(["explorer.exe", "/select,", item["path"]])
        return {"ok": True}

    def open_recycle_bin(self):
        subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"])
        return {"ok": True}


def _sanitize_webview_env():
    """WebView2 若看到值为空/无效的 WEBVIEW2_USER_DATA_FOLDER，会退回到"在 exe 旁边建数据文件夹"，
    这样清理工具自己反而在用户目录留下缓存。清掉无效值，让 pywebview 使用随用随删的私有目录。"""
    key = "WEBVIEW2_USER_DATA_FOLDER"
    value = os.environ.get(key)
    if key in os.environ and (not value or not os.path.isabs(value or "")):
        del os.environ[key]


def main():
    _sanitize_webview_env()
    api = Api()
    window = webview.create_window(
        f"{APP_NAME} v{APP_VER}", WEB_INDEX, js_api=api, width=1240, height=860, min_size=(980, 700),
        text_select=False, background_color="#0A0C10",
    )

    def on_loaded():
        # 窗口/任务栏图标
        try:
            from System.Drawing import Icon
            ico = os.path.join(base_dir(), "assets", "icon.ico")
            if os.path.exists(ico):
                window.native.Icon = Icon(ico)
        except Exception:
            pass

        # 自检：设置环境变量 SCC_DIAG=<日志路径> 时，把页面是否真的渲染出来写到该文件（不截屏）
        target = os.environ.get("SCC_DIAG")
        if not target:
            return

        def check():
            try:
                info = window.evaluate_js(
                    "JSON.stringify({title: document.title, cards: document.querySelectorAll('.stat').length,"
                    " chips: document.querySelectorAll('.chip').length,"
                    " swatches: document.querySelectorAll('.swatch').length,"
                    " theme: document.body.dataset.theme,"
                    " ready: !!(window.pywebview && window.pywebview.api"
                    " && typeof window.pywebview.api.get_state === 'function'),"
                    " ticker: (document.querySelector('#tickerText') || {}).textContent,"
                    " errs: window.__errs || []})"
                )
            except Exception as exc:
                info = f"ERR {exc}"
            try:
                with open(target, "w", encoding="utf-8") as f:
                    f.write(str(info))
            except OSError:
                pass

        threading.Timer(3.0, check).start()

    window.events.loaded += on_loaded
    webview.start(api.attach, window)


if __name__ == "__main__":
    main()

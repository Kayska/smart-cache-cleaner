# -*- coding: utf-8 -*-
"""视觉验证：启动窗口，用 WebView2 CapturePreview 只截应用页面（不经过屏幕），逐套主题截图 + 扫描结果。
不点击清理按钮。"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webview

import app as appmod

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "shots")
os.makedirs(OUT, exist_ok=True)
THEMES = ["aurora", "violet", "glacier", "ember", "daylight"]


def js(window, code):
    try:
        return window.evaluate_js(code)
    except Exception as exc:
        return f"JSERR {exc}"


def capture(window, name):
    """在 UI 线程里调用 WebView2 的 CapturePreview，输出只含本应用的页面内容。"""
    import clr  # noqa
    from System import Action
    from System.IO import FileStream, FileMode
    from System.Threading.Tasks import Task
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat

    path = os.path.join(OUT, name)
    done = threading.Event()

    def work():
        try:
            browser = window.native.browser.webview
            stream = FileStream(path, FileMode.Create)
            task = browser.CoreWebView2.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream)

            def finish(_t):
                try:
                    stream.Dispose()
                finally:
                    done.set()

            task.ContinueWith(Action[Task](finish))
        except Exception as exc:
            print("CAPTURE_ERR", name, exc)
            done.set()

    window.native.Invoke(Action(work))
    done.wait(20)
    ok = os.path.exists(path) and os.path.getsize(path) > 5000
    print("CAPTURE", name, os.path.getsize(path) if os.path.exists(path) else 0, ok)


def run(window):
    time.sleep(5)
    capture(window, "t0_aurora_home.png")
    for t in THEMES[1:]:
        js(window, f"document.querySelector('.swatch[data-theme={t}]').click()")
        time.sleep(0.9)
        capture(window, f"t_{t}.png")
    js(window, "document.querySelector('.swatch[data-theme=aurora]').click()")
    time.sleep(0.6)
    js(window, "document.querySelector('#scanBtn').click()")
    time.sleep(14)
    print("STATE", js(window, "JSON.stringify({rows:document.querySelectorAll('#rows tr').length,"
                             " total:document.querySelector('#statTotal').textContent,"
                             " ticker:document.querySelector('#tickerText').textContent})"))
    capture(window, "t_aurora_results.png")
    js(window, "document.querySelector('.swatch[data-theme=daylight]').click()")
    time.sleep(0.9)
    capture(window, "t_daylight_results.png")
    js(window, "document.querySelector('.swatch[data-theme=violet]').click()")
    time.sleep(0.9)
    capture(window, "t_violet_results.png")
    print("JS_ERRORS", js(window, "JSON.stringify(window.__errs || [])"))
    window.destroy()


def main():
    api = appmod.Api()
    window = webview.create_window(
        f"{appmod.APP_NAME} v{appmod.APP_VER}", appmod.WEB_INDEX, js_api=api,
        width=1240, height=860, text_select=False, background_color="#0A0C10",
    )
    api.attach(window)
    threading.Thread(target=run, args=(window,), daemon=True).start()
    webview.start()
    print("DONE")


if __name__ == "__main__":
    main()

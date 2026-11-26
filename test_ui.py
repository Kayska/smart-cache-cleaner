# -*- coding: utf-8 -*-
"""
界面实测：启动真实窗口 -> 自动点"开始扫描" -> 截图核对。
只读：不会打开清理确认框，更不会执行清理。
警告：截图截的是屏幕区域，窗口被别的程序挡住时会把别人的窗口也截进来；机器有人在用时不要跑。
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import webview
from PIL import ImageGrab

import app as appmod

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")
os.makedirs(OUT, exist_ok=True)


def shot(window, name):
    import ctypes
    from ctypes import wintypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    hwnd = ctypes.windll.user32.FindWindowW(None, f"{appmod.APP_NAME} v{appmod.APP_VER}")
    rect = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    # 只截客户区，不带标题栏
    client = wintypes.RECT()
    ctypes.windll.user32.GetClientRect(hwnd, ctypes.byref(client))
    pt = wintypes.POINT(0, 0)
    ctypes.windll.user32.ClientToScreen(hwnd, ctypes.byref(pt))
    x, y = pt.x, pt.y
    w, h = client.right, client.bottom
    time.sleep(0.4)
    img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
    img.save(os.path.join(OUT, name))
    print("SHOT", name, img.size)


def js(window, code):
    try:
        return window.evaluate_js(code)
    except Exception as exc:
        return f"JSERR {exc}"


def run(window):
    time.sleep(4)
    shot(window, "1_home.png")
    js(window, "document.querySelector('#scanBtn').click()")
    time.sleep(3)
    shot(window, "2_scanning.png")
    time.sleep(12)
    info = js(window, "JSON.stringify({rows:document.querySelectorAll('#rows tr').length, "
                      "checked:document.querySelectorAll('#rows tr.checked').length, "
                      "total:document.querySelector('#statTotal').textContent, "
                      "count:document.querySelector('#statCount').textContent, "
                      "sel:document.querySelector('#selSize').textContent, "
                      "ticker:document.querySelector('#tickerText').textContent})")
    print("AFTER_SCAN", info)
    shot(window, "3_results.png")
    # 筛选
    js(window, "const q=document.querySelector('#q'); q.value='pip'; q.dispatchEvent(new Event('input'))")
    time.sleep(0.6)
    shot(window, "4_filter.png")
    js(window, "const q=document.querySelector('#q'); q.value=''; q.dispatchEvent(new Event('input'))")
    # 日志展开
    js(window, "document.querySelector('#logToggle').click()")
    time.sleep(0.6)
    shot(window, "5_log.png")
    js(window, "document.querySelector('#logToggle').click()")
    # 注意：这里不点「清理」按钮。确认弹窗一旦被人点确认就会真的移文件，不放在自动测试里。
    errs = js(window, "JSON.stringify(window.__errs || [])")
    print("JS_ERRORS", errs)
    window.destroy()


def main():
    api = appmod.Api()
    window = webview.create_window(
        f"{appmod.APP_NAME} v{appmod.APP_VER}", appmod.WEB_INDEX, js_api=api, width=1240, height=860,
        text_select=False, background_color="#0A0C10",
    )
    api.attach(window)
    threading.Thread(target=run, args=(window,), daemon=True).start()
    webview.start()
    print("UI_TEST_DONE")


if __name__ == "__main__":
    main()

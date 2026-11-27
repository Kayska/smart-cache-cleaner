# -*- coding: utf-8 -*-
"""验证打包后的 exe：等待窗口出现 -> 读页面自检日志 -> 发 WM_CLOSE 关闭。不截屏、不触发扫描或清理。"""
import ctypes
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
# exe 优先找仓库里的 release/，其次找上级目录的 output/（本地打包时的输出位置）
_CANDIDATES = [
    os.path.join(HERE, "release", "智能缓存清理器.exe"),
    os.path.join(HERE, "..", "output", "智能缓存清理器.exe"),
]
EXE = next((p for p in _CANDIDATES if os.path.exists(p)), _CANDIDATES[0])
TITLE = "智能缓存清理器 v2.1"
DIAG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "exe_diag.log")
os.makedirs(os.path.dirname(DIAG), exist_ok=True)
if os.path.exists(DIAG):
    os.remove(DIAG)

print("EXISTS", os.path.exists(EXE), "SIZE_MB", round(os.path.getsize(EXE) / 1024 / 1024, 2) if os.path.exists(EXE) else 0)
user32 = ctypes.windll.user32
stale = user32.FindWindowW(None, TITLE)
if stale:
    user32.PostMessageW(stale, 0x0010, 0, 0)
    time.sleep(2)

env = dict(os.environ, SCC_DIAG=DIAG)
proc = subprocess.Popen([EXE], env=env)
hwnd, waited = 0, 0
for waited in range(1, 91):
    time.sleep(0.5)
    hwnd = user32.FindWindowW(None, TITLE)
    if hwnd:
        break
print("WINDOW_FOUND", bool(hwnd), "after_s", round(waited * 0.5, 1))
if not hwnd:
    proc.kill()
    sys.exit(1)

info = None
for _ in range(30):
    time.sleep(0.5)
    if os.path.exists(DIAG):
        time.sleep(0.3)
        info = open(DIAG, encoding="utf-8").read()
        break
print("PAGE_DIAG", info)
user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE
for _ in range(30):
    time.sleep(0.5)
    if proc.poll() is not None:
        break
print("EXIT_CODE", proc.poll())
if proc.poll() is None:
    proc.kill()
print("WINDOW_GONE", not user32.FindWindowW(None, TITLE))
ok = bool(info and '"cards":3' in info and '"swatches":5' in info and '"ready":true' in info and '"errs":[]' in info)
print("EXE_TEST", "OK" if ok else "FAIL")

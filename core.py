# -*- coding: utf-8 -*-
"""
智能缓存清理器 - 后端核心（与界面无关）
扫描/分类/回收站操作都在这里，界面层（WebView 或其他）只调用这些函数。

约定来自 safe-dir-cleanup 经验：
- 排除项目/依赖目录；只操作文件，不动源码、依赖、构建产物
- 移入回收站而不是直接删除；分批、逐个验证、有残留立即停止
"""

import ctypes
import os
import time
from ctypes import wintypes

BATCH_SIZE = 10
MAX_ITEMS = 5000

EXCLUDE_DIRS = {
    "node_modules", ".git", ".svn", ".hg",
    "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "build", "dist", "out", "target",
    ".gradle", ".next", ".nuxt", ".vs", ".idea", ".vscode",
    ".venv", "venv", "env", "site-packages",
    ".tox", ".nox", ".terraform", ".serverless",
}

STRONG_EXTS = {
    ".tmp", ".temp", ".bak", ".old", ".cache",
    ".pyc", ".pyo", ".log", ".etl", ".dmp",
}
WEAK_EXTS = {".diag", ".crdownload", ".part", ".partial"}
JUNK_NAMES = {"thumbs.db", ".ds_store", "desktop.ini", "ehthumbs.db", "iconcache.db"}

# 缓存目录名：按路径段精确匹配，避免 "cache-cleaner" 这类工程目录被误判
CACHE_DIR_NAMES = {
    "temp", "tmp", "cache", "caches", "crashdumps", "inetcache",
    "npm-cache", "code cache", "service worker",
}

LEVEL_NAMES = {2: "高", 1: "中", 0: "低"}


def human_size(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "-"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


# ---------------------------------------------------------------------------
# 回收站
# ---------------------------------------------------------------------------
class SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", ctypes.c_uint),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", ctypes.c_ushort),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", ctypes.c_void_p),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


class SHQUERYRBINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_ulonglong),
        ("i64NumItems", ctypes.c_ulonglong),
    ]


FO_DELETE = 3
FFLAGS = 0x0040 | 0x0010 | 0x0004 | 0x0400  # ALLOWUNDO | NOCONFIRMATION | SILENT | NOERRORUI


def recycle_paths(paths):
    """把路径列表移入回收站。返回 (rc, aborted)。rc=2 时文件也可能已进回收站，以 exists 为准。"""
    op = SHFILEOPSTRUCTW()
    op.hwnd = None
    op.wFunc = FO_DELETE
    op.pFrom = "\0".join(paths) + "\0\0"
    op.pTo = None
    op.fFlags = FFLAGS
    op.fAnyOperationsAborted = False
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return rc, bool(op.fAnyOperationsAborted)


def query_recycle_bin(root="C:\\"):
    """查询某个盘回收站的 (项目数, 字节数)，失败返回 (None, None)。回收站按盘隔离。"""
    try:
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        hr = ctypes.windll.shell32.SHQueryRecycleBinW(root, ctypes.byref(info))
        if hr == 0:
            return int(info.i64NumItems), int(info.i64Size)
    except Exception:
        pass
    return None, None


# ---------------------------------------------------------------------------
# 预设位置
# ---------------------------------------------------------------------------
def _env(name, fallback=""):
    return os.environ.get(name, fallback) or fallback


def build_presets():
    local = _env("LOCALAPPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Local"))
    roaming = _env("APPDATA", os.path.join(os.path.expanduser("~"), "AppData", "Roaming"))
    home = os.path.expanduser("~")
    win = _env("WINDIR", "C:\\Windows")
    return [
        {"key": "win_temp",     "label": "用户临时目录",          "hint": "%TEMP%",                                   "path": _env("TEMP", os.path.join(local, "Temp")),                      "on": True,  "risk": 0},
        {"key": "win_temp2",    "label": "系统临时目录",          "hint": "Windows\\Temp",                            "path": os.path.join(win, "Temp"),                                        "on": True,  "risk": 0},
        {"key": "inet_cache",   "label": "IE / Edge 网络缓存",    "hint": "INetCache",                                "path": os.path.join(local, "Microsoft", "Windows", "INetCache"),        "on": True,  "risk": 0},
        {"key": "edge_cache",   "label": "Edge 浏览器缓存",       "hint": "User Data\\Default\\Cache",                "path": os.path.join(local, "Microsoft", "Edge", "User Data", "Default", "Cache"), "on": True, "risk": 0},
        {"key": "chrome_cache", "label": "Chrome 浏览器缓存",     "hint": "User Data\\Default\\Cache",                "path": os.path.join(local, "Google", "Chrome", "User Data", "Default", "Cache"), "on": True, "risk": 0},
        {"key": "crashdumps",   "label": "崩溃转储",              "hint": "CrashDumps",                               "path": os.path.join(local, "CrashDumps"),                               "on": True,  "risk": 0},
        {"key": "pip_cache",    "label": "pip 下载缓存",          "hint": "下次安装时重新下载",                        "path": os.path.join(local, "pip", "Cache"),                             "on": True,  "risk": 0},
        {"key": "npm_cache",    "label": "npm 缓存",              "hint": "下次安装时重新下载",                        "path": os.path.join(local, "npm-cache"),                                "on": True,  "risk": 0},
        {"key": "yarn_cache",   "label": "Yarn 缓存",             "hint": "下次安装时重新下载",                        "path": os.path.join(local, "Yarn", "Cache"),                            "on": False, "risk": 0},
        {"key": "roaming_temp", "label": "Roaming 临时文件",      "hint": "AppData\\Roaming\\Temp",                   "path": os.path.join(roaming, "Temp"),                                   "on": False, "risk": 0},
        {"key": "nuget_cache",  "label": "NuGet 包缓存",          "hint": "重建较慢",                                 "path": os.path.join(home, ".nuget", "packages"),                        "on": False, "risk": 1},
        {"key": "pnpm_store",   "label": "pnpm store",            "hint": "体积大、重建慢，建议只清 30 天以上",       "path": os.path.join(local, "pnpm", "store"),                            "on": False, "risk": 1},
        {"key": "gradle_cache", "label": "Gradle 缓存",           "hint": "重建慢",                                   "path": os.path.join(home, ".gradle", "caches"),                         "on": False, "risk": 1},
    ]


# ---------------------------------------------------------------------------
# 扫描
# ---------------------------------------------------------------------------
def is_cache_dir_path(path):
    segs = [s for s in path.lower().replace("/", "\\").split("\\") if s]
    for i, seg in enumerate(segs):
        if seg in CACHE_DIR_NAMES:
            return True
        nxt = segs[i + 1] if i + 1 < len(segs) else ""
        if seg in ("pip", "npm", "yarn", "pnpm") and nxt in ("cache", "caches"):
            return True
    return False


def classify_file(path, name, root_key, age_days):
    """返回 (类别, 建议等级 0低/1中/2高)；不算缓存返回 None。"""
    lower = name.lower()
    ext = os.path.splitext(lower)[1]
    in_cache_dir = is_cache_dir_path(path)
    in_temp_root = root_key in ("win_temp", "win_temp2", "roaming_temp")

    signals = []
    strong = False
    if ext in STRONG_EXTS:
        signals.append("ext")
        strong = True
    elif ext in WEAK_EXTS:
        signals.append("partial")
    if lower in JUNK_NAMES:
        signals.append("junk")
        strong = True
    elif lower.startswith("_") and ext == ".txt":
        signals.append("cmdout")
    if in_cache_dir or in_temp_root:
        signals.append("cachedir")

    # 必须有实打实的缓存特征；光是"文件很旧"不算
    if not signals:
        return None

    score = 2 if strong else 1
    if "cachedir" in signals:
        score += 1
    if age_days >= 30:
        score += 1
    level = 2 if score >= 3 else (1 if score == 2 else 0)

    if strong:
        category = "临时 / 缓存文件"
    elif "cachedir" in signals:
        category = "缓存目录残留"
    elif "partial" in signals:
        category = "下载残留"
    else:
        category = "命令输出"
    return category, level


def scan_roots(roots, idle_days, stop_event, skip_prefixes=()):
    """生成器。roots: [(key, path)]；逐个 yield 候选文件信息字典。"""
    cutoff = time.time() - idle_days * 86400
    seen = set()
    skip = tuple(s for s in skip_prefixes if s)
    for key, root in roots:
        if stop_event.is_set():
            return
        if not root or not os.path.isdir(root):
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root, topdown=True, onerror=lambda e: None):
                if stop_event.is_set():
                    return
                # 原地剪枝，不进入项目/依赖目录；pnpm/gradle 这类只认强特征
                risk1 = key in ("pnpm_store", "gradle_cache", "nuget_cache")
                dirnames[:] = [
                    d for d in dirnames
                    if d.lower() not in EXCLUDE_DIRS and not (d.startswith(".") and len(d) > 1)
                ]
                for fn in filenames:
                    if stop_event.is_set():
                        return
                    p = os.path.join(dirpath, fn)
                    norm = os.path.normcase(os.path.abspath(p))
                    if norm in seen or norm.startswith(skip):
                        continue
                    seen.add(norm)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    last_active = max(st.st_atime, st.st_mtime)
                    if last_active > cutoff:
                        continue
                    age_days = (time.time() - last_active) / 86400
                    result = classify_file(p, fn, key, age_days)
                    if not result:
                        continue
                    if risk1 and result[1] < 2:
                        continue  # 重建慢的位置只收强特征文件
                    category, level = result
                    yield {
                        "path": p,
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "category": category,
                        "level": level,
                        "root": key,
                    }
        except Exception as exc:  # 扫描不应因为单个目录出错而中断
            yield {"__error__": f"{root}: {exc}"}


def prune_empty_dirs(dirs, keep):
    """删除列表中已经变空的目录（自底向上），不会碰到 keep 里的根目录。返回删掉的目录数。"""
    removed = 0
    keep_norm = {os.path.normcase(os.path.abspath(k)) for k in keep}
    stack = sorted({os.path.normpath(d) for d in dirs if d}, key=lambda s: -len(s))
    seen = set()
    while stack:
        d = stack.pop()
        if d in seen:
            continue
        seen.add(d)
        if os.path.normcase(os.path.abspath(d)) in keep_norm:
            continue
        try:
            if os.path.isdir(d) and not os.listdir(d):
                os.rmdir(d)
                removed += 1
                parent = os.path.dirname(d)
                if parent and parent not in seen:
                    stack.append(parent)
        except OSError:
            pass
    return removed

# 智能缓存清理器

Windows 上的缓存文件清理工具：按闲置天数找出缓存文件，勾选确认后分批移入回收站（可还原），支持自定义背景图片。

- 界面：pywebview (WebView2) + HTML/CSS/JS，毛玻璃、极光背景、自定义图片背景
- 主题：左栏底部可切换 5 套配色（极光、紫罗兰、雾蓝、暖阳、晨曦浅色），选择会被记住
- 后端：Python + ctypes 调用 Windows 回收站接口，每批 10 个并逐个验证
- 安全：排除 `node_modules`、`.git`、`__pycache__` 等项目/依赖目录，只处理文件；恢复时从回收站还原，清空回收站后才会真正释放空间

## 使用

直接运行 `release/智能缓存清理器.exe`（未签名，首次运行可能被 SmartScreen 拦截）。需要 Windows 11 自带的 WebView2 运行时。

1. 左侧勾选要扫描的位置，设置闲置天数（默认 7 天）
2. 点「开始扫描」，结果中默认勾选高、中建议的文件，可逐项调整
3. 点「清理到回收站」，在确认弹窗里再次确认
4. 确认无误后清空回收站以真正释放磁盘空间

设置保存在 `%APPDATA%\SmartCacheCleaner\`，自定义背景图也存在这里。

## 从源码构建

```bash
pip install -r requirements.txt
pyinstaller build.spec
```

产物在 `dist/智能缓存清理器.exe`。直接开发调试可运行 `python app.py`。

## 测试

- `test_ui_v2.py`：启动窗口、真实扫描，并用 WebView2 的 CapturePreview 把各主题下的页面截到 `shots/`（只截应用自身内容，不截屏幕）
- `test_exe.py`：验证打包后的 exe 能加载页面并正常退出。设 `SCC_DIAG=<日志路径>` 可输出页面自检结果

## 图标

`assets/icon.svg` 是图标的矢量稿，`render_icon.py` 用 Pillow 绘制同一设计（不依赖浏览器），输出多尺寸 PNG 和 `assets/icon.ico`（7 个尺寸，16–256 px）。改图标时两处一起改，重跑脚本后再重新打包。页面里用的 `web/icon.png` 也由它生成，需要手动复制过去。

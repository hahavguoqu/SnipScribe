# SnipScribe

Windows 本地截图识别工具：长按右键呼出，框选后识别中文、英文和数学公式。当前窗口名称为 FormulaSnip。

## 功能

- 公式：PP-FormulaNet_plus-S，输出 LaTeX。
- 文字：PP-OCRv5_mobile，识别中文、英文，保留基本换行。
- 文字＋公式：PP-DocLayout_plus-L 定位公式，结合文字与公式识别，按阅读顺序输出 Markdown。小型行内公式可能漏检。
- 截图预览、结果编辑、复制结果、系统托盘。
- CPU 推理，默认 2 个线程；可通过 `FORMULASNIP_THREADS` 环境变量调整。

## 安装（Windows x64）

先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，然后在 PowerShell 中运行：

```powershell
git clone https://github.com/hahavguoqu/SnipScribe.git D:\FormulaSnip
Set-Location D:\FormulaSnip
$env:UV_CACHE_DIR = "$PWD\.uv-cache"
$env:UV_PYTHON_INSTALL_DIR = "$PWD\runtime"
uv sync --frozen
uv run --frozen python download_models.py
```

首次安装需要联网下载 Python、依赖和四个模型。仓库不包含权重或运行环境。
模型下载自 PaddleX 官方 BOS 服务，下载完成后识别在本地运行。
uv 可以安装在 PATH 中，也可以将 `uv.exe` 放入项目的 `tools` 目录。

双击 `Start.vbs` 隐藏控制台启动；也可以运行 `Start.ps1` 或 `uv run --frozen python launch.py`。

## 使用

1. 启动软件后，右键原地按住约 650 毫秒，松开呼出窗口。
2. 选择公式、文字或文字＋公式模式。
3. 点击“截图 / 框选区域”，拖动左键选择内容，松开自动识别。
4. 编辑结果并复制；也可以打开图片、重新识别。

`Ctrl + Alt + L` 呼出；`Ctrl + Alt + Esc` 取消任务。
框选期间按 Esc 或右键取消。长按时间可在界面调整。
右键监听只读取按键状态，不拦截系统鼠标事件；部分应用的原有右键菜单可能同时出现。

关闭窗口收起到托盘，右键监听继续运行。托盘右键菜单只保留“退出软件”。
退出后整个程序结束，需重新启动才能呼出。当前不设置开机自启动。

## 内存与延迟

采用“模型每次用完关闭”：启动、呼出和切换模式不加载模型。
选好截图或图片后才创建独立识别进程，完成、失败、取消或超时后结束该进程及其子进程，释放模型内存。
界面和右键监听常驻，结果保留，可随时复制或修改。

每次识别都有模型加载时间；状态栏耗时只统计推理阶段，不包含加载。
总等待与 CPU、截图、模式和磁盘缓存有关，混合模式需加载多个模型。
单次进程不额外预热，直接识别当前截图。

模型、缓存、运行环境、配置和日志位于项目目录。
截图在内存及 `temp` 临时文件中传递，完成或取消后清理，不上传。
权重、运行环境、配置、日志、截图和临时文件不提交到 Git。

## 验证

Python 命令使用 uv，依赖由 `pyproject.toml` 与 `uv.lock` 管理。

```powershell
uv run --frozen python tests/check_on_demand.py
```

Windows 集成检查使用真实模型，覆盖三个模式、重复识别、进程释放、取消和界面布局。
模型由百度 PaddleOCR / PaddleX 提供，相关使用条件遵循官方说明。
[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) · [PaddleX](https://github.com/PaddlePaddle/PaddleX)

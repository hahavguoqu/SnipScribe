import env
import ctypes
import sys
import json
import logging
import time
import uuid
from PySide6.QtCore import Qt, QTimer, QProcess, QProcessEnvironment, QSize
from PySide6.QtGui import QPixmap, QPainter, QColor, QIcon, QShortcut, QKeySequence
from PySide6.QtWidgets import (QApplication, QWidget, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QPlainTextEdit, QSystemTrayIcon, QMenu, QSlider, QCheckBox,
    QFrame, QButtonGroup, QFileDialog, QSplitter)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from proc_utils import ProcessGuard

LOG = logging.getLogger('formulasnip')
LOG.setLevel(logging.INFO)
handler = logging.FileHandler(env.ROOT / 'logs/app.log', encoding='utf-8')
handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
LOG.addHandler(handler)
MODES = {'formula': ('公式', '框选一个数学公式，转换为可编辑的 LaTeX。'),
         'text': ('文字', '识别中文、英文及混排文字，保留基本换行。'),
         'mixed': ('文字＋公式', '按阅读顺序输出 Markdown。行内小公式可能需要单独框选。')}


class TrayMenu(QMenu):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet('''
            QMenu { background:transparent; border:0; padding:18px 14px; }
            QMenu::item { color:#222938; background:transparent; font:18px "Microsoft YaHei UI";
                          padding:14px 22px; border-radius:9px; min-width:170px; }
            QMenu::item:selected { background:#f0f3fa; }
            QMenu::item:pressed { background:#e8edfa; }
        ''')

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        for inset in range(1, 10):
            painter.setBrush(QColor(30, 40, 65, 2 + inset // 3))
            painter.drawRoundedRect(self.rect().adjusted(inset, inset + 2, -inset, -inset), 16, 16)
        painter.setBrush(QColor('#ffffff'))
        painter.drawRoundedRect(self.rect().adjusted(9, 9, -9, -9), 14, 14)
        painter.end()
        super().paintEvent(event)


class Window(QWidget):
    def __init__(self, start_services=True):
        super().__init__()
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setWindowTitle('FormulaSnip · 截图识别')
        self.resize(1120, 820); self.setMinimumSize(930, 700)
        self.capture = self.engine = self.job = self.current_image = None
        self.capture_guard = self.engine_guard = None
        self.engine_buffer = b''
        self.ready = self.shutting_down = self.pending_capture = False
        self.loaded_modes = set()
        self.queued_job = None
        self.session_active = False
        self.settings_path = env.ROOT / 'data/settings.json'
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            self.settings = {}
        self.mode = self.settings.get('mode', 'formula')
        if self.mode not in MODES: self.mode = 'formula'
        self.setStyleSheet('''
            QWidget { background:#ffffff; color:#202533; font-family:"Microsoft YaHei UI"; font-size:18px; }
            QFrame#sidebar { background:#f6f8fc; border-right:1px solid #e9edf4; }
            QFrame#sidebar QLabel, QFrame#sidebar QCheckBox { background:transparent; }
            QLabel#brand { font-family:"Segoe UI"; font-size:25px; font-weight:700; }
            QLabel#title { font-size:32px; font-weight:700; }
            QLabel#muted { color:#7d8595; font-size:16px; }
            QLabel#section { font-size:19px; font-weight:600; }
            QLabel#duration { color:#5264d8; font-size:16px; font-weight:600; }
            QPushButton { border:1px solid #e2e7f0; border-radius:12px; padding:13px 20px; background:#fff; font-size:18px; }
            QPushButton:hover { background:#f5f7fe; border-color:#c4cdee; }
            QPushButton:focus { border:1px solid #667ff0; }
            QPushButton:disabled { color:#a3aaba; border-color:#edf0f5; background:#f8f9fc; }
            QPushButton#primary { color:white; background:#5264ed; border:1px solid #5264ed; font-weight:600; }
            QPushButton#primary:hover { background:#4053d7; }
            QPushButton#mode { text-align:left; color:#687185; background:transparent; border:1px solid transparent; padding:16px 18px; font-size:20px; }
            QPushButton#mode:hover { background:#edf1fa; }
            QPushButton#mode:checked { background:#e8edff; color:#4659d9; font-weight:600; }
            QPushButton#quiet { color:#798295; border:0; background:transparent; font-size:16px; }
            QPushButton#quiet:hover { background:#edf1fa; }
            QPlainTextEdit { background:#fff; border:1px solid #e3e8f1; border-radius:16px; padding:20px; font-size:22px; selection-background-color:#dce4ff; }
            QPlainTextEdit:focus { border-color:#aebcf8; }
            QSlider::groove:horizontal { height:5px; background:#dfe5f0; border-radius:2px; }
            QSlider::sub-page:horizontal { background:#6677ee; border-radius:2px; }
            QSlider::handle:horizontal { width:16px; height:16px; margin:-6px 0; border:2px solid #5264ed; background:white; border-radius:9px; }
            QSplitter::handle { background:#fff; height:10px; }
            QMenu { background:white; padding:6px; }
            QMenu::item { padding:9px 24px; }
            QMenu::item:selected { background:#e9eefc; }
            QCheckBox { spacing:10px; font-size:17px; }
            QCheckBox::indicator { width:20px; height:20px; border:1px solid #ccd4e3; background:white; border-radius:6px; }
            QCheckBox::indicator:checked { border-color:#5264ed; background:#5264ed; }
        ''')
        check_icon = (env.ROOT / 'assets/check.svg').as_posix()
        self.setStyleSheet(self.styleSheet() + f'QCheckBox::indicator:checked {{ image:url("{check_icon}"); }}')
        outer = QHBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        sidebar = QFrame(); sidebar.setObjectName('sidebar'); sidebar.setFixedWidth(255)
        side = QVBoxLayout(sidebar); side.setContentsMargins(24, 32, 24, 24); side.setSpacing(12)
        brand = QLabel('FormulaSnip'); brand.setObjectName('brand'); side.addWidget(brand)
        side.addSpacing(28)
        self.group = QButtonGroup(self); self.mode_buttons = {}
        for mode, (name, description) in MODES.items():
            button = QPushButton(name); button.setObjectName('mode'); button.setCheckable(True)
            button.setChecked(mode == self.mode); button.setToolTip(description)
            button.clicked.connect(lambda checked=False, mode=mode: self.change_mode(mode))
            self.group.addButton(button); self.mode_buttons[mode] = button; side.addWidget(button)
        side.addStretch()
        self.enabled = QCheckBox('长按右键呼出'); self.enabled.setChecked(self.settings.get('enabled', True)); side.addWidget(self.enabled)
        row = QHBoxLayout(); duration_title = QLabel('长按时间'); duration_title.setObjectName('muted'); row.addWidget(duration_title); row.addStretch()
        self.duration_value = QLabel(); self.duration_value.setObjectName('duration'); row.addWidget(self.duration_value); side.addLayout(row)
        self.hold = QSlider(Qt.Horizontal); self.hold.setRange(400, 2000); self.hold.setSingleStep(50); self.hold.setPageStep(100)
        self.hold.setValue(self.settings.get('hold_ms', 650)); self.hold.setFixedHeight(30)
        self.hold.setAccessibleName('长按时间，单位毫秒'); side.addWidget(self.hold)
        self.duration_value.setText(f'{self.hold.value()} 毫秒')
        self.hold.valueChanged.connect(lambda value: self.duration_value.setText(f'{value} 毫秒'))
        release_tip = QLabel('按住后松开，即可呼出'); release_tip.setObjectName('muted'); side.addWidget(release_tip); side.addSpacing(14)
        shortcut = QLabel('Ctrl + Alt + L  呼出\nCtrl + Alt + Esc  取消'); shortcut.setObjectName('muted'); side.addWidget(shortcut); side.addSpacing(14)
        hide = QPushButton('收起到托盘'); hide.clicked.connect(self.suspend_panel); side.addWidget(hide)
        exit_button = QPushButton('退出软件'); exit_button.setObjectName('quiet'); exit_button.clicked.connect(self.quit); side.addWidget(exit_button)
        outer.addWidget(sidebar)
        main = QVBoxLayout(); main.setContentsMargins(36, 32, 36, 26); main.setSpacing(18); outer.addLayout(main, 1)
        title_row = QHBoxLayout(); self.title = QLabel(); self.title.setObjectName('title'); title_row.addWidget(self.title); title_row.addStretch()
        main.addLayout(title_row)
        self.description = QLabel(); self.description.setObjectName('muted'); self.description.setWordWrap(True); main.addWidget(self.description)
        actions = QHBoxLayout()
        self.snip = QPushButton('截图 / 框选区域'); self.snip.setObjectName('primary'); self.snip.clicked.connect(self.begin_capture); actions.addWidget(self.snip)
        self.open_image = QPushButton('打开图片'); self.open_image.clicked.connect(self.choose_image); actions.addWidget(self.open_image)
        self.cancel = QPushButton('取消'); self.cancel.clicked.connect(lambda: self.cancel_work()); self.cancel.setVisible(False); actions.addWidget(self.cancel)
        actions.addStretch(); main.addLayout(actions)
        split = QSplitter(Qt.Vertical)
        preview_container = QWidget(); p_layout = QVBoxLayout(preview_container); p_layout.setContentsMargins(0, 0, 0, 0)
        header = QLabel('截图预览'); header.setObjectName('section'); p_layout.addWidget(header)
        self.preview = QLabel('框选需要识别的内容，或打开一张图片'); self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(130); self.preview.setStyleSheet('background:#f7f9fc;border:1px solid #eef1f6;border-radius:16px;color:#919aab;font-size:18px;')
        p_layout.addWidget(self.preview); split.addWidget(preview_container)
        results = QWidget(); r_layout = QVBoxLayout(results); r_layout.setContentsMargins(0, 0, 0, 0)
        row = QHBoxLayout(); self.result_label = QLabel(); self.result_label.setObjectName('section'); row.addWidget(self.result_label); row.addStretch()
        self.retry = QPushButton('重新识别'); self.retry.clicked.connect(self.recognize_current); row.addWidget(self.retry)
        self.copy = QPushButton('复制结果'); self.copy.setObjectName('primary'); self.copy.clicked.connect(self.copy_result); self.copy.setEnabled(False); row.addWidget(self.copy)
        r_layout.addLayout(row)
        self.output = QPlainTextEdit(); self.output.setPlaceholderText('识别结果会显示在这里。可以直接修改，再复制使用。'); r_layout.addWidget(self.output)
        split.addWidget(results); split.setSizes([200, 330]); main.addWidget(split, 1)
        self.status = QLabel('呼出后加载模型，关闭窗口后释放。'); self.status.setObjectName('muted'); self.status.setWordWrap(True); main.addWidget(self.status)
        self.enabled.toggled.connect(self.save_settings); self.hold.valueChanged.connect(self.save_settings)
        self.output.textChanged.connect(lambda: self.copy.setEnabled(bool(self.output.toPlainText().strip())))
        icon = QPixmap(64, 64); icon.fill(QColor('#4169e1')); painter = QPainter(icon); painter.setPen(Qt.white)
        font = painter.font(); font.setPixelSize(42); painter.setFont(font); painter.drawText(icon.rect(), Qt.AlignCenter, 'Σ'); painter.end()
        self.setWindowIcon(QIcon(icon)); self.tray = QSystemTrayIcon(QIcon(icon), self); self.tray.setToolTip('FormulaSnip · 截图识别')
        self.menu = TrayMenu(self); self.menu.addAction('退出软件', self.quit)
        self.tray.setContextMenu(self.menu); self.tray.activated.connect(lambda reason: self.show_panel() if reason == QSystemTrayIcon.Trigger else None); self.tray.show()
        self.key_state = ctypes.windll.user32.GetAsyncKeyState
        self.key_state.argtypes = [ctypes.c_int]; self.key_state.restype = ctypes.c_short
        self.right_started = None; self.right_origin = None; self.right_moved = False
        self.hotkey_previous = self.emergency_previous = False
        self.poll = QTimer(self); self.poll.timeout.connect(self.poll_keys); self.poll.start(40)
        self.watchdog = QTimer(self); self.watchdog.setSingleShot(True); self.watchdog.timeout.connect(self.job_timeout)
        self.capture_timeout = QTimer(self); self.capture_timeout.setSingleShot(True); self.capture_timeout.timeout.connect(self.cancel_work)
        self.esc = QShortcut(QKeySequence('Esc'), self); self.esc.activated.connect(self.cancel_work)
        self.change_mode(self.mode)
        self.update_actions()

    def child(self, script, args=()):
        process = QProcess(self); process.setWorkingDirectory(str(env.ROOT))
        process.setProcessEnvironment(QProcessEnvironment.systemEnvironment())
        process.setProgram(env.UV)
        process.setArguments(['run', '--frozen', '--no-sync', 'python', '-u', script, *args])
        return process

    def start_engine(self):
        if self.shutting_down or self.engine is not None: return
        self.engine_buffer = b''; self.ready = False; self.loaded_modes.clear()
        process = self.child('engine.py'); self.engine = process
        guard = ProcessGuard(); self.engine_guard = guard
        process.started.connect(lambda: guard.attach(int(process.processId())))
        process.readyReadStandardOutput.connect(lambda: self.read_engine(process))
        process.readyReadStandardError.connect(lambda: self.log_stderr(process, 'engine'))
        process.finished.connect(lambda code, status: self.engine_finished(process, guard, code))
        process.errorOccurred.connect(lambda error: self.process_error(process, '识别服务'))
        process.start(); self.update_actions()

    def log_stderr(self, process, name):
        data = bytes(process.readAllStandardError()).decode('utf-8', errors='replace')
        if data.strip(): LOG.info('%s: %s', name, data.strip())

    def process_error(self, process, name):
        LOG.error('%s: %s', name, process.errorString()); self.status.setText(name + '启动失败：' + process.errorString())
        if process is self.capture: self.finish_capture(process)
        elif process is self.engine:
            self.stop_engine()

    def read_engine(self, process):
        if process is not self.engine:
            process.readAllStandardOutput(); return
        self.engine_buffer += bytes(process.readAllStandardOutput())
        while b'\n' in self.engine_buffer:
            line, self.engine_buffer = self.engine_buffer.split(b'\n', 1)
            try: data = json.loads(line.decode('utf-8'))
            except (ValueError, UnicodeError):
                LOG.warning('Non-JSON engine output: %r', line[:300]); continue
            kind = data.get('type')
            if kind == 'ready':
                self.ready = True
                if self.queued_job:
                    payload = self.queued_job; self.queued_job = None; self.send(payload)
                else:
                    self.load_mode()
                continue
            if not self.job or data.get('id') != self.job['id']: continue
            if kind == 'progress': self.status.setText(data['message'])
            elif kind == 'loaded':
                self.loaded_modes.update(MODES if data.get('mode') == 'mixed' else [data.get('mode')])
                self.complete_job(); self.status.setText('已就绪。点击“截图 / 框选区域”开始。')
                if self.mode != data.get('mode'): self.load_mode()
            elif kind == 'result':
                self.output.setPlainText(data['text'])
                message = f'识别完成，用时 {data["seconds"]:.3f} 秒。' + data.get('warning', '')
                self.status.setText(message if data['text'] else '没有识别到内容，请检查截图范围。')
                self.complete_job(); LOG.info('Result: mode=%s seconds=%.3f items=%s', self.mode, data['seconds'], len(data['items']))
            elif kind == 'error':
                self.complete_job(); self.status.setText('识别失败：' + data['message']); LOG.error('Engine error: %s', data['message'])
                self.stop_engine()

    def send(self, payload):
        payload['id'] = uuid.uuid4().hex; self.job = payload
        self.engine.write((json.dumps(payload) + '\n').encode('utf-8'))
        self.watchdog.start(90000 if payload['action'] == 'load' else 60000); self.update_actions()

    def load_mode(self):
        if self.session_active and self.ready and not self.job and self.mode not in self.loaded_modes:
            self.status.setText('正在加载' + MODES[self.mode][0] + '模型…')
            self.send({'action': 'load', 'mode': self.mode})
        self.update_actions()

    def stop_engine(self):
        process, guard = self.engine, self.engine_guard
        self.engine = self.engine_guard = None
        self.ready = False; self.loaded_modes.clear()
        if self.queued_job and self.queued_job.get('file'):
            (env.ROOT / 'temp' / self.queued_job['file']).unlink(missing_ok=True)
        self.queued_job = None
        if guard: guard.close()
        if process: process.kill()
        self.complete_job()

    def engine_finished(self, process, guard, code):
        guard.close()
        if process is self.engine:
            self.stop_engine()
            if not self.shutting_down:
                self.status.setText('识别服务意外停止，可以重新识别。')
        process.deleteLater()

    def complete_job(self):
        self.watchdog.stop()
        if self.job and self.job.get('file'): (env.ROOT / 'temp' / self.job['file']).unlink(missing_ok=True)
        self.job = None; self.update_actions()

    def job_timeout(self):
        self.cancel_work(show=False); self.stop_engine(); self.show_panel(load=False)
        self.status.setText('处理超时，已取消并释放模型。重新呼出可加载模型，也可打开图片重试。')

    def change_mode(self, mode):
        self.mode = mode; self.mode_buttons[mode].setChecked(True)
        title, subtitle = MODES[mode]; self.title.setText(title + '识别'); self.description.setText(subtitle)
        self.result_label.setText({'formula': 'LaTeX 结果', 'text': '文字结果', 'mixed': 'Markdown 结果'}[mode])
        self.save_settings(); self.load_mode(); self.update_actions()

    def save_settings(self, *_):
        self.settings = {'hold_ms': self.hold.value(), 'enabled': self.enabled.isChecked(), 'mode': self.mode}
        self.settings_path.write_text(json.dumps(self.settings, ensure_ascii=False), encoding='utf-8')

    def update_actions(self):
        busy = bool(self.job or self.queued_job) or (self.engine is not None and not self.ready) or self.capture is not None or self.pending_capture
        self.snip.setEnabled(self.ready and not busy); self.open_image.setEnabled(not busy)
        self.retry.setEnabled(not busy and self.current_image is not None); self.cancel.setVisible(busy)
        for button in self.mode_buttons.values(): button.setEnabled(not busy)

    def poll_keys(self):
        # Read state only. Never intercept or suppress OS input events.
        down = lambda code: bool(self.key_state(code) & 0x8000)
        emergency = down(0x11) and down(0x12) and down(0x1B)
        if emergency and not self.emergency_previous: self.cancel_work(); self.show_panel()
        self.emergency_previous = emergency
        hotkey = down(0x11) and down(0x12) and down(0x4C)
        if hotkey and not self.hotkey_previous: self.show_panel()
        self.hotkey_previous = hotkey
        right = down(0x02)
        class Point(ctypes.Structure): _fields_ = [('x', ctypes.c_long), ('y', ctypes.c_long)]
        point = Point(); ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
        if right and self.right_started is None:
            self.right_started = time.monotonic(); self.right_origin = (point.x, point.y); self.right_moved = False
        elif right:
            if abs(point.x - self.right_origin[0]) > 12 or abs(point.y - self.right_origin[1]) > 12: self.right_moved = True
        elif self.right_started is not None:
            elapsed = time.monotonic() - self.right_started; self.right_started = None
            if self.settings['enabled'] and not self.right_moved and elapsed >= self.settings['hold_ms'] / 1000 and self.capture is None and not self.pending_capture:
                QTimer.singleShot(60, self.show_panel)

    def show_panel(self, load=True):
        if self.capture is not None or self.pending_capture or self.shutting_down: return
        self.session_active = True
        self.showNormal(); self.raise_(); self.activateWindow()
        if load:
            if self.engine is None:
                self.status.setText('正在启动识别服务并加载模型…')
                self.watchdog.start(90000); self.start_engine()
            else:
                self.load_mode()

    def suspend_panel(self):
        self.session_active = False
        self.cancel_work(show=False)
        self.stop_engine()
        self.hide()
        self.status.setText('模型已释放。再次呼出时重新加载。')

    def begin_capture(self):
        if self.job or self.queued_job or self.capture is not None or self.pending_capture or not self.ready: return
        self.pending_capture = True; self.update_actions(); self.hide(); QTimer.singleShot(300, self.open_capture)

    def open_capture(self):
        if not self.pending_capture or self.shutting_down: return
        self.pending_capture = False; self.capture_file = 'capture-' + uuid.uuid4().hex + '.png'
        process = self.child('capture.py', [self.capture_file]); self.capture = process
        guard = ProcessGuard(); self.capture_guard = guard
        process.started.connect(lambda: guard.attach(int(process.processId())))
        process.readyReadStandardError.connect(lambda: self.log_stderr(process, 'capture'))
        process.finished.connect(lambda code, status: self.finish_capture(process, code))
        process.errorOccurred.connect(lambda error: self.process_error(process, '截图窗口'))
        self.capture_timeout.start(48000); process.start(); self.update_actions()

    def finish_capture(self, process, code=1):
        if process is not self.capture: return
        self.capture_timeout.stop(); self.capture_guard.close(); self.capture_guard = None
        self.capture = None; process.deleteLater(); self.update_actions(); self.show_panel()
        path = env.ROOT / 'temp' / self.capture_file
        if code == 0 and path.is_file():
            pixmap = QPixmap(str(path)); path.unlink(missing_ok=True)
            if not pixmap.isNull(): self.set_image(pixmap); return
        path.unlink(missing_ok=True)
        self.status.setText('截图已取消。' if code == 0 else '截图未完成，已释放桌面。请重试。')

    def choose_image(self):
        path, _ = QFileDialog.getOpenFileName(self, '打开图片', str(env.ROOT / 'data'), '图片 (*.png *.jpg *.jpeg *.bmp *.webp)')
        if path:
            pixmap = QPixmap(path)
            if pixmap.isNull(): self.status.setText('无法读取该图片，请换一张图片。')
            else: self.set_image(pixmap)

    def set_image(self, pixmap):
        self.current_image = pixmap; self.refresh_preview(); self.recognize_current()

    def refresh_preview(self):
        if self.current_image is not None:
            self.preview.setPixmap(self.current_image.scaled(max(1, self.preview.width() - 20), max(1, self.preview.height() - 20), Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'preview'): self.refresh_preview()

    def recognize_current(self):
        if self.current_image is None or self.job or self.queued_job: return
        filename = 'job-' + uuid.uuid4().hex + '.png'
        if not self.current_image.save(str(env.ROOT / 'temp' / filename), 'PNG'):
            self.status.setText('无法创建临时截图，请检查 D 盘剩余空间。'); return
        payload = {'action': 'recognize', 'mode': self.mode, 'file': filename}
        if self.ready:
            self.status.setText('正在识别…'); self.send(payload)
        else:
            self.status.setText('正在启动识别并加载模型…')
            self.queued_job = payload
            self.watchdog.start(90000); self.start_engine()

    def cancel_work(self, show=True):
        self.pending_capture = False; self.capture_timeout.stop()
        if self.capture is not None:
            process = self.capture; self.capture = None
            if self.capture_guard: self.capture_guard.close(); self.capture_guard = None
            process.kill(); (env.ROOT / 'temp' / self.capture_file).unlink(missing_ok=True)
        if self.job or self.queued_job or (self.engine is not None and not self.ready):
            self.stop_engine()
        self.complete_job()
        if show: self.show_panel()
        if not self.job: self.status.setText('已取消，可以重新截图。')

    def copy_result(self):
        QApplication.clipboard().setText(self.output.toPlainText()); self.status.setText('结果已复制到剪贴板。')

    def closeEvent(self, event):
        if self.shutting_down: event.accept()
        else: event.ignore(); self.suspend_panel()

    def quit(self):
        self.shutting_down = True; self.poll.stop(); self.cancel_work(show=False)
        if self.engine_guard: self.engine_guard.close(); self.engine_guard = None
        if self.engine: self.engine.kill()
        self.tray.hide(); QApplication.quit()


def main():
    app = QApplication(sys.argv); app.setQuitOnLastWindowClosed(False)
    socket = QLocalSocket(); socket.connectToServer('FormulaSnip-local-v2')
    background = '--background' in sys.argv
    if socket.waitForConnected(400):
        if not background: socket.write(b'show'); socket.waitForBytesWritten(400)
        return
    QLocalServer.removeServer('FormulaSnip-local-v2')
    server = QLocalServer(); server.listen('FormulaSnip-local-v2')
    window = Window()
    def incoming():
        connection = server.nextPendingConnection()
        if connection:
            connection.waitForReadyRead(400)
            if bytes(connection.readAll()) == b'show': window.show_panel()
            connection.disconnectFromServer(); connection.deleteLater()
    server.newConnection.connect(incoming)
    app.aboutToQuit.connect(lambda: window.engine_guard.close() if window.engine_guard else None)
    if not background: window.show_panel()
    sys.exit(app.exec())


if __name__ == '__main__': main()

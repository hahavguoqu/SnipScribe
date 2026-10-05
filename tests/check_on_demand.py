"""Windows integration checks for models retained until the panel closes."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import env
from app import Window
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QPainter, QFont, QFontDatabase

app = QApplication([])
for filename in ('msyh.ttc', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + filename)
settings_path = env.ROOT / 'data/settings.json'
settings = settings_path.read_bytes() if settings_path.exists() else None
window = Window()
window.poll.stop()

def pump_until(predicate, timeout=120):
    deadline = time.monotonic() + timeout
    while not predicate():
        app.processEvents()
        if time.monotonic() > deadline:
            raise AssertionError('Timed out: ' + window.status.text())
        time.sleep(.01)
    app.processEvents()

def sample(text):
    image = QPixmap(900, 140); image.fill('white')
    painter = QPainter(image); painter.setPen('black')
    painter.setFont(QFont('Microsoft YaHei UI', 26))
    painter.drawText(25, 80, text); painter.end()
    return image

try:
    app.processEvents()
    assert window.engine is None and not window.session_active
    assert window.windowFlags() & Qt.WindowStaysOnTopHint
    labels = [item.text() for item in window.findChildren(QLabel)]
    assert '截取内容，即刻编辑' not in labels and '完全本地' not in labels
    window.change_mode('formula')
    window.show_panel()
    process = window.engine
    finished = []
    process.finished.connect(lambda *_: finished.append(True))
    pump_until(lambda: window.ready and window.job is None)
    assert 'formula' in window.loaded_modes
    for mode, text in [('formula', 'y = 2'), ('formula', 'y = 3'),
                       ('text', '中文文字 English 123'), ('mixed', '中文文字 English 123')]:
        window.change_mode(mode)
        pump_until(lambda: window.ready and window.job is None)
        started = time.monotonic()
        window.set_image(sample(text))
        pump_until(lambda: window.job is None)
        assert window.engine is process and not finished
        assert window.output.toPlainText().strip(), window.status.text()
        assert window.snip.isEnabled() and window.retry.isEnabled()
        print(mode, round(time.monotonic() - started, 2), window.output.toPlainText(), flush=True)
    # Temporarily hiding for capture must retain the model, including cancellation.
    window.begin_capture()
    assert window.pending_capture and window.engine is process
    window.cancel_work()
    assert window.engine is process and not window.pending_capture
    window.close()
    pump_until(lambda: bool(finished))
    assert window.engine is None and not window.session_active and not window.isVisible()
    assert window.output.toPlainText().strip()
    window.change_mode('formula')
    window.show_panel()
    assert window.engine is not None and window.engine is not process
    # Close during model startup/loading; no automatic restart afterward.
    window.suspend_panel()
    pump_until(lambda: window.engine is None)
    assert not window.session_active
    window.show_panel()
    pump_until(lambda: window.ready and window.job is None)
    # Service errors release the model and clean the screenshot.
    bad = env.ROOT / 'temp/job-test-invalid.png'
    bad.write_bytes(b'invalid image')
    window.send({'action': 'recognize', 'mode': 'formula', 'file': bad.name})
    pump_until(lambda: window.engine is None)
    assert '识别失败' in window.status.text() and not bad.exists()
    window.suspend_panel()
    for width, height in [(930, 700), (1120, 820), (1500, 960)]:
        window.resize(width, height); window.show(); app.processEvents()
        assert window.duration_value.width() >= window.duration_value.fontMetrics().horizontalAdvance(window.duration_value.text())
    window.grab().save(str(env.ROOT / 'work/ui-session.png'))
    print('PASS: topmost; background idle; preload; all modes; retained process; close releases; reopen; cancel; errors; layout')
finally:
    window.quit()
    if settings is None: settings_path.unlink(missing_ok=True)
    else: settings_path.write_bytes(settings)

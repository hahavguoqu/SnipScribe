"""Windows integration check with real model subprocesses; run through uv."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import env
from app import Window
from PySide6.QtWidgets import QApplication, QLabel
from PySide6.QtGui import QPixmap, QPainter, QFont, QFontDatabase

app = QApplication([])
for filename in ('msyh.ttc', 'segoeui.ttf'):
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/' + filename)
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
    pump_until(lambda: window.snip.isEnabled())
    assert window.engine is None
    labels = [item.text() for item in window.findChildren(QLabel)]
    assert '截取内容，即刻编辑' not in labels and '完全本地' not in labels
    for mode, text in [('formula', 'x = 1'), ('formula', 'y = 2'),
                       ('text', '中文文字 English 123'), ('mixed', '中文文字 English 123')]:
        window.change_mode(mode)
        assert window.engine is None
        window.output.clear()
        started = time.monotonic()
        window.set_image(sample(text))
        process = window.engine
        assert process is not None
        finished = []
        process.finished.connect(lambda *_: finished.append(True))
        pump_until(lambda: window.engine is None and window.job is None and window.queued_job is None)
        pump_until(lambda: bool(finished))
        assert window.output.toPlainText().strip(), window.status.text()
        assert window.snip.isEnabled() and window.retry.isEnabled()
        print(mode, round(time.monotonic() - started, 2), window.output.toPlainText(), flush=True)
    window.recognize_current()
    window.cancel_work()
    assert window.engine is None and window.job is None and window.queued_job is None
    assert window.snip.isEnabled()
    # Cancellation after ready, while a real model is loading.
    window.change_mode('formula'); window.recognize_current()
    pump_until(lambda: window.job is not None)
    window.cancel_work()
    assert window.engine is None and window.snip.isEnabled()
    # Malformed image exercises the real service's error response and release.
    bad = env.ROOT / 'temp' / 'job-test-invalid.png'
    bad.write_bytes(b'invalid image')
    window.queued_job = {'action': 'recognize', 'mode': 'formula', 'file': bad.name}
    window.start_engine()
    pump_until(lambda: window.engine is None and window.queued_job is None)
    assert '识别失败' in window.status.text() and not bad.exists()
    window.begin_capture(); window.cancel_work()
    assert not window.pending_capture and window.capture is None and window.snip.isEnabled()
    for width, height in [(930, 700), (1120, 820), (1500, 960)]:
        window.resize(width, height); window.show(); app.processEvents()
        assert window.duration_value.width() >= window.duration_value.fontMetrics().horizontalAdvance(window.duration_value.text())
    window.resize(1120, 820); app.processEvents()
    window.grab().save(str(env.ROOT / 'work/ui-on-demand.png'))
    print('PASS: no startup model; all modes; repeated cold recognition; release; cancellation; layout')
finally:
    window.quit()

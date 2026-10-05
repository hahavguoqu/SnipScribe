"""Short-lived screenshot selector. Always releases the desktop on exit/timeout."""
import env
import sys
import json
from PySide6.QtCore import Qt, QRect, QTimer
from PySide6.QtGui import QPainter, QColor, QPen, QFont
from PySide6.QtWidgets import QApplication, QWidget, QPushButton


class Overlay(QWidget):
    def __init__(self, screen, finish):
        super().__init__()
        self.finish = finish
        self.background = screen.grabWindow(0)
        if self.background.isNull():
            raise RuntimeError('屏幕截图失败，请退出独占全屏后重试。')
        self.ratio = self.background.devicePixelRatio()
        self.setWindowTitle('FormulaSnip 截图框选')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Window)
        self.setGeometry(screen.geometry())
        self.setCursor(Qt.CrossCursor)
        self.start = None
        self.end = None
        self.done = False
        cancel = QPushButton('取消截图  Esc', self)
        cancel.setGeometry(max(10, self.width() - 230), 18, 210, 52)
        cancel.setStyleSheet('background:white;color:#1e293b;border:1px solid #cbd5e1;border-radius:8px;font:18px "Microsoft YaHei UI";')
        cancel.clicked.connect(lambda: self.complete(None))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(0, 0, self.background)
        painter.fillRect(self.rect(), QColor(15, 23, 42, 85))
        if self.start is not None and self.end is not None:
            rect = QRect(self.start, self.end).normalized().intersected(self.rect())
            physical = QRect(round(rect.x() * self.ratio), round(rect.y() * self.ratio),
                             round(rect.width() * self.ratio), round(rect.height() * self.ratio))
            painter.drawPixmap(rect, self.background, physical)
            painter.setPen(QPen(QColor('#4169e1'), 2))
            painter.drawRect(rect)
        painter.setFont(QFont('Microsoft YaHei UI', 13))
        painter.setPen(Qt.white)
        painter.drawText(24, 48, '拖动左键框选，松开后识别。Esc / 右键取消，45 秒后自动退出。')

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            self.complete(None)
        elif event.button() == Qt.LeftButton:
            self.start = event.position().toPoint()
            self.end = self.start
            self.update()

    def mouseMoveEvent(self, event):
        if self.start is not None:
            self.end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.start is not None:
            rect = QRect(self.start, event.position().toPoint()).normalized().intersected(self.rect())
            if rect.width() < 8 or rect.height() < 8:
                self.complete(None)
                return
            physical = QRect(round(rect.x() * self.ratio), round(rect.y() * self.ratio),
                             round(rect.width() * self.ratio), round(rect.height() * self.ratio))
            self.complete(self.background.copy(physical))

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.complete(None)

    def closeEvent(self, event):
        self.complete(None)
        event.accept()

    def complete(self, pixmap):
        if self.done:
            return
        self.done = True
        self.hide()
        self.releaseMouse()
        self.releaseKeyboard()
        self.finish(pixmap)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    output = env.ROOT / 'temp' / sys.argv[1]
    if output.resolve().parent != (env.ROOT / 'temp').resolve():
        raise ValueError('Invalid output path')
    overlays = []
    finished = False
    def finish(pixmap):
        nonlocal finished
        if finished:
            return
        finished = True
        for overlay in overlays:
            overlay.hide()
            overlay.releaseMouse()
            overlay.releaseKeyboard()
        if pixmap is not None:
            if not pixmap.save(str(output), 'PNG'):
                print(json.dumps({'error': '无法保存临时截图'}), flush=True)
            else:
                print(json.dumps({'file': output.name}), flush=True)
        else:
            print(json.dumps({'canceled': True}), flush=True)
        app.quit()
    # Grab all screens before showing any overlay so one overlay never contaminates another.
    overlays = [Overlay(screen, finish) for screen in app.screens()]
    for overlay in overlays:
        overlay.show()
    active = app.screenAt(__import__('PySide6.QtGui', fromlist=['QCursor']).QCursor.pos())
    target = next((o for o in overlays if o.geometry() == active.geometry()), overlays[0]) if active else overlays[0]
    target.activateWindow()
    target.setFocus()
    QTimer.singleShot(45000, lambda: finish(None))
    sys.exit(app.exec())


if __name__ == '__main__':
    main()

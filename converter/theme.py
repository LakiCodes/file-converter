from functools import lru_cache

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


INK = "#1d2538"
MUTED = "#5f6b81"
ACCENT = "#5056c8"


@lru_cache(maxsize=96)
def icon(name, color=ACCENT, size=20):
    image = QPixmap(size * 2, size * 2)
    image.fill(Qt.GlobalColor.transparent)
    image.setDevicePixelRatio(2)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24, size / 24)
    pen = QPen(QColor(color))
    pen.setWidthF(1.65)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)

    def line(*points):
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(*point)
        p.drawPath(path)

    if name == "brand":
        line((4, 8), (20, 8), (16, 4))
        line((20, 8), (16, 12))
        line((20, 16), (4, 16), (8, 12))
        line((4, 16), (8, 20))
    elif name in {"file", "text", "edit"}:
        line((6, 3), (14, 3), (19, 8), (19, 21), (5, 21), (5, 4), (6, 3))
        line((13, 3), (13, 9), (19, 9))
        if name != "file":
            line((8, 13), (16, 13))
            line((8, 16.5), (15, 16.5))
    elif name == "image":
        p.drawRoundedRect(QRectF(3, 4, 18, 16), 2, 2)
        p.drawEllipse(QRectF(7, 7, 3.5, 3.5))
        line((4, 17), (9, 13), (12, 15), (16.5, 10.5), (21, 15))
    elif name in {"merge", "split"}:
        p.drawRoundedRect(QRectF(2.5, 4.5, 6, 5), 1, 1)
        p.drawRoundedRect(QRectF(2.5, 14.5, 6, 5), 1, 1)
        p.drawRoundedRect(QRectF(16, 8.5, 5.5, 7), 1, 1)
        line((8.5, 7), (12, 7), (12, 17), (8.5, 17))
        line((12, 12), (16, 12))
    elif name == "trash":
        line((4, 6), (20, 6))
        line((9, 6), (9, 3), (15, 3), (15, 6))
        line((6, 6), (7.5, 21), (16.5, 21), (18, 6))
        line((10, 10), (10.5, 17))
        line((14, 10), (13.5, 17))
    elif name == "rotate":
        p.drawArc(QRectF(5, 5, 15, 15), 215 * 16, 290 * 16)
        line((4, 5), (4, 10), (9, 10))
    elif name in {"resize", "compress"}:
        p.drawRoundedRect(QRectF(4, 4, 16, 16), 2, 2)
        line((8, 16), (15, 9))
        line((11, 9), (15, 9), (15, 13))
        line((8, 12), (8, 16), (12, 16))
    elif name == "layers":
        line((3, 8), (12, 3), (21, 8), (12, 13), (3, 8))
        line((3, 12), (12, 17), (21, 12))
        line((3, 16), (12, 21), (21, 16))
    elif name in {"lock", "unlock"}:
        p.drawRoundedRect(QRectF(5, 11, 14, 10), 2, 2)
        if name == "lock":
            p.drawArc(QRectF(8, 3, 8, 12), 0, 180 * 16)
            line((8, 9), (8, 11))
            line((16, 9), (16, 11))
        else:
            p.drawArc(QRectF(8, 2, 8, 10), 0, 180 * 16)
            line((8, 7), (8, 11))
        line((12, 15), (12, 17))
    elif name == "add":
        line((5, 12), (19, 12))
        line((12, 5), (12, 19))
    elif name in {"up", "down"}:
        y1, y2 = (14.5, 9) if name == "up" else (9, 14.5)
        line((6, y1), (12, y2), (18, y1))
    elif name == "close":
        line((7, 7), (17, 17))
        line((17, 7), (7, 17))
    elif name == "check":
        line((4, 12), (9, 17), (20, 6))
    elif name == "arrow":
        line((4, 12), (19, 12))
        line((14, 7), (19, 12), (14, 17))
    elif name == "upload":
        line((5, 14), (5, 20), (19, 20), (19, 14))
        line((12, 15), (12, 4))
        line((7, 9), (12, 4), (17, 9))
    elif name == "folder":
        line((3, 6), (9, 6), (12, 9), (21, 9), (21, 19), (3, 19), (3, 6))
    elif name == "search":
        p.drawEllipse(QRectF(4, 4, 12, 12))
        line((14.5, 14.5), (20, 20))
    elif name == "warning":
        line((12, 3), (22, 20), (2, 20), (12, 3))
        line((12, 9), (12, 13))
        line((12, 16), (12, 16.2))
    p.end()
    return QIcon(image)


STYLE = """
QWidget { color: #1d2538; font-family: 'Segoe UI'; font-size: 13px; }
QMainWindow, QWidget#root { background: #f5f6fb; }
QWidget#topbar { background: #ffffff; border-bottom: 1px solid #e4e7f0; }
QWidget#canvas, QWidget#transparent, QScrollArea { background: transparent; border: 0; }
QScrollArea > QWidget > QWidget { background: transparent; }
QLabel#brandMark { background: #5056c8; border-radius: 11px; }
QLabel#brandTitle { font-size: 19px; font-weight: 750; }
QLabel#muted, QLabel#hint { color: #5f6b81; }
QLabel#hint { font-size: 12px; }
QLabel#badge { background: #eeeffb; color: #474db9; padding: 3px 8px; border-radius: 7px; font-weight: 700; font-size: 11px; }
QLabel#title { font-size: 29px; font-weight: 750; }
QLabel#subheading { font-size: 18px; font-weight: 700; }
QLabel#groupHeading { color: #525d76; font-size: 12px; font-weight: 700; }
QLabel#fieldLabel { font-size: 12px; font-weight: 650; }
QLabel#selectedTitle { font-size: 20px; font-weight: 750; }
QLabel#selectedIcon, QLabel#emptyIcon { background: #eeeffb; border-radius: 12px; }
QLabel#success { color: #087356; font-weight: 700; }
QLabel#warning { color: #925410; font-weight: 700; }
QFrame#drop { background: #fcfcff; border: 1px dashed #a2a9d8; border-radius: 17px; }
QFrame#drop[active="true"] { background: #ebeefe; border: 2px dashed #575dce; }
QFrame#side, QFrame#surface { background: #ffffff; border: 1px solid #e1e5f0; border-radius: 16px; }
QFrame#result { background: #f3f7f8; border: 1px solid #e3ebee; border-radius: 11px; }
QFrame[frameShape="4"] { color: #e6e9f1; border: 0; background: #e6e9f1; max-height: 1px; }
QPushButton { background: #ffffff; border: 1px solid #dfe3ef; border-radius: 9px; font-weight: 650; padding: 8px 12px; }
QPushButton:hover { background: #f2f3fd; border-color: #bbc0ed; }
QPushButton:focus-visible { border: 2px solid #686de0; }
QPushButton:disabled { color: #8a93a8; background: #f4f5f9; border-color: #e6e9f0; }
QPushButton#primary { background: #5056c8; border-color: #5056c8; color: white; min-height: 24px; }
QPushButton#primary:hover { background: #434ab9; border-color: #434ab9; }
QPushButton#primary:disabled { color: #fbfbfe; background: #9397c3; border-color: #9397c3; }
QPushButton#ghost, QPushButton#rowButton { background: transparent; border: 1px solid transparent; }
QPushButton#ghost:hover, QPushButton#rowButton:hover { background: #eef0fc; border-color: #e3e6fa; }
QPushButton#ghost:disabled, QPushButton#rowButton:disabled { color: #a3aabd; }
QPushButton#tool { text-align: left; min-height: 26px; padding: 6px 9px; }
QPushButton#tool:checked { background: #eeefff; color: #393eaa; border-color: #8d94e1; }
QPushButton#tool:disabled { color: #858da2; background: #f6f7fa; }
QLineEdit, QSpinBox, QComboBox { min-height: 20px; background: #fbfcff; border: 1px solid #dfe3ef; border-radius: 8px; padding: 6px 8px; selection-background-color: #5056c8; }
QLineEdit:focus, QSpinBox:focus, QComboBox:focus { border-color: #777edc; }
QComboBox QAbstractItemView { background: #ffffff; color: #1d2538; selection-background-color: #e9ebfd; selection-color: #272d69; border: 1px solid #e0e3f1; }
QListWidget, QPlainTextEdit { background: #ffffff; border: 1px solid #e1e5f0; border-radius: 9px; outline: 0; }
QListWidget::item { padding: 8px; }
QListWidget::item:selected { background: #eeefff; color: #262c69; }
QListWidget::item:hover { background: #f4f5fb; }
QScrollBar:vertical { border: 0; width: 8px; margin: 0; background: transparent; }
QScrollBar::handle:vertical { background: #cbd1e1; min-height: 26px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QProgressBar { border: 0; border-radius: 3px; background: #e7e9f6; height: 6px; }
QProgressBar::chunk { background: #5056c8; border-radius: 3px; }
QToolTip { background: #282e4a; color: #ffffff; padding: 4px; border: 1px solid #282e4a; }
"""

import sys
import os
import math
import json
import tempfile
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QToolBar, QFileDialog, QInputDialog, QColorDialog, QFontDialog,
    QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem,
    QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsPathItem,
    QGraphicsSimpleTextItem, QGraphicsItem, QMessageBox, QLabel, QMenu,
    QComboBox, QWidget, QSizePolicy, QDialog, QVBoxLayout, QTextBrowser,
    QPushButton, QHBoxLayout, QStatusBar, QFormLayout, QSpinBox,
    QDialogButtonBox, QLineEdit, QTextEdit, QCheckBox, QToolButton, QFrame,
    QTabWidget
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QPolygonF, QFont, QAction,
    QActionGroup, QTransform, QPainterPath, QPainterPathStroker, QImageReader,
    QBrush, QPalette, QIcon, QCursor, QDoubleValidator, QKeySequence,
    QGuiApplication, QFontMetricsF
)
from PyQt6.QtCore import (
    Qt, QPointF, QRectF, QLineF, QTimer, QBuffer, QByteArray, QIODevice,
    QSettings, pyqtSignal, QSize, QRect, QPoint
)

APP_NAME = "HandwrittenImageMiya"
APP_VERSION = "v2.0.0"
PROJECT_FORMAT_VERSION = "2.0.0"
DEFAULT_FONT_FAMILY = "Meiryo UI"
SUPPORTED_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp"}
SUPPORTED_OPEN_EXTS = SUPPORTED_IMAGE_EXTS | {".pdf", ".hwi"}
MAX_UNDO_STEPS = 30
MAX_RECENT_FILES = 10
QUICK_COLORS = [
    ("赤", "#E53935"),
    ("オレンジ", "#FB8C00"),
    ("黄", "#FDD835"),
    ("緑", "#2E7D32"),
    ("青", "#1E88E5"),
    ("紫", "#8E24AA"),
    ("黒", "#212121"),
    ("白", "#FFFFFF"),
]
QUICK_TEXT_TEMPLATES = ["ここを確認", "修正お願いします", "OK", "NG", "※注意", "削除"]


def resource_path(relative_path):
    """実行時（exe）でも通常時（.py）でも正しいファイルパスを取得する"""
    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)


def find_readme_path():
    """READMEファイルの大文字・小文字の差異を吸収して探索する"""
    for candidate in ("README.MD", "README.md", "readme.md", "Readme.md"):
        p = resource_path(candidate)
        if os.path.exists(p):
            return p
    return resource_path("README.MD")


def render_pdf_page_to_pixmap(page, target_dpi=150.0, max_dim=3600):
    """PDFページを高精細かつ安全にQPixmapへレンダリングする"""
    rect = page.rect
    zoom = target_dpi / 72.0
    max_side = max(float(rect.width), float(rect.height), 1.0)
    if max_side * zoom > max_dim:
        zoom = max_dim / max_side
    zoom = max(0.5, zoom)

    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    samples = pix.samples  # バッファの寿命を明示的に保持
    qimg = QImage(samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def qimage_to_bytes(image, fmt="JPEG", quality=95):
    """QImageをメモリ上で指定フォーマットのバイト列に変換する"""
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, fmt, quality)
    buffer.close()
    return bytes(byte_array.data())


def create_mosaic_pixmap(source_pixmap, block_size=14):
    """指定ピクスマップにモザイク処理（縮小→ニアレスト拡大）を施す"""
    if source_pixmap.isNull() or source_pixmap.width() <= 0 or source_pixmap.height() <= 0:
        return source_pixmap
    w = source_pixmap.width()
    h = source_pixmap.height()
    small_w = max(1, w // max(2, block_size))
    small_h = max(1, h // max(2, block_size))
    small = source_pixmap.scaled(
        small_w, small_h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation
    )
    return small.scaled(
        w, h,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation
    )


def create_color_icon(color, size=14):
    """現在選択中の色を分かりやすく示すスウォッチアイコンを生成する"""
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

    # 半透明色も識別できるよう市松模様を下地に描画
    if color.alpha() < 255:
        cell = max(3, size // 4)
        for y in range(0, size, cell):
            for x in range(0, size, cell):
                is_light = ((x // cell) + (y // cell)) % 2 == 0
                painter.fillRect(x, y, cell, cell, QColor("#FFFFFF") if is_light else QColor("#CCCCCC"))

    painter.fillRect(1, 1, size - 2, size - 2, color)
    painter.setPen(QPen(QColor("#555555"), 1))
    painter.drawRect(0, 0, size - 1, size - 1)
    painter.end()
    return QIcon(pix)


def snap_line_point(start, end):
    """Shiftキー押下時に直線を0/45/90度単位にスナップさせる"""
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    dist = math.hypot(dx, dy)
    if dist < 1e-6:
        return end
    angle = math.atan2(dy, dx)
    snapped_angle = round(angle / (math.pi / 4.0)) * (math.pi / 4.0)
    return QPointF(start.x() + math.cos(snapped_angle) * dist,
                   start.y() + math.sin(snapped_angle) * dist)


def snap_square_point(anchor, current):
    """Shiftキー押下時に図形の縦横比を1:1（正方形・正円）にスナップさせる"""
    dx = current.x() - anchor.x()
    dy = current.y() - anchor.y()
    side = max(abs(dx), abs(dy))
    sx = 1.0 if dx >= 0 else -1.0
    sy = 1.0 if dy >= 0 else -1.0
    return QPointF(anchor.x() + sx * side, anchor.y() + sy * side)


def apply_light_theme(app):
    """OSがダークモードであってもアプリ全体を常に完全なライトモードに固定する"""
    app.setStyle("Fusion")
    app.setFont(QFont(DEFAULT_FONT_FAMILY, 9))

    # Qt 6.8以降ではカラースキームも明示的にLightへ固定
    hints = app.styleHints()
    if hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
        try:
            hints.setColorScheme(Qt.ColorScheme.Light)
        except Exception:
            pass

    palette = QPalette()
    window_bg = QColor("#F5F6F7")
    base_bg = QColor("#FFFFFF")
    alt_bg = QColor("#F0F2F5")
    text_fg = QColor("#222222")
    disabled_fg = QColor("#9AA0A6")
    disabled_bg = QColor("#EBEEF0")
    highlight_bg = QColor("#005FB8")
    highlight_fg = QColor("#FFFFFF")
    button_bg = QColor("#FFFFFF")

    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        palette.setColor(group, QPalette.ColorRole.Window, window_bg)
        palette.setColor(group, QPalette.ColorRole.WindowText, text_fg)
        palette.setColor(group, QPalette.ColorRole.Base, base_bg)
        palette.setColor(group, QPalette.ColorRole.AlternateBase, alt_bg)
        palette.setColor(group, QPalette.ColorRole.ToolTipBase, QColor("#FFFDF5"))
        palette.setColor(group, QPalette.ColorRole.ToolTipText, text_fg)
        palette.setColor(group, QPalette.ColorRole.Text, text_fg)
        palette.setColor(group, QPalette.ColorRole.Button, button_bg)
        palette.setColor(group, QPalette.ColorRole.ButtonText, text_fg)
        palette.setColor(group, QPalette.ColorRole.BrightText, QColor("#CC0000"))
        palette.setColor(group, QPalette.ColorRole.Link, highlight_bg)
        palette.setColor(group, QPalette.ColorRole.Highlight, highlight_bg)
        palette.setColor(group, QPalette.ColorRole.HighlightedText, highlight_fg)
        if hasattr(QPalette.ColorRole, "PlaceholderText"):
            palette.setColor(group, QPalette.ColorRole.PlaceholderText, QColor("#888888"))

    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Window, window_bg)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_fg)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, disabled_bg)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_fg)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, disabled_bg)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_fg)
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor("#B8D4F0"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))

    app.setPalette(palette)

    bg_main = "#F5F6F7"
    bg_toolbar = "#FFFFFF"
    bg_view = "#D0D7DE"
    text_main = "#222222"
    text_muted = "#777777"
    border_toolbar = "#D0D4DA"
    selection_bg = "#005FB8"
    selection_text = "#FFFFFF"
    hover_bg = "#E8EEF5"
    combo_bg = "#FFFFFF"
    dialog_bg = "#F5F6F7"

    style = f"""
    QMainWindow {{
        background-color: {bg_main};
        color: {text_main};
    }}
    QMenuBar {{
        background-color: {bg_toolbar};
        border-bottom: 1px solid {border_toolbar};
        font-size: 10pt;
        color: {text_main};
    }}
    QMenuBar::item {{
        background-color: transparent;
        padding: 5px 12px;
    }}
    QMenuBar::item:selected {{
        background-color: {selection_bg};
        color: {selection_text};
    }}
    QMenu {{
        background-color: {bg_toolbar};
        color: {text_main};
        border: 1px solid {border_toolbar};
        font-size: 10pt;
        padding: 4px 0px;
    }}
    QMenu::item {{
        padding: 6px 28px 6px 22px;
    }}
    QMenu::item:selected {{
        background-color: {selection_bg};
        color: {selection_text};
    }}
    QMenu::item:disabled {{
        color: #A0A5AC;
        background-color: transparent;
    }}
    QMenu::separator {{
        height: 1px;
        background: #E2E5EA;
        margin: 4px 8px;
    }}
    QToolBar {{
        background-color: {bg_toolbar};
        border-bottom: 1px solid {border_toolbar};
        spacing: 3px;
        padding: 3px 6px;
    }}
    QToolBar::separator {{
        width: 1px;
        background-color: #DCDFE4;
        margin: 4px 5px;
    }}
    QToolButton {{
        color: {text_main};
        font-size: 9pt;
        border: 1px solid transparent;
        border-radius: 4px;
        padding: 3px 6px;
        min-height: 20px;
        background-color: transparent;
    }}
    QToolButton:hover {{
        background-color: {hover_bg};
        border: 1px solid #B9C8DA;
    }}
    QToolButton:checked {{
        background-color: {selection_bg};
        border: 1px solid {selection_bg};
        color: {selection_text};
        font-weight: bold;
    }}
    QToolButton:disabled {{
        color: #A6ABB2;
        background-color: transparent;
        border: 1px solid transparent;
    }}
    QComboBox {{
        border: 1px solid {border_toolbar};
        border-radius: 4px;
        padding: 2px 5px;
        background-color: {combo_bg};
        color: {text_main};
        font-size: 9pt;
        min-height: 20px;
        min-width: 48px;
    }}
    QComboBox:hover, QComboBox:focus {{
        border: 1px solid {selection_bg};
    }}
    QComboBox QAbstractItemView {{
        background-color: {combo_bg};
        color: {text_main};
        selection-background-color: {selection_bg};
        selection-color: {selection_text};
        border: 1px solid {border_toolbar};
        outline: none;
    }}
    QToolBar QLabel {{
        color: {text_main};
        font-weight: bold;
        padding-left: 3px;
        padding-right: 2px;
        font-size: 9pt;
    }}
    QGraphicsView {{
        background-color: {bg_view};
        border: none;
    }}
    QStatusBar {{
        background-color: {bg_toolbar};
        color: {text_main};
        border-top: 1px solid {border_toolbar};
        font-size: 9pt;
    }}
    QStatusBar::item {{
        border: none;
    }}
    QStatusBar QLabel {{
        color: {text_muted};
        padding: 2px 8px;
        font-size: 9pt;
    }}
    QDialog, QMessageBox, QInputDialog {{
        background-color: {dialog_bg};
        color: {text_main};
    }}
    QDialog QLabel, QMessageBox QLabel, QInputDialog QLabel {{
        color: {text_main};
        font-size: 10pt;
        font-weight: normal;
    }}
    QLineEdit, QSpinBox, QTextEdit, QTextBrowser {{
        background-color: {combo_bg};
        color: {text_main};
        border: 1px solid {border_toolbar};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: {selection_bg};
        selection-color: {selection_text};
    }}
    QLineEdit:focus, QSpinBox:focus, QTextEdit:focus {{
        border: 1px solid {selection_bg};
    }}
    QPushButton {{
        background-color: {combo_bg};
        color: {text_main};
        border: 1px solid {border_toolbar};
        border-radius: 4px;
        padding: 6px 18px;
        min-width: 64px;
        font-size: 10pt;
    }}
    QPushButton:hover {{
        background-color: {selection_bg};
        color: {selection_text};
        border: 1px solid {selection_bg};
    }}
    QPushButton:pressed {{
        background-color: #004B94;
        color: {selection_text};
    }}
    QToolTip {{
        background-color: #FFFDF5;
        color: {text_main};
        border: 1px solid #C5C9CE;
        padding: 4px 7px;
        font-size: 9pt;
    }}
    QTabWidget::pane {{
        border: 1px solid {border_toolbar};
        background-color: {combo_bg};
        border-radius: 4px;
        top: -1px;
    }}
    QTabBar::tab {{
        background-color: #EAEEF3;
        color: #444444;
        border: 1px solid {border_toolbar};
        border-bottom: none;
        border-top-left-radius: 5px;
        border-top-right-radius: 5px;
        padding: 7px 14px;
        margin-right: 2px;
        font-size: 9pt;
    }}
    QTabBar::tab:hover {{
        background-color: {hover_bg};
        color: {text_main};
    }}
    QTabBar::tab:selected {{
        background-color: {combo_bg};
        color: {selection_bg};
        font-weight: bold;
        border-bottom: 2px solid {combo_bg};
    }}
    QCheckBox {{
        color: {text_main};
        font-size: 9pt;
        spacing: 6px;
    }}
    QScrollBar:vertical {{
        background: #EEF0F3;
        width: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:vertical {{
        background: #BDC3CB;
        min-height: 28px;
        border-radius: 4px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #98A1AD;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar:horizontal {{
        background: #EEF0F3;
        height: 12px;
        margin: 0px;
    }}
    QScrollBar::handle:horizontal {{
        background: #BDC3CB;
        min-width: 28px;
        border-radius: 4px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: #98A1AD;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
    }}
    """
    app.setStyleSheet(style)


class CustomGraphicsView(QGraphicsView):
    """拡大縮小、横スクロール、パン移動、ドラッグ＆ドロップに対応したカスタムQGraphicsView"""
    zoomChanged = pyqtSignal(float)
    fileDropped = pyqtSignal(str, bool)  # (path, insert_as_annotation)

    MIN_ZOOM = 0.05
    MAX_ZOOM = 20.0

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)

        self._panning = False
        self._space_pressed = False
        self._pan_start_pos = None
        self._saved_drag_mode = QGraphicsView.DragMode.NoDrag
        self._saved_cursor = Qt.CursorShape.ArrowCursor

    def current_zoom(self):
        t = self.transform()
        return max(1e-6, math.hypot(t.m11(), t.m12()))

    def zoom_by(self, factor):
        cur = self.current_zoom()
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, cur * factor))
        actual = target / cur
        if abs(actual - 1.0) > 1e-6:
            self.scale(actual, actual)
            self.zoomChanged.emit(self.current_zoom())

    def reset_zoom(self):
        self.resetTransform()
        self.zoomChanged.emit(self.current_zoom())

    def fit_scene_in_view(self):
        if self.scene() and not self.scene().sceneRect().isEmpty():
            self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self.zoomChanged.emit(self.current_zoom())

    def wheelEvent(self, event):
        modifiers = event.modifiers()

        # Ctrl + 上下スクロール = カーソル中心で拡大・縮小
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            if angle != 0:
                factor = 1.25 if angle > 0 else 0.8
                self.zoom_by(factor)
            event.accept()

        # Shift + 上下スクロール = 横スクロール
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            angle = event.angleDelta().y()
            h_bar = self.horizontalScrollBar()
            if h_bar:
                h_bar.setValue(h_bar.value() - angle)
            event.accept()

        else:
            super().wheelEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and not self._space_pressed:
            self._space_pressed = True
            self._saved_cursor = self.viewport().cursor().shape()
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat() and self._space_pressed:
            self._space_pressed = False
            if not self._panning:
                self.viewport().setCursor(self._saved_cursor)
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        if self._space_pressed or self._panning:
            self._space_pressed = False
            self._panning = False
            self._pan_start_pos = None
            self.setDragMode(self._saved_drag_mode)
            self.viewport().setCursor(self._saved_cursor)
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        # 中ボタンまたは Space + 左ボタンでパン移動
        if event.button() == Qt.MouseButton.MiddleButton or (
            event.button() == Qt.MouseButton.LeftButton and self._space_pressed
        ):
            self._panning = True
            self._pan_start_pos = event.position()
            self._saved_drag_mode = self.dragMode()
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._panning and self._pan_start_pos is not None:
            delta = event.position() - self._pan_start_pos
            self._pan_start_pos = event.position()
            h_bar = self.horizontalScrollBar()
            v_bar = self.verticalScrollBar()
            if h_bar:
                h_bar.setValue(int(h_bar.value() - delta.x()))
            if v_bar:
                v_bar.setValue(int(v_bar.value() - delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._panning and (
            event.button() == Qt.MouseButton.MiddleButton
            or event.button() == Qt.MouseButton.LeftButton
        ):
            self._panning = False
            self._pan_start_pos = None
            self.setDragMode(self._saved_drag_mode)
            if self._space_pressed:
                self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
            else:
                self.viewport().setCursor(self._saved_cursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    ext = os.path.splitext(url.toLocalFile())[1].lower()
                    if ext in SUPPORTED_OPEN_EXTS:
                        event.acceptProposedAction()
                        return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            insert_mode = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
            for url in event.mimeData().urls():
                if url.isLocalFile():
                    path = url.toLocalFile()
                    ext = os.path.splitext(path)[1].lower()
                    if ext in SUPPORTED_OPEN_EXTS:
                        self.fileDropped.emit(path, insert_mode)
                        event.acceptProposedAction()
                        return
        super().dropEvent(event)


class CustomLineItem(QGraphicsLineItem):
    """線を描画し、当たり判定（ドラッグ範囲）をキャッシュ付きで広げたカスタムアイテム"""
    def __init__(self, line, pen):
        super().__init__(line)
        self._cached_shape = None
        self.setPen(pen)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def setLine(self, *args):
        self._cached_shape = None
        super().setLine(*args)

    def setPen(self, pen):
        self._cached_shape = None
        super().setPen(pen)

    def shape(self):
        if self._cached_shape is None:
            path = QPainterPath()
            path.moveTo(self.line().p1())
            path.lineTo(self.line().p2())
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF() + 12.0, 22.0))
            self._cached_shape = stroker.createStroke(path)
        return self._cached_shape


class ArrowItem(CustomLineItem):
    """矢印（片矢印・両矢印）を描画するカスタムアイテム"""
    def __init__(self, line, pen, double_ended=False):
        self._double_ended = bool(double_ended)
        super().__init__(line, pen)

    def is_double_ended(self):
        return self._double_ended

    def set_double_ended(self, value):
        self.prepareGeometryChange()
        self._double_ended = bool(value)
        self._cached_shape = None
        self.update()

    def _arrow_size(self):
        return max(12.0, self.pen().widthF() * 3.5)

    def _arrow_head_points(self, tip, from_pt):
        dx = tip.x() - from_pt.x()
        dy = tip.y() - from_pt.y()
        angle = math.atan2(-dy, dx)
        arrow_size = self._arrow_size()
        p1 = tip - QPointF(math.sin(angle + math.pi / 3.0) * arrow_size,
                           math.cos(angle + math.pi / 3.0) * arrow_size)
        p2 = tip - QPointF(math.sin(angle + math.pi - math.pi / 3.0) * arrow_size,
                           math.cos(angle + math.pi - math.pi / 3.0) * arrow_size)
        return p1, p2

    def boundingRect(self):
        extra = self._arrow_size() + self.pen().widthF() + 4.0
        return super().boundingRect().adjusted(-extra, -extra, extra, extra)

    def shape(self):
        if self._cached_shape is None:
            line = self.line()
            path = QPainterPath()
            path.moveTo(line.p1())
            path.lineTo(line.p2())
            if line.length() > 0:
                p1, p2 = self._arrow_head_points(line.p2(), line.p1())
                path.moveTo(p1)
                path.lineTo(line.p2())
                path.lineTo(p2)
                if self._double_ended:
                    q1, q2 = self._arrow_head_points(line.p1(), line.p2())
                    path.moveTo(q1)
                    path.lineTo(line.p1())
                    path.lineTo(q2)
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF() + 12.0, 22.0))
            self._cached_shape = stroker.createStroke(path)
        return self._cached_shape

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        line = self.line()
        if line.length() == 0:
            return

        head_pen = QPen(self.pen())
        head_pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(head_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        p1, p2 = self._arrow_head_points(line.p2(), line.p1())
        painter.drawPolyline(QPolygonF([p1, line.p2(), p2]))

        if self._double_ended:
            q1, q2 = self._arrow_head_points(line.p1(), line.p2())
            painter.drawPolyline(QPolygonF([q1, line.p1(), q2]))


class CustomPathItem(QGraphicsPathItem):
    """フリーハンド・マーカーを描画し、当たり判定をキャッシュ付きで広げたカスタムアイテム"""
    def __init__(self, path, pen):
        super().__init__(path)
        self._cached_shape = None
        self.setPen(pen)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def setPath(self, path):
        self._cached_shape = None
        super().setPath(path)

    def setPen(self, pen):
        self._cached_shape = None
        super().setPen(pen)

    def setBrush(self, brush):
        self._cached_shape = None
        super().setBrush(brush)

    def shape(self):
        if self._cached_shape is None:
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF() + 12.0, 22.0))
            stroke = stroker.createStroke(self.path())
            if self.brush().style() != Qt.BrushStyle.NoBrush:
                stroke = stroke.united(self.path())
            self._cached_shape = stroke
        return self._cached_shape


class CustomRectItem(QGraphicsRectItem):
    """四角・角丸四角を描画し、当たり判定をキャッシュ・塗りつぶし対応したカスタムアイテム"""
    def __init__(self, rect, pen, corner_radius=0.0):
        super().__init__(rect)
        self._corner_radius = float(corner_radius)
        self._cached_shape = None
        self.setPen(pen)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def corner_radius(self):
        return self._corner_radius

    def setCornerRadius(self, radius):
        self._corner_radius = max(0.0, float(radius))
        self._cached_shape = None
        self.update()

    def setRect(self, *args):
        self._cached_shape = None
        super().setRect(*args)

    def setPen(self, pen):
        self._cached_shape = None
        super().setPen(pen)

    def setBrush(self, brush):
        self._cached_shape = None
        super().setBrush(brush)

    def _effective_radius(self):
        r = self.rect()
        return min(self._corner_radius, r.width() * 0.5, r.height() * 0.5)

    def paint(self, painter, option, widget=None):
        if self._corner_radius > 0.0:
            painter.setPen(self.pen())
            painter.setBrush(self.brush())
            rad = self._effective_radius()
            painter.drawRoundedRect(self.rect(), rad, rad)
            if self.isSelected():
                sel_pen = QPen(QColor(0, 95, 184), 0, Qt.PenStyle.DashLine)
                painter.setPen(sel_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(self.rect())
        else:
            super().paint(painter, option, widget)

    def shape(self):
        if self._cached_shape is None:
            path = QPainterPath()
            if self._corner_radius > 0.0:
                rad = self._effective_radius()
                path.addRoundedRect(self.rect(), rad, rad)
            else:
                path.addRect(self.rect())
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF() + 12.0, 22.0))
            stroke = stroker.createStroke(path)
            if self.brush().style() != Qt.BrushStyle.NoBrush:
                stroke = stroke.united(path)
            self._cached_shape = stroke
        return self._cached_shape


class CustomEllipseItem(QGraphicsEllipseItem):
    """楕円/丸を描画し、当たり判定をキャッシュ・塗りつぶし対応したカスタムアイテム"""
    def __init__(self, rect, pen):
        super().__init__(rect)
        self._cached_shape = None
        self.setPen(pen)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def setRect(self, *args):
        self._cached_shape = None
        super().setRect(*args)

    def setPen(self, pen):
        self._cached_shape = None
        super().setPen(pen)

    def setBrush(self, brush):
        self._cached_shape = None
        super().setBrush(brush)

    def shape(self):
        if self._cached_shape is None:
            path = QPainterPath()
            path.addEllipse(self.rect())
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF() + 12.0, 22.0))
            stroke = stroker.createStroke(path)
            if self.brush().style() != Qt.BrushStyle.NoBrush:
                stroke = stroke.united(path)
            self._cached_shape = stroke
        return self._cached_shape


class CustomPolygonItem(QGraphicsPolygonItem):
    """多角形（三角）を描画し、当たり判定をキャッシュ・塗りつぶし対応したカスタムアイテム"""
    def __init__(self, polygon, pen):
        super().__init__(polygon)
        self._cached_shape = None
        self.setPen(pen)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def setPolygon(self, polygon):
        self._cached_shape = None
        super().setPolygon(polygon)

    def setPen(self, pen):
        self._cached_shape = None
        super().setPen(pen)

    def setBrush(self, brush):
        self._cached_shape = None
        super().setBrush(brush)

    def shape(self):
        if self._cached_shape is None:
            path = QPainterPath()
            path.addPolygon(self.polygon())
            path.closeSubpath()
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self.pen().widthF() + 12.0, 22.0))
            stroke = stroker.createStroke(path)
            if self.brush().style() != Qt.BrushStyle.NoBrush:
                stroke = stroke.united(path)
            self._cached_shape = stroke
        return self._cached_shape


class CustomTextItem(QGraphicsTextItem):
    """背景色や枠線を設定でき、ダブルクリックで即編集できるカスタムテキストアイテム"""
    def __init__(self, text):
        super().__init__(text)
        self._bg_brush = QBrush(Qt.BrushStyle.NoBrush)
        self._border_pen = QPen(Qt.PenStyle.NoPen)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def brush(self):
        return self._bg_brush

    def setBrush(self, brush):
        self._bg_brush = brush
        self.update()

    def pen(self):
        return self._border_pen

    def setPen(self, pen):
        self.prepareGeometryChange()
        self._border_pen = pen
        self.update()

    def paint(self, painter, option, widget):
        if self._bg_brush.style() != Qt.BrushStyle.NoBrush or self._border_pen.style() != Qt.PenStyle.NoPen:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setBrush(self._bg_brush)
            painter.setPen(self._border_pen)
            painter.drawRoundedRect(self.boundingRect(), 4.0, 4.0)
            painter.restore()
        super().paint(painter, option, widget)

    def mouseDoubleClickEvent(self, event):
        scene = self.scene()
        if scene and hasattr(scene, "edit_text_item") and scene.current_tool == "select":
            scene.edit_text_item(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class CustomPixmapItem(QGraphicsItem):
    """注釈として挿入された画像・モザイクパッチアイテム"""
    def __init__(self, pixmap, rect, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self._rect = rect
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def boundingRect(self):
        return self._rect

    def setRect(self, rect):
        self.prepareGeometryChange()
        self._rect = rect
        self.update()

    def rect(self):
        return self._rect

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        painter.drawPixmap(self._rect, self.original_pixmap, QRectF(self.original_pixmap.rect()))
        if self.isSelected():
            pen = QPen(QColor(0, 95, 184), 0, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._rect)

    def shape(self):
        path = QPainterPath()
        path.addRect(self._rect)
        return path


class NumberStampItem(QGraphicsItem):
    """手順書や資料レビューに便利な連番丸数字スタンプアイテム"""
    def __init__(self, number, radius=20.0, bg_color=None, text_color=None, parent=None):
        super().__init__(parent)
        self.number = int(number)
        self._radius = max(8.0, float(radius))
        self._bg_color = QColor(bg_color) if bg_color is not None else QColor("#E53935")
        self._text_color = QColor(text_color) if text_color is not None else QColor("#FFFFFF")
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def radius(self):
        return self._radius

    def setRadius(self, radius):
        self.prepareGeometryChange()
        self._radius = max(8.0, float(radius))
        self.update()

    def bg_color(self):
        return self._bg_color

    def setBgColor(self, color):
        self._bg_color = QColor(color)
        self.update()

    def text_color(self):
        return self._text_color

    def setTextColor(self, color):
        self._text_color = QColor(color)
        self.update()

    def setNumber(self, number):
        self.number = int(number)
        self.update()

    def boundingRect(self):
        pad = 3.0
        r = self._radius + pad
        return QRectF(-r, -r, r * 2.0, r * 2.0)

    def shape(self):
        path = QPainterPath()
        r = self._radius + 4.0
        path.addEllipse(QRectF(-r, -r, r * 2.0, r * 2.0))
        return path

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        circle_rect = QRectF(-self._radius, -self._radius, self._radius * 2.0, self._radius * 2.0)

        border_pen = QPen(QColor("#FFFFFF"), max(1.5, self._radius * 0.12))
        painter.setPen(border_pen)
        painter.setBrush(QBrush(self._bg_color))
        painter.drawEllipse(circle_rect)

        label = str(self.number)
        font = QFont(DEFAULT_FONT_FAMILY)
        font.setBold(True)
        scale_factor = 0.95 if len(label) <= 1 else (0.78 if len(label) == 2 else 0.62)
        font.setPixelSize(max(8, int(self._radius * scale_factor * 1.15)))
        painter.setFont(font)
        painter.setPen(QPen(self._text_color))
        painter.drawText(circle_rect, Qt.AlignmentFlag.AlignCenter, label)

        if self.isSelected():
            sel_pen = QPen(QColor(0, 95, 184), 0, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(circle_rect)

    def mouseDoubleClickEvent(self, event):
        scene = self.scene()
        if scene and hasattr(scene, "edit_stamp_number") and scene.current_tool == "select":
            scene.edit_stamp_number(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class CalloutItem(QGraphicsItem):
    """矢印しっぽ付きの吹き出し（コールアウト）注釈アイテム"""
    def __init__(self, box_rect, tip_point, text, font, text_color, pen, brush, parent=None):
        super().__init__(parent)
        self._box_rect = QRectF(box_rect).normalized()
        self._tip_point = QPointF(tip_point)
        self._text = str(text)
        self._font = QFont(font)
        self._text_color = QColor(text_color)
        self._pen = QPen(pen)
        self._brush = QBrush(brush)
        self._cached_outline = None
        self._cached_shape = None
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        )

    def _invalidate_cache(self):
        self._cached_outline = None
        self._cached_shape = None

    def box_rect(self):
        return QRectF(self._box_rect)

    def setBoxRect(self, rect):
        self.prepareGeometryChange()
        r = QRectF(rect).normalized()
        if r.width() < 36.0:
            r.setWidth(36.0)
        if r.height() < 28.0:
            r.setHeight(28.0)
        self._box_rect = r
        self._invalidate_cache()
        self.update()

    def tip_point(self):
        return QPointF(self._tip_point)

    def setTipPoint(self, pt):
        self.prepareGeometryChange()
        self._tip_point = QPointF(pt)
        self._invalidate_cache()
        self.update()

    def text(self):
        return self._text

    def setText(self, text):
        self._text = str(text)
        self.update()

    def font(self):
        return QFont(self._font)

    def setFont(self, font):
        self._font = QFont(font)
        self.update()

    def defaultTextColor(self):
        return QColor(self._text_color)

    def setDefaultTextColor(self, color):
        self._text_color = QColor(color)
        self.update()

    def pen(self):
        return QPen(self._pen)

    def setPen(self, pen):
        self.prepareGeometryChange()
        self._pen = QPen(pen)
        self._invalidate_cache()
        self.update()

    def brush(self):
        return QBrush(self._brush)

    def setBrush(self, brush):
        self._brush = QBrush(brush)
        self.update()

    def fit_box_to_text(self):
        """文字量に合わせて吹き出し枠をちょうど良いサイズへ調整する"""
        fm = QFontMetricsF(self._font)
        pad_x = 18.0
        pad_y = 12.0
        max_w = 420.0
        bound = fm.boundingRect(
            QRectF(0, 0, max_w, 2000.0),
            int(Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap),
            self._text or " ",
        )
        new_w = max(80.0, min(max_w + pad_x * 2.0, bound.width() + pad_x * 2.0 + 10.0))
        new_h = max(42.0, bound.height() + pad_y * 2.0 + 6.0)
        c = self._box_rect.center()
        self.setBoxRect(QRectF(c.x() - new_w * 0.5, c.y() - new_h * 0.5, new_w, new_h))

    def _outline_path(self):
        if self._cached_outline is None:
            r = self._box_rect
            rad = min(10.0, r.width() * 0.25, r.height() * 0.25)
            box_path = QPainterPath()
            box_path.addRoundedRect(r, rad, rad)
            if not r.contains(self._tip_point):
                center = r.center()
                dx = self._tip_point.x() - center.x()
                dy = self._tip_point.y() - center.y()
                dist = math.hypot(dx, dy)
                if dist > 1e-3:
                    nx = -dy / dist
                    ny = dx / dist
                    hw = min(14.0, max(6.0, min(r.width(), r.height()) * 0.22))
                    b1 = QPointF(center.x() + nx * hw, center.y() + ny * hw)
                    b2 = QPointF(center.x() - nx * hw, center.y() - ny * hw)
                    tail = QPainterPath()
                    tail.moveTo(b1)
                    tail.lineTo(self._tip_point)
                    tail.lineTo(b2)
                    tail.closeSubpath()
                    box_path = box_path.united(tail).simplified()
            self._cached_outline = box_path
        return self._cached_outline

    def boundingRect(self):
        pad = max(4.0, self._pen.widthF() + 4.0)
        return self._outline_path().boundingRect().adjusted(-pad, -pad, pad, pad)

    def shape(self):
        if self._cached_shape is None:
            outline = self._outline_path()
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self._pen.widthF() + 10.0, 18.0))
            self._cached_shape = stroker.createStroke(outline).united(outline)
        return self._cached_shape

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        outline = self._outline_path()
        painter.setPen(self._pen)
        painter.setBrush(self._brush)
        painter.drawPath(outline)

        if self._text:
            text_rect = self._box_rect.adjusted(10.0, 6.0, -10.0, -6.0)
            painter.setFont(self._font)
            painter.setPen(QPen(self._text_color))
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap),
                self._text,
            )

        if self.isSelected():
            sel_pen = QPen(QColor(0, 95, 184), 0, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._box_rect)
        painter.restore()

    def mouseDoubleClickEvent(self, event):
        scene = self.scene()
        if scene and hasattr(scene, "edit_callout_item") and scene.current_tool == "select":
            scene.edit_callout_item(self)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class SpotlightItem(QGraphicsItem):
    """指定範囲だけ明るく際立たせ周囲を暗くして注目箇所を一目で伝えるアイテム"""
    def __init__(self, rect, pen, dim_alpha=115, corner_radius=8.0, parent=None):
        super().__init__(parent)
        self._rect = QRectF(rect).normalized()
        self._pen = QPen(pen)
        self._dim_alpha = max(30, min(220, int(dim_alpha)))
        self._corner_radius = max(0.0, float(corner_radius))
        self._cached_shape = None
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )

    def rect(self):
        return QRectF(self._rect)

    def setRect(self, rect):
        self.prepareGeometryChange()
        self._rect = QRectF(rect).normalized()
        self._cached_shape = None
        self.update()

    def pen(self):
        return QPen(self._pen)

    def setPen(self, pen):
        self.prepareGeometryChange()
        self._pen = QPen(pen)
        self._cached_shape = None
        self.update()

    def dim_alpha(self):
        return self._dim_alpha

    def setDimAlpha(self, alpha):
        self._dim_alpha = max(30, min(220, int(alpha)))
        self.update()

    def corner_radius(self):
        return self._corner_radius

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange:
            self.prepareGeometryChange()
        return super().itemChange(change, value)

    def _effective_radius(self):
        return min(self._corner_radius, self._rect.width() * 0.5, self._rect.height() * 0.5)

    def boundingRect(self):
        pad = max(6.0, self._pen.widthF() + 4.0)
        base = self._rect
        sc = self.scene()
        if sc is not None and not sc.sceneRect().isEmpty():
            cover = self.mapRectFromScene(sc.sceneRect())
            base = base.united(cover)
        return base.adjusted(-pad, -pad, pad, pad)

    def shape(self):
        if self._cached_shape is None:
            path = QPainterPath()
            rad = self._effective_radius()
            if rad > 0.0:
                path.addRoundedRect(self._rect, rad, rad)
            else:
                path.addRect(self._rect)
            stroker = QPainterPathStroker()
            stroker.setWidth(max(self._pen.widthF() + 14.0, 24.0))
            self._cached_shape = stroker.createStroke(path)
        return self._cached_shape

    def paint(self, painter, option, widget=None):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rad = self._effective_radius()

        sc = self.scene()
        if sc is not None and not sc.sceneRect().isEmpty():
            cover = self.mapRectFromScene(sc.sceneRect())
            dim_path = QPainterPath()
            dim_path.setFillRule(Qt.FillRule.OddEvenFill)
            dim_path.addRect(cover)
            if rad > 0.0:
                dim_path.addRoundedRect(self._rect, rad, rad)
            else:
                dim_path.addRect(self._rect)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(0, 0, 0, self._dim_alpha)))
            painter.drawPath(dim_path)

        painter.setPen(self._pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if rad > 0.0:
            painter.drawRoundedRect(self._rect, rad, rad)
        else:
            painter.drawRect(self._rect)

        if self.isSelected():
            sel_pen = QPen(QColor(0, 150, 255), 0, Qt.PenStyle.DashLine)
            painter.setPen(sel_pen)
            painter.drawRect(self._rect)
        painter.restore()


class MarginHandleItem(QGraphicsRectItem):
    """余白をドラッグ操作で直感的に追加・削減するための専用ハンドル"""
    SIDE_LABELS = {"top": "上", "bottom": "下", "left": "左", "right": "右"}

    def __init__(self, side, rect, parent_scene):
        super().__init__(rect)
        self.side = side
        self.parent_scene = parent_scene
        self.setAcceptHoverEvents(True)
        self.setBrush(QBrush(QColor(0, 120, 255, 130)))
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setZValue(999999)
        self.press_pos = None
        self.orig_rect = None
        self.preview_rect = None
        self.preview_label = None

    def cleanup_preview(self):
        """プレビュー枠・数値ラベルを確実にクリーンアップする"""
        if self.preview_rect is not None:
            if self.preview_rect.scene() is self.parent_scene:
                self.parent_scene.removeItem(self.preview_rect)
            self.preview_rect = None
        if self.preview_label is not None:
            if self.preview_label.scene() is self.parent_scene:
                self.parent_scene.removeItem(self.preview_label)
            self.preview_label = None
        self.press_pos = None

    def hoverEnterEvent(self, event):
        if self.side in ("top", "bottom"):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setBrush(QBrush(QColor(0, 120, 255, 210)))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor(0, 120, 255, 130)))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.cleanup_preview()
            self.press_pos = event.scenePos()
            self.orig_rect = self.parent_scene.sceneRect()

            scale = self.parent_scene.get_view_scale()
            self.preview_rect = QGraphicsRectItem(self.orig_rect)
            self.preview_rect.setPen(QPen(QColor(0, 120, 255), 2.0 / scale, Qt.PenStyle.DashLine))
            self.preview_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.preview_rect.setData(0, "transient_ui")
            self.preview_rect.setZValue(999998)
            self.parent_scene.addItem(self.preview_rect)

            self.preview_label = QGraphicsSimpleTextItem("")
            font = QFont(DEFAULT_FONT_FAMILY, 11)
            font.setBold(True)
            self.preview_label.setFont(font)
            self.preview_label.setBrush(QBrush(QColor("#005FB8")))
            self.preview_label.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
            self.preview_label.setData(0, "transient_ui")
            self.preview_label.setZValue(999999)
            self.parent_scene.addItem(self.preview_label)
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton and self.preview_rect:
            self.cleanup_preview()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_pos is not None and self.preview_rect is not None:
            delta = event.scenePos() - self.press_pos
            new_rect = QRectF(self.orig_rect)
            min_size = 50.0
            orig_img_rect = getattr(self.parent_scene, "original_image_rect", None)

            diff_px = 0
            if self.side == "top":
                new_top = self.orig_rect.top() + delta.y()
                if new_top > self.orig_rect.bottom() - min_size:
                    new_top = self.orig_rect.bottom() - min_size
                if orig_img_rect and not orig_img_rect.isEmpty() and new_top > orig_img_rect.top():
                    new_top = orig_img_rect.top()
                new_rect.setTop(new_top)
                diff_px = int(round(self.orig_rect.top() - new_top))
            elif self.side == "bottom":
                new_bottom = self.orig_rect.bottom() + delta.y()
                if new_bottom < self.orig_rect.top() + min_size:
                    new_bottom = self.orig_rect.top() + min_size
                if orig_img_rect and not orig_img_rect.isEmpty() and new_bottom < orig_img_rect.bottom():
                    new_bottom = orig_img_rect.bottom()
                new_rect.setBottom(new_bottom)
                diff_px = int(round(new_bottom - self.orig_rect.bottom()))
            elif self.side == "left":
                new_left = self.orig_rect.left() + delta.x()
                if new_left > self.orig_rect.right() - min_size:
                    new_left = self.orig_rect.right() - min_size
                if orig_img_rect and not orig_img_rect.isEmpty() and new_left > orig_img_rect.left():
                    new_left = orig_img_rect.left()
                new_rect.setLeft(new_left)
                diff_px = int(round(self.orig_rect.left() - new_left))
            elif self.side == "right":
                new_right = self.orig_rect.right() + delta.x()
                if new_right < self.orig_rect.left() + min_size:
                    new_right = self.orig_rect.left() + min_size
                if orig_img_rect and not orig_img_rect.isEmpty() and new_right < orig_img_rect.right():
                    new_right = orig_img_rect.right()
                new_rect.setRight(new_right)
                diff_px = int(round(new_right - self.orig_rect.right()))

            self.preview_rect.setRect(new_rect)
            sign = "+" if diff_px >= 0 else ""
            side_jp = self.SIDE_LABELS.get(self.side, "")
            label_text = f"{side_jp} {sign}{diff_px} px  ({int(new_rect.width())} × {int(new_rect.height())})"
            if self.preview_label is not None:
                self.preview_label.setText(label_text)
                self.preview_label.setPos(event.scenePos() + QPointF(14.0 / self.parent_scene.get_view_scale(), 0))
            self.parent_scene.statusMessageRequested.emit(f"余白調整中: {label_text}", 0)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.preview_rect is not None:
            final_rect = self.preview_rect.rect()
            self.cleanup_preview()

            top_margin = int(round(self.orig_rect.top() - final_rect.top()))
            bottom_margin = int(round(final_rect.bottom() - self.orig_rect.bottom()))
            left_margin = int(round(self.orig_rect.left() - final_rect.left()))
            right_margin = int(round(final_rect.right() - self.orig_rect.right()))

            if top_margin != 0 or bottom_margin != 0 or left_margin != 0 or right_margin != 0:
                main_win = self.parent_scene.parent()
                if hasattr(main_win, "apply_margin"):
                    color = (
                        self.parent_scene.current_brush_color
                        if self.parent_scene.use_fill
                        else QColor(Qt.GlobalColor.white)
                    )
                    main_win.apply_margin(top_margin, bottom_margin, left_margin, right_margin, color)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class AnnotationScene(QGraphicsScene):
    """画像と注釈を管理するシーン"""
    stateChanged = pyqtSignal()
    mouseSceneMoved = pyqtSignal(QPointF)
    statusMessageRequested = pyqtSignal(str, int)
    cropSelectionChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tool = "select"
        self.current_line_type = "line"     # line, arrow, double_arrow, freehand, marker
        self.current_shape_type = "rect"    # rect, rounded_rect, ellipse, triangle, mosaic, stamp, spotlight
        self.current_pen_style = Qt.PenStyle.SolidLine

        # 色管理（ペン・文字・ブラシ）
        self.current_pen_color = QColor(Qt.GlobalColor.red)
        self.current_text_color = QColor(Qt.GlobalColor.red)
        self.current_brush_color = QColor(Qt.GlobalColor.white)
        self.current_fill_mode = 0          # 0: 透過(枠のみ), 1: 塗りつぶし, 2: 半透明塗り

        # 図形線太さと文字サイズを明確に分離
        self.pen_width = 5.0
        self.current_font_size = 24.0
        self.current_font_family = DEFAULT_FONT_FAMILY
        self.current_font_bold = False
        self.current_font_italic = False
        self.next_stamp_number = 1
        self.recent_texts = []

        self.show_grid = False
        self.grid_size = 50
        self._is_exporting = False
        self._last_handles_rect = QRectF()

        self.start_point = None
        self.temp_item = None
        self.bg_item = None
        self.pending_text_item = None
        self._last_freehand_point = None
        self._callout_drag_tip = None

        # 切り抜き（トリミング）状態
        self.crop_rect = None
        self._crop_drag_mode = None
        self._crop_drag_start = None
        self._crop_orig_rect = None

        # スポイト状態
        self._eyedropper_image = None
        self._eyedropper_hover_pos = None
        self._eyedropper_hover_color = None

        self.resizing_item = None
        self.resize_mode = None
        self.initial_scale = 1.0
        self.initial_dist_x = 1.0
        self.initial_dist_y = 1.0
        self.shape_anchor = None
        self.initial_path = None
        self.initial_rect = None
        self.start_scene_rect = None
        self._drag_initial_positions = {}

        self.current_path = None
        self.copied_items = []

        self.has_unsaved_changes = False
        self.margin_handles = []
        self.original_image_rect = QRectF()

        self.undo_stack = []
        self.redo_stack = []
        self._state_id_counter = 0
        self._saved_state_id = None
        self.was_modified = False
        self._arrow_key_moved = False

        self.selectionChanged.connect(self._on_selection_changed)

    @property
    def use_fill(self):
        return self.current_fill_mode != 0

    @use_fill.setter
    def use_fill(self, value):
        if value:
            if self.current_fill_mode == 0:
                self.current_fill_mode = 1
        else:
            self.current_fill_mode = 0

    def get_current_brush(self):
        if self.current_fill_mode == 0:
            return QBrush(Qt.BrushStyle.NoBrush)
        color = QColor(self.current_brush_color)
        if self.current_fill_mode == 2 and color.alpha() == 255:
            color.setAlpha(95)
        return QBrush(color)

    def get_view_scale(self):
        if self.views():
            t = self.views()[0].transform()
            scale = math.hypot(t.m11(), t.m12())
            if scale > 1e-6:
                return scale
        return 1.0

    def _on_selection_changed(self):
        self.invalidate_handles()
        self.stateChanged.emit()

    def invalidate_handles(self):
        """選択ハンドルの描画領域だけを高速に再描画する（残像防止）"""
        new_rect = self._compute_handles_bounding_rect()
        dirty = self._last_handles_rect.united(new_rect)
        if not dirty.isEmpty():
            self.invalidate(dirty, QGraphicsScene.SceneLayer.ForegroundLayer)
        self._last_handles_rect = new_rect

    def _compute_handles_bounding_rect(self):
        if self.current_tool != "select":
            return QRectF()
        scale = self.get_view_scale()
        pad = 16.0 / scale
        union_rect = QRectF()
        for item in self.selectedItems():
            if item == self.bg_item or item == self.pending_text_item or isinstance(item, MarginHandleItem):
                continue
            r = item.sceneBoundingRect().adjusted(-pad, -pad, pad, pad)
            union_rect = union_rect.united(r) if not union_rect.isEmpty() else r
        return union_rect

    def annotation_items(self):
        """背景・ハンドル・配置待ち・一時UIを除いた全注釈アイテムをZ値昇順で返す"""
        result = []
        for item in self.items():
            if (
                item == self.bg_item
                or item.zValue() < 0
                or item == self.pending_text_item
                or isinstance(item, MarginHandleItem)
                or item == self.temp_item
                or item.data(0) == "transient_ui"
            ):
                continue
            if item.parentItem() is not None:
                continue
            result.append(item)
        result.sort(key=lambda it: it.zValue())
        return result

    def get_next_z_value(self):
        """シーン内で最も前面に配置するためのZ値を取得"""
        max_z = 0.0
        for item in self.items():
            if (
                item != self.bg_item
                and not isinstance(item, MarginHandleItem)
                and item.data(0) != "transient_ui"
                and item.zValue() < 900000
                and item.zValue() > max_z
            ):
                max_z = item.zValue()
        return max_z + 1.0

    def bring_to_front(self, item):
        """指定したアイテムを最前面に移動"""
        if not item or item == self.bg_item or isinstance(item, MarginHandleItem):
            return
        item.setZValue(self.get_next_z_value())
        self.has_unsaved_changes = True
        self.save_state()
        self.update()

    def send_to_back(self, item):
        """指定したアイテムを（背景より前の）最背面に移動"""
        if not item or item == self.bg_item or isinstance(item, MarginHandleItem):
            return
        others = [it for it in self.annotation_items() if it != item]
        item.setZValue(1.0)
        for idx, other in enumerate(others, start=2):
            other.setZValue(float(idx))
        self.has_unsaved_changes = True
        self.save_state()
        self.update()

    def _serialize_item_to_dict(self, item):
        if isinstance(item, ArrowItem):
            return {
                "type": "arrow",
                "line": QLineF(item.line()),
                "pen": QPen(item.pen()),
                "double_ended": item.is_double_ended(),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CustomLineItem):
            return {
                "type": "line",
                "line": QLineF(item.line()),
                "pen": QPen(item.pen()),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CustomRectItem):
            return {
                "type": "rect",
                "rect": QRectF(item.rect()),
                "pen": QPen(item.pen()),
                "brush": QBrush(item.brush()),
                "corner_radius": item.corner_radius(),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CustomEllipseItem):
            return {
                "type": "ellipse",
                "rect": QRectF(item.rect()),
                "pen": QPen(item.pen()),
                "brush": QBrush(item.brush()),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CustomPolygonItem):
            return {
                "type": "polygon",
                "polygon": QPolygonF(item.polygon()),
                "pen": QPen(item.pen()),
                "brush": QBrush(item.brush()),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CustomPathItem):
            return {
                "type": "path",
                "path": QPainterPath(item.path()),
                "pen": QPen(item.pen()),
                "brush": QBrush(item.brush()),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CustomTextItem):
            return {
                "type": "text",
                "text": item.toPlainText(),
                "font": QFont(item.font()),
                "color": QColor(item.defaultTextColor()),
                "pen": QPen(item.pen()),
                "brush": QBrush(item.brush()),
                "scale": item.scale(),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CustomPixmapItem):
            return {
                "type": "pixmap",
                "pixmap": item.original_pixmap,
                "rect": QRectF(item.rect()),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, NumberStampItem):
            return {
                "type": "stamp",
                "number": item.number,
                "radius": item.radius(),
                "bg_color": QColor(item.bg_color()),
                "text_color": QColor(item.text_color()),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, CalloutItem):
            return {
                "type": "callout",
                "box_rect": QRectF(item.box_rect()),
                "tip_point": QPointF(item.tip_point()),
                "text": item.text(),
                "font": QFont(item.font()),
                "color": QColor(item.defaultTextColor()),
                "pen": QPen(item.pen()),
                "brush": QBrush(item.brush()),
                "pos": QPointF(item.pos()),
            }
        if isinstance(item, SpotlightItem):
            return {
                "type": "spotlight",
                "rect": QRectF(item.rect()),
                "pen": QPen(item.pen()),
                "dim_alpha": item.dim_alpha(),
                "corner_radius": item.corner_radius(),
                "pos": QPointF(item.pos()),
            }
        return None

    def _create_item_from_dict(self, data):
        item_type = data.get("type")
        new_item = None
        if item_type == "arrow":
            new_item = ArrowItem(QLineF(data["line"]), QPen(data["pen"]), data.get("double_ended", False))
        elif item_type == "line":
            new_item = CustomLineItem(QLineF(data["line"]), QPen(data["pen"]))
        elif item_type == "rect":
            new_item = CustomRectItem(
                QRectF(data["rect"]), QPen(data["pen"]), data.get("corner_radius", 0.0)
            )
            new_item.setBrush(QBrush(data.get("brush", QBrush(Qt.BrushStyle.NoBrush))))
        elif item_type == "ellipse":
            new_item = CustomEllipseItem(QRectF(data["rect"]), QPen(data["pen"]))
            new_item.setBrush(QBrush(data.get("brush", QBrush(Qt.BrushStyle.NoBrush))))
        elif item_type == "polygon":
            new_item = CustomPolygonItem(QPolygonF(data["polygon"]), QPen(data["pen"]))
            new_item.setBrush(QBrush(data.get("brush", QBrush(Qt.BrushStyle.NoBrush))))
        elif item_type == "path":
            new_item = CustomPathItem(QPainterPath(data["path"]), QPen(data["pen"]))
            new_item.setBrush(QBrush(data.get("brush", QBrush(Qt.BrushStyle.NoBrush))))
        elif item_type == "text":
            new_item = CustomTextItem(data["text"])
            new_item.setFont(QFont(data["font"]))
            new_item.setDefaultTextColor(QColor(data["color"]))
            new_item.setPen(QPen(data.get("pen", QPen(Qt.PenStyle.NoPen))))
            new_item.setBrush(QBrush(data.get("brush", QBrush(Qt.BrushStyle.NoBrush))))
            new_item.setScale(data.get("scale", 1.0))
        elif item_type == "pixmap":
            new_item = CustomPixmapItem(data["pixmap"], QRectF(data["rect"]))
        elif item_type == "stamp":
            new_item = NumberStampItem(
                data["number"], data.get("radius", 20.0),
                data.get("bg_color", QColor("#E53935")),
                data.get("text_color", QColor("#FFFFFF"))
            )
        elif item_type == "callout":
            new_item = CalloutItem(
                QRectF(data["box_rect"]),
                QPointF(data["tip_point"]),
                data.get("text", ""),
                QFont(data["font"]),
                QColor(data["color"]),
                QPen(data["pen"]),
                QBrush(data["brush"]),
            )
        elif item_type == "spotlight":
            new_item = SpotlightItem(
                QRectF(data["rect"]),
                QPen(data["pen"]),
                data.get("dim_alpha", 115),
                data.get("corner_radius", 8.0),
            )
        if new_item is not None and "pos" in data:
            new_item.setPos(QPointF(data["pos"]))
        return new_item

    def get_scene_state(self):
        """現在のシーンのアイテム状態をZ値昇順でシリアライズして取得"""
        items_data = []
        for item in self.annotation_items():
            d = self._serialize_item_to_dict(item)
            if d is not None:
                items_data.append(d)

        bg_pixmap = self.bg_item.pixmap() if self.bg_item else QPixmap()
        bg_rect = QRectF(self.sceneRect())
        original_image_rect = QRectF(self.original_image_rect)

        return {
            "items": items_data,
            "bg_pixmap": bg_pixmap,
            "bg_rect": bg_rect,
            "original_image_rect": original_image_rect,
            "next_stamp_number": self.next_stamp_number,
        }

    def restore_scene_state(self, state):
        """保存された状態からシーンを高速に復元"""
        self._cancel_transient_operations()
        if isinstance(state, dict):
            items_data = state["items"]
            bg_pixmap = state.get("bg_pixmap")
            bg_rect = state.get("bg_rect")
            original_image_rect = state.get("original_image_rect", QRectF())
            if "next_stamp_number" in state:
                self.next_stamp_number = state["next_stamp_number"]
        else:
            items_data = state
            bg_pixmap = None
            bg_rect = None
            original_image_rect = QRectF()

        for item in list(self.items()):
            if item != self.bg_item and not isinstance(item, MarginHandleItem):
                self.removeItem(item)

        self.clearSelection()

        # 背景画像が同一なら再設定をスキップして高速化
        if bg_pixmap is not None and not bg_pixmap.isNull():
            if self.bg_item is None:
                self.bg_item = self.addPixmap(bg_pixmap)
                self.bg_item.setZValue(-1.0)
                self.bg_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            elif self.bg_item.pixmap().cacheKey() != bg_pixmap.cacheKey():
                self.bg_item.setPixmap(bg_pixmap)
        if bg_rect is not None and not bg_rect.isEmpty() and bg_rect != self.sceneRect():
            self.setSceneRect(bg_rect)

        self.original_image_rect = QRectF(original_image_rect)

        for i, data in enumerate(items_data):
            new_item = self._create_item_from_dict(data)
            if new_item is not None:
                new_item.setZValue(float(i + 1))
                self.addItem(new_item)

        self.update_margin_handles()
        self.invalidate_handles()

    def _cancel_transient_operations(self):
        """一時的なテキスト配置・描画・リサイズ状態を安全に解除する"""
        if self.pending_text_item is not None:
            if self.pending_text_item.scene() is self:
                self.removeItem(self.pending_text_item)
            self.pending_text_item = None
        if self.temp_item is not None:
            if self.temp_item.scene() is self:
                self.removeItem(self.temp_item)
            self.temp_item = None
        self.start_point = None
        self.current_path = None
        self._last_freehand_point = None
        self._callout_drag_tip = None
        self.resizing_item = None
        self.resize_mode = None
        self.shape_anchor = None
        self.initial_path = None
        self.initial_rect = None
        self.start_scene_rect = None
        self._drag_initial_positions.clear()
        self.was_modified = False
        self.clear_crop_selection()
        self.clear_eyedropper()

    def clear_crop_selection(self):
        had = self.crop_rect is not None
        self.crop_rect = None
        self._crop_drag_mode = None
        self._crop_drag_start = None
        self._crop_orig_rect = None
        if had:
            self.cropSelectionChanged.emit(False)
            self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.ForegroundLayer)

    def set_eyedropper_image(self, image):
        self._eyedropper_image = image
        self._eyedropper_hover_pos = None
        self._eyedropper_hover_color = None

    def clear_eyedropper(self):
        had = self._eyedropper_image is not None or self._eyedropper_hover_pos is not None
        self._eyedropper_image = None
        self._eyedropper_hover_pos = None
        self._eyedropper_hover_color = None
        if had:
            self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.ForegroundLayer)

    def remember_recent_text(self, text):
        t = (text or "").strip()
        if not t:
            return
        self.recent_texts = [x for x in self.recent_texts if x != t]
        self.recent_texts.insert(0, t)
        self.recent_texts = self.recent_texts[:6]

    def mark_as_saved(self):
        """現在のUndo先端状態を保存済みとして記録する"""
        if self.undo_stack:
            self._saved_state_id = self.undo_stack[-1].get("_id")
        self.has_unsaved_changes = False
        self.stateChanged.emit()

    def _sync_unsaved_from_stack(self):
        if self.undo_stack and self._saved_state_id is not None:
            self.has_unsaved_changes = (self.undo_stack[-1].get("_id") != self._saved_state_id)
        else:
            self.has_unsaved_changes = True

    def can_undo(self):
        return len(self.undo_stack) > 1

    def can_redo(self):
        return len(self.redo_stack) > 0

    def save_state(self):
        """操作のたびに状態をスタックに保存"""
        state = self.get_scene_state()
        self._state_id_counter += 1
        state["_id"] = self._state_id_counter
        self.undo_stack.append(state)
        self.redo_stack.clear()
        if len(self.undo_stack) > MAX_UNDO_STEPS:
            self.undo_stack.pop(0)
        self.stateChanged.emit()

    def undo(self):
        """元に戻す"""
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self.restore_scene_state(self.undo_stack[-1])
            self._sync_unsaved_from_stack()
            self.stateChanged.emit()

    def redo(self):
        """やり直す"""
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            self.restore_scene_state(state)
            self._sync_unsaved_from_stack()
            self.stateChanged.emit()

    def set_background(self, pixmap, reset_stamp_counter=True):
        self._cancel_transient_operations()
        self.clear_margin_handles()
        self.clear()
        self.bg_item = self.addPixmap(pixmap)
        self.bg_item.setZValue(-1.0)
        self.bg_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setSceneRect(QRectF(pixmap.rect()))

        self.original_image_rect = QRectF(0, 0, pixmap.width(), pixmap.height())
        if reset_stamp_counter:
            self.next_stamp_number = 1

        self.undo_stack.clear()
        self.redo_stack.clear()
        self.save_state()
        self.mark_as_saved()
        self.update_margin_handles()

    def load_state_as_clean(self, state, is_modified=False):
        """PDFの別ページなどキャッシュ済み状態をシーンへ復元する"""
        self._cancel_transient_operations()
        self.clear_margin_handles()
        self.clear()
        self.bg_item = None
        self.restore_scene_state(state)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.save_state()
        if is_modified:
            self._saved_state_id = None
            self.has_unsaved_changes = True
        else:
            self.mark_as_saved()
        self.stateChanged.emit()

    def update_margin_handles(self):
        """現在のツールモードとズーム倍率に応じて余白ドラッグハンドルを同期配置する"""
        self.clear_margin_handles()
        if self.current_tool == "margin" and self.bg_item:
            r = self.sceneRect()
            scale = self.get_view_scale()
            thickness = max(12.0, min(80.0, 16.0 / scale))
            half = thickness * 0.5

            top_h = MarginHandleItem("top", QRectF(r.left(), r.top() - half, r.width(), thickness), self)
            bot_h = MarginHandleItem("bottom", QRectF(r.left(), r.bottom() - half, r.width(), thickness), self)
            left_h = MarginHandleItem("left", QRectF(r.left() - half, r.top(), thickness, r.height()), self)
            right_h = MarginHandleItem("right", QRectF(r.right() - half, r.top(), thickness, r.height()), self)

            for h in (top_h, bot_h, left_h, right_h):
                self.addItem(h)
                self.margin_handles.append(h)

    def clear_margin_handles(self):
        """一時的な余白ドラッグハンドルとプレビュー枠をシーンから消去する"""
        for h in self.margin_handles:
            h.cleanup_preview()
            if h.scene() is self:
                self.removeItem(h)
        self.margin_handles.clear()

    def set_margin_handles_visible(self, visible):
        for h in self.margin_handles:
            h.setVisible(visible)

    def _get_item_handles(self, item):
        """選択アイテムごとのリサイズハンドル座標とカーソル種別を返す"""
        if isinstance(item, CustomPixmapItem):
            r = item.rect()
            return [
                ("pixmap_top_left", r.topLeft(), Qt.CursorShape.SizeFDiagCursor),
                ("pixmap_bottom_right", r.bottomRight(), Qt.CursorShape.SizeFDiagCursor),
                ("pixmap_top_right", r.topRight(), Qt.CursorShape.SizeBDiagCursor),
                ("pixmap_bottom_left", r.bottomLeft(), Qt.CursorShape.SizeBDiagCursor),
                ("pixmap_top", QPointF(r.center().x(), r.top()), Qt.CursorShape.SizeVerCursor),
                ("pixmap_bottom", QPointF(r.center().x(), r.bottom()), Qt.CursorShape.SizeVerCursor),
                ("pixmap_left", QPointF(r.left(), r.center().y()), Qt.CursorShape.SizeHorCursor),
                ("pixmap_right", QPointF(r.right(), r.center().y()), Qt.CursorShape.SizeHorCursor),
            ]
        if isinstance(item, (CustomRectItem, CustomEllipseItem)):
            r = item.rect()
            return [
                ("shape_tl", r.topLeft(), Qt.CursorShape.SizeFDiagCursor),
                ("shape_tr", r.topRight(), Qt.CursorShape.SizeBDiagCursor),
                ("shape_bl", r.bottomLeft(), Qt.CursorShape.SizeBDiagCursor),
                ("shape_br", r.bottomRight(), Qt.CursorShape.SizeFDiagCursor),
            ]
        if isinstance(item, CustomPolygonItem):
            return [("shape_br", item.boundingRect().bottomRight(), Qt.CursorShape.SizeFDiagCursor)]
        if isinstance(item, CustomPathItem):
            return [("path_br", item.boundingRect().bottomRight(), Qt.CursorShape.SizeFDiagCursor)]
        if isinstance(item, CustomLineItem):
            return [
                ("line_p1", item.line().p1(), Qt.CursorShape.CrossCursor),
                ("line_p2", item.line().p2(), Qt.CursorShape.CrossCursor),
            ]
        if isinstance(item, CustomTextItem):
            return [("text_scale", item.boundingRect().bottomRight(), Qt.CursorShape.SizeFDiagCursor)]
        if isinstance(item, NumberStampItem):
            rad = item.radius()
            return [("stamp_radius", QPointF(rad, rad), Qt.CursorShape.SizeFDiagCursor)]
        if isinstance(item, CalloutItem):
            r = item.box_rect()
            return [
                ("callout_tip", item.tip_point(), Qt.CursorShape.CrossCursor),
                ("callout_tl", r.topLeft(), Qt.CursorShape.SizeFDiagCursor),
                ("callout_tr", r.topRight(), Qt.CursorShape.SizeBDiagCursor),
                ("callout_bl", r.bottomLeft(), Qt.CursorShape.SizeBDiagCursor),
                ("callout_br", r.bottomRight(), Qt.CursorShape.SizeFDiagCursor),
            ]
        if isinstance(item, SpotlightItem):
            r = item.rect()
            return [
                ("shape_tl", r.topLeft(), Qt.CursorShape.SizeFDiagCursor),
                ("shape_tr", r.topRight(), Qt.CursorShape.SizeBDiagCursor),
                ("shape_bl", r.bottomLeft(), Qt.CursorShape.SizeBDiagCursor),
                ("shape_br", r.bottomRight(), Qt.CursorShape.SizeFDiagCursor),
            ]
        return []

    def drawForeground(self, painter, rect):
        """補助グリッドおよび選択アイテムのサイズ変更用ハンドルを描画"""
        super().drawForeground(painter, rect)
        if self._is_exporting:
            return

        # 補助グリッド（表示ONかつキャンバスが存在するときのみ）
        if self.show_grid and self.bg_item and not self.sceneRect().isEmpty():
            sr = self.sceneRect()
            clip = sr.intersected(rect)
            if not clip.isEmpty():
                step = max(10, int(self.grid_size))
                painter.save()
                grid_pen = QPen(QColor(0, 95, 184, 55), 0, Qt.PenStyle.DotLine)
                painter.setPen(grid_pen)
                x = math.floor(clip.left() / step) * step
                while x <= clip.right():
                    if sr.left() <= x <= sr.right():
                        painter.drawLine(QPointF(x, clip.top()), QPointF(x, clip.bottom()))
                    x += step
                y = math.floor(clip.top() / step) * step
                while y <= clip.bottom():
                    if sr.top() <= y <= sr.bottom():
                        painter.drawLine(QPointF(clip.left(), y), QPointF(clip.right(), y))
                    y += step
                painter.restore()

        if self.current_tool == "crop" and self.bg_item and not self.sceneRect().isEmpty():
            sr = self.sceneRect()
            scale = self.get_view_scale()
            painter.save()
            if self.crop_rect is not None and not self.crop_rect.isEmpty():
                cr = self.crop_rect.intersected(sr)
                dim = QPainterPath()
                dim.setFillRule(Qt.FillRule.OddEvenFill)
                dim.addRect(sr)
                dim.addRect(cr)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 0, 0, 120))
                painter.drawPath(dim)

                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(Qt.GlobalColor.white, 2.0 / scale))
                painter.drawRect(cr)
                painter.setPen(QPen(QColor(0, 120, 255), 1.5 / scale, Qt.PenStyle.DashLine))
                painter.drawRect(cr)

                hs = 10.0 / scale
                half = hs * 0.5
                painter.setBrush(QColor(0, 120, 255))
                painter.setPen(QPen(Qt.GlobalColor.white, 1.5 / scale))
                for pt in (cr.topLeft(), cr.topRight(), cr.bottomLeft(), cr.bottomRight()):
                    painter.drawRect(QRectF(pt.x() - half, pt.y() - half, hs, hs))

                # 選択サイズバッジ
                size_text = f"{int(round(cr.width()))} × {int(round(cr.height()))} px"
                font = QFont(DEFAULT_FONT_FAMILY)
                font.setPointSizeF(max(6.0, 10.0 / scale))
                font.setBold(True)
                painter.setFont(font)
                fm = QFontMetricsF(font)
                tw = fm.horizontalAdvance(size_text) + 12.0 / scale
                th = fm.height() + 6.0 / scale
                bx = cr.left()
                by = cr.top() - th - 4.0 / scale
                if by < sr.top():
                    by = cr.top() + 4.0 / scale
                badge = QRectF(bx, by, tw, th)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(0, 95, 184, 220))
                painter.drawRoundedRect(badge, 3.0 / scale, 3.0 / scale)
                painter.setPen(QPen(Qt.GlobalColor.white))
                painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, size_text)
            painter.restore()
            return

        if self.current_tool == "eyedropper" and self._eyedropper_hover_pos is not None and self._eyedropper_hover_color is not None:
            scale = self.get_view_scale()
            p = self._eyedropper_hover_pos
            c = self._eyedropper_hover_color
            off = 16.0 / scale
            box_w = 96.0 / scale
            box_h = 28.0 / scale
            box = QRectF(p.x() + off, p.y() - box_h - 6.0 / scale, box_w, box_h)
            painter.save()
            painter.setBrush(QColor(255, 255, 255, 240))
            painter.setPen(QPen(QColor("#555555"), 1.0 / scale))
            painter.drawRoundedRect(box, 4.0 / scale, 4.0 / scale)
            sw = 18.0 / scale
            swatch = QRectF(box.left() + 5.0 / scale, box.top() + 5.0 / scale, sw, sw)
            painter.setBrush(c)
            painter.drawRect(swatch)
            font = QFont(DEFAULT_FONT_FAMILY)
            font.setPointSizeF(max(5.0, 8.5 / scale))
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QPen(QColor("#222222")))
            text_r = QRectF(swatch.right() + 5.0 / scale, box.top(), box.right() - swatch.right() - 6.0 / scale, box.height())
            painter.drawText(text_r, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), c.name().upper())
            painter.restore()
            return

        if self.current_tool != "select":
            return

        selected = self.selectedItems()
        if not selected:
            return

        scale = self.get_view_scale()
        handle_size = 10.0 / scale
        half = handle_size * 0.5

        painter.save()
        painter.setPen(QPen(Qt.GlobalColor.white, 1.5 / scale))

        for item in selected:
            if item == self.bg_item or item == self.pending_text_item or isinstance(item, MarginHandleItem):
                continue
            for mode, local_pt, _ in self._get_item_handles(item):
                pt = item.mapToScene(local_pt)
                if mode == "callout_tip":
                    painter.setBrush(QColor(255, 140, 0))
                    painter.drawEllipse(QRectF(pt.x() - half * 1.15, pt.y() - half * 1.15, handle_size * 1.15, handle_size * 1.15))
                else:
                    painter.setBrush(QColor(0, 120, 255))
                    painter.drawRect(QRectF(pt.x() - half, pt.y() - half, handle_size, handle_size))
        painter.restore()

    def _capture_mosaic_region(self, scene_rect):
        """指定矩形領域の現在キャンバス表示をモザイク画像化する"""
        w = max(1, int(round(scene_rect.width())))
        h = max(1, int(round(scene_rect.height())))
        if w < 2 or h < 2:
            return QPixmap()

        prev_temp = self.temp_item
        if prev_temp is not None:
            prev_temp.setVisible(False)
        self._is_exporting = True
        self.set_margin_handles_visible(False)

        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.white)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.render(painter, QRectF(0, 0, w, h), scene_rect)
        painter.end()

        self._is_exporting = False
        self.set_margin_handles_visible(True)
        if prev_temp is not None:
            prev_temp.setVisible(True)

        block_size = max(8, int(round(self.pen_width * 2.5)))
        return create_mosaic_pixmap(QPixmap.fromImage(img), block_size=block_size)

    def mousePressEvent(self, event):
        # プレビュー中のテキスト配置確定/キャンセル
        if self.current_tool == "text" and self.pending_text_item is not None:
            if event.button() == Qt.MouseButton.LeftButton:
                self.pending_text_item.setPos(event.scenePos())
                placed = self.pending_text_item
                self.pending_text_item = None
                self.has_unsaved_changes = True
                self.save_state()
                if hasattr(self.parent(), "set_tool"):
                    self.parent().set_tool("select")
                self.clearSelection()
                placed.setSelected(True)
                event.accept()
                return
            if event.button() == Qt.MouseButton.RightButton:
                self.removeItem(self.pending_text_item)
                self.pending_text_item = None
                if hasattr(self.parent(), "set_tool"):
                    self.parent().set_tool("select")
                event.accept()
                return

        if self.current_tool == "margin":
            super().mousePressEvent(event)
            return

        if self.current_tool == "eyedropper":
            color = self._sample_eyedropper_color(event.scenePos())
            if color is not None:
                shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                target = "brush" if (event.button() == Qt.MouseButton.RightButton or shift) else "pen"
                main_win = self.parent()
                if hasattr(main_win, "apply_eyedropper_color"):
                    main_win.apply_eyedropper_color(color, target)
            event.accept()
            return

        if self.current_tool == "crop":
            if event.button() == Qt.MouseButton.RightButton:
                self.clear_crop_selection()
                event.accept()
                return
            if event.button() == Qt.MouseButton.LeftButton and self.bg_item:
                pos = event.scenePos()
                sr = self.sceneRect()
                clamped = QPointF(max(sr.left(), min(sr.right(), pos.x())), max(sr.top(), min(sr.bottom(), pos.y())))
                self._crop_drag_start = clamped
                handle_area = 16.0 / self.get_view_scale()

                mode = "new"
                if self.crop_rect is not None and not self.crop_rect.isEmpty():
                    cr = self.crop_rect
                    corners = [
                        ("tl", cr.topLeft()),
                        ("tr", cr.topRight()),
                        ("bl", cr.bottomLeft()),
                        ("br", cr.bottomRight()),
                    ]
                    for m, pt in corners:
                        if (pos - pt).manhattanLength() < handle_area:
                            mode = m
                            break
                    if mode == "new" and cr.contains(pos):
                        mode = "move"

                self._crop_drag_mode = mode
                if mode == "new":
                    self.crop_rect = QRectF(clamped, clamped)
                    self._crop_orig_rect = QRectF(self.crop_rect)
                else:
                    self._crop_orig_rect = QRectF(self.crop_rect)
                self.cropSelectionChanged.emit(False)
                self.invalidate(sr, QGraphicsScene.SceneLayer.ForegroundLayer)
                event.accept()
            return

        if self.current_tool == "select":
            if event.button() == Qt.MouseButton.RightButton:
                super().mousePressEvent(event)
                return

            pos = event.scenePos()
            self.resizing_item = None
            self.resize_mode = None
            self.was_modified = False

            handle_area = 16.0 / self.get_view_scale()
            for item in self.selectedItems():
                if item == self.bg_item or isinstance(item, MarginHandleItem):
                    continue
                for mode, local_pt, _ in self._get_item_handles(item):
                    pt = item.mapToScene(local_pt)
                    if (pos - pt).manhattanLength() < handle_area:
                        self.resizing_item = item
                        self.resize_mode = mode
                        if mode.startswith("pixmap_"):
                            self.start_scene_rect = item.rect().translated(item.pos())
                        elif mode == "shape_br":
                            if isinstance(item, CustomPolygonItem):
                                self.shape_anchor = item.polygon().boundingRect().topLeft()
                            else:
                                self.shape_anchor = item.rect().topLeft()
                        elif mode == "shape_tl":
                            self.shape_anchor = item.rect().bottomRight()
                        elif mode == "shape_tr":
                            self.shape_anchor = item.rect().bottomLeft()
                        elif mode == "shape_bl":
                            self.shape_anchor = item.rect().topRight()
                        elif mode == "callout_tl":
                            self.shape_anchor = item.box_rect().bottomRight()
                        elif mode == "callout_tr":
                            self.shape_anchor = item.box_rect().bottomLeft()
                        elif mode == "callout_bl":
                            self.shape_anchor = item.box_rect().topRight()
                        elif mode == "callout_br":
                            self.shape_anchor = item.box_rect().topLeft()
                        elif mode == "path_br":
                            self.shape_anchor = item.boundingRect().topLeft()
                            self.initial_path = QPainterPath(item.path())
                            self.initial_rect = QRectF(item.boundingRect())
                        elif mode == "text_scale":
                            self.initial_scale = item.scale()
                            self.start_point = pos
                            self.initial_dist_x = max(1.0, pos.x() - item.scenePos().x())
                            self.initial_dist_y = max(1.0, pos.y() - item.scenePos().y())
                        event.accept()
                        return

            super().mousePressEvent(event)
            # 実際の移動有無を正確に判定するため初期位置を記録
            self._drag_initial_positions = {
                it: QPointF(it.pos())
                for it in self.selectedItems()
                if it != self.bg_item and not isinstance(it, MarginHandleItem)
            }
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.scenePos()

            # 吹き出し（コールアウト）ドラッグ開始（始点＝指す先、終点＝吹き出しボックス）
            if self.current_tool == "callout":
                self._callout_drag_tip = QPointF(self.start_point)
                pen = QPen(self.current_pen_color)
                pen.setWidthF(max(2.0, min(self.pen_width, 8.0)))
                pen.setStyle(self.current_pen_style)
                pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
                bg_c = QColor(self.current_brush_color) if self.use_fill else QColor(Qt.GlobalColor.white)
                font = QFont(self.current_font_family)
                font.setPointSizeF(max(8.0, self.current_font_size))
                font.setBold(self.current_font_bold)
                font.setItalic(self.current_font_italic)
                init_box = QRectF(self.start_point.x() + 20.0, self.start_point.y() - 70.0, 140.0, 50.0)
                self.temp_item = CalloutItem(
                    init_box, self._callout_drag_tip, "コメント",
                    font, self.current_text_color, pen, QBrush(bg_c)
                )
                self.temp_item.setZValue(self.get_next_z_value())
                self.addItem(self.temp_item)
                return

            # 連番スタンプは1クリックで即配置
            if self.current_tool == "shape" and self.current_shape_type == "stamp":
                radius = max(14.0, min(60.0, self.current_font_size * 0.85))
                stamp = NumberStampItem(
                    self.next_stamp_number,
                    radius=radius,
                    bg_color=self.current_pen_color,
                    text_color=QColor("#FFFFFF")
                )
                stamp.setPos(self.start_point)
                stamp.setZValue(self.get_next_z_value())
                self.addItem(stamp)
                self.next_stamp_number += 1
                self.has_unsaved_changes = True
                self.save_state()
                self.start_point = None
                event.accept()
                return

            pen = QPen(self.current_pen_color)
            pen.setWidthF(self.pen_width)
            pen.setStyle(self.current_pen_style)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

            brush = self.get_current_brush()

            if self.current_tool == "line":
                if self.current_line_type == "line":
                    self.temp_item = CustomLineItem(QLineF(self.start_point, self.start_point), pen)
                elif self.current_line_type == "arrow":
                    self.temp_item = ArrowItem(QLineF(self.start_point, self.start_point), pen, double_ended=False)
                elif self.current_line_type == "double_arrow":
                    self.temp_item = ArrowItem(QLineF(self.start_point, self.start_point), pen, double_ended=True)
                elif self.current_line_type in ("freehand", "marker"):
                    draw_pen = QPen(pen)
                    if self.current_line_type == "marker":
                        mc = QColor(self.current_pen_color)
                        mc.setAlpha(95)
                        draw_pen.setColor(mc)
                        draw_pen.setWidthF(max(self.pen_width * 2.5, 16.0))
                        draw_pen.setStyle(Qt.PenStyle.SolidLine)
                    self.current_path = QPainterPath(self.start_point)
                    self._last_freehand_point = self.start_point
                    self.temp_item = CustomPathItem(self.current_path, draw_pen)
                    if self.current_line_type == "freehand":
                        self.temp_item.setBrush(brush)
                if self.temp_item is not None:
                    self.temp_item.setZValue(self.get_next_z_value())
                    self.addItem(self.temp_item)

            elif self.current_tool == "shape":
                if self.current_shape_type == "rect":
                    self.temp_item = CustomRectItem(QRectF(self.start_point, self.start_point), pen, corner_radius=0.0)
                    self.temp_item.setBrush(brush)
                elif self.current_shape_type == "rounded_rect":
                    self.temp_item = CustomRectItem(QRectF(self.start_point, self.start_point), pen, corner_radius=16.0)
                    self.temp_item.setBrush(brush)
                elif self.current_shape_type == "ellipse":
                    self.temp_item = CustomEllipseItem(QRectF(self.start_point, self.start_point), pen)
                    self.temp_item.setBrush(brush)
                elif self.current_shape_type == "triangle":
                    self.temp_item = CustomPolygonItem(
                        QPolygonF([self.start_point, self.start_point, self.start_point]), pen
                    )
                    self.temp_item.setBrush(brush)
                elif self.current_shape_type == "mosaic":
                    preview_pen = QPen(QColor("#005FB8"), max(1.5, 2.0 / self.get_view_scale()), Qt.PenStyle.DashLine)
                    self.temp_item = CustomRectItem(QRectF(self.start_point, self.start_point), preview_pen)
                    self.temp_item.setBrush(QBrush(QColor(0, 95, 184, 35)))
                elif self.current_shape_type == "spotlight":
                    self.temp_item = SpotlightItem(QRectF(self.start_point, self.start_point), pen)
                if self.temp_item is not None:
                    self.temp_item.setZValue(self.get_next_z_value())
                    self.addItem(self.temp_item)

    def _sample_eyedropper_color(self, scene_pos):
        if self._eyedropper_image is None or self.bg_item is None:
            return None
        sr = self.sceneRect()
        if sr.isEmpty():
            return None
        ix = int(round(scene_pos.x() - sr.left()))
        iy = int(round(scene_pos.y() - sr.top()))
        if 0 <= ix < self._eyedropper_image.width() and 0 <= iy < self._eyedropper_image.height():
            return self._eyedropper_image.pixelColor(ix, iy)
        return None

    def mouseDoubleClickEvent(self, event):
        if self.current_tool == "crop" and self.crop_rect is not None and self.crop_rect.width() >= 10 and self.crop_rect.height() >= 10:
            main_win = self.parent()
            if hasattr(main_win, "confirm_crop"):
                main_win.confirm_crop()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        self.mouseSceneMoved.emit(event.scenePos())

        if self.current_tool == "text" and self.pending_text_item is not None:
            self.pending_text_item.setPos(event.scenePos())
            event.accept()
            return

        if self.current_tool == "margin":
            super().mouseMoveEvent(event)
            return

        if self.current_tool == "eyedropper":
            pos = event.scenePos()
            color = self._sample_eyedropper_color(pos)
            self._eyedropper_hover_pos = pos if color is not None else None
            self._eyedropper_hover_color = color
            if color is not None:
                self.statusMessageRequested.emit(
                    f"スポイト: {color.name().upper()} (R:{color.red()}, G:{color.green()}, B:{color.blue()})  "
                    f"[左クリック: 線/枠色 / 右クリック: 背景/塗色]",
                    0,
                )
            self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.ForegroundLayer)
            event.accept()
            return

        if self.current_tool == "crop":
            sr = self.sceneRect()
            if self._crop_drag_mode is not None and self._crop_drag_start is not None:
                pos = event.scenePos()
                clamped = QPointF(max(sr.left(), min(sr.right(), pos.x())), max(sr.top(), min(sr.bottom(), pos.y())))
                shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                if self._crop_drag_mode == "new":
                    target = snap_square_point(self._crop_drag_start, clamped) if shift_held else clamped
                    self.crop_rect = QRectF(self._crop_drag_start, target).normalized().intersected(sr)
                elif self._crop_drag_mode == "move":
                    delta = clamped - self._crop_drag_start
                    r = QRectF(self._crop_orig_rect)
                    dx = max(sr.left() - r.left(), min(sr.right() - r.right(), delta.x()))
                    dy = max(sr.top() - r.top(), min(sr.bottom() - r.bottom(), delta.y()))
                    r.translate(dx, dy)
                    self.crop_rect = r
                else:
                    anchors = {
                        "tl": self._crop_orig_rect.bottomRight(),
                        "tr": self._crop_orig_rect.bottomLeft(),
                        "bl": self._crop_orig_rect.topRight(),
                        "br": self._crop_orig_rect.topLeft(),
                    }
                    anchor = anchors[self._crop_drag_mode]
                    target = snap_square_point(anchor, clamped) if shift_held else clamped
                    self.crop_rect = QRectF(anchor, target).normalized().intersected(sr)
                self.invalidate(sr, QGraphicsScene.SceneLayer.ForegroundLayer)
                event.accept()
                return
            elif self.crop_rect is not None and self.views():
                pos = event.scenePos()
                handle_area = 16.0 / self.get_view_scale()
                cr = self.crop_rect
                cursor = Qt.CursorShape.CrossCursor
                if (pos - cr.topLeft()).manhattanLength() < handle_area or (pos - cr.bottomRight()).manhattanLength() < handle_area:
                    cursor = Qt.CursorShape.SizeFDiagCursor
                elif (pos - cr.topRight()).manhattanLength() < handle_area or (pos - cr.bottomLeft()).manhattanLength() < handle_area:
                    cursor = Qt.CursorShape.SizeBDiagCursor
                elif cr.contains(pos):
                    cursor = Qt.CursorShape.SizeAllCursor
                self.views()[0].viewport().setCursor(cursor)
            return

        if self.current_tool == "select":
            if event.buttons() == Qt.MouseButton.NoButton:
                pos = event.scenePos()
                handle_area = 16.0 / self.get_view_scale()
                on_handle = False
                cursor_shape = Qt.CursorShape.ArrowCursor

                for item in self.selectedItems():
                    if item == self.bg_item or isinstance(item, MarginHandleItem):
                        continue
                    for _, local_pt, cursor in self._get_item_handles(item):
                        pt = item.mapToScene(local_pt)
                        if (pos - pt).manhattanLength() < handle_area:
                            on_handle = True
                            cursor_shape = cursor
                            break
                    if on_handle:
                        break

                if not on_handle:
                    transform = self.views()[0].transform() if self.views() else QTransform()
                    item_under_mouse = self.itemAt(pos, transform)
                    if item_under_mouse and item_under_mouse != self.bg_item and not isinstance(item_under_mouse, MarginHandleItem):
                        cursor_shape = (
                            Qt.CursorShape.SizeAllCursor
                            if item_under_mouse.isSelected()
                            else Qt.CursorShape.PointingHandCursor
                        )

                if self.views():
                    self.views()[0].viewport().setCursor(cursor_shape)

                super().mouseMoveEvent(event)
                return

            if self.resizing_item is not None:
                pos = event.scenePos()
                item = self.resizing_item
                local_pos = item.mapFromScene(pos)
                shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

                if self.resize_mode.startswith("pixmap_"):
                    mode = self.resize_mode[len("pixmap_"):]
                    start_rect = self.start_scene_rect
                    r = start_rect.width() / max(1.0, start_rect.height())
                    min_dim = 8.0

                    if mode == "bottom_right":
                        anchor = start_rect.topLeft()
                        dx = pos.x() - anchor.x()
                        dy = pos.y() - anchor.y()
                        val = max(min_dim, abs(dx), abs(dy) * r)
                        sx = 1.0 if dx >= 0 else -1.0
                        sy = 1.0 if dy >= 0 else -1.0
                        new_scene_rect = QRectF(anchor, QPointF(anchor.x() + sx * val, anchor.y() + sy * val / r)).normalized()
                    elif mode == "top_left":
                        anchor = start_rect.bottomRight()
                        dx = anchor.x() - pos.x()
                        dy = anchor.y() - pos.y()
                        val = max(min_dim, abs(dx), abs(dy) * r)
                        sx = 1.0 if dx >= 0 else -1.0
                        sy = 1.0 if dy >= 0 else -1.0
                        new_scene_rect = QRectF(anchor, QPointF(anchor.x() - sx * val, anchor.y() - sy * val / r)).normalized()
                    elif mode == "top_right":
                        anchor = start_rect.bottomLeft()
                        dx = pos.x() - anchor.x()
                        dy = anchor.y() - pos.y()
                        val = max(min_dim, abs(dx), abs(dy) * r)
                        sx = 1.0 if dx >= 0 else -1.0
                        sy = 1.0 if dy >= 0 else -1.0
                        new_scene_rect = QRectF(anchor, QPointF(anchor.x() + sx * val, anchor.y() - sy * val / r)).normalized()
                    elif mode == "bottom_left":
                        anchor = start_rect.topRight()
                        dx = anchor.x() - pos.x()
                        dy = pos.y() - anchor.y()
                        val = max(min_dim, abs(dx), abs(dy) * r)
                        sx = 1.0 if dx >= 0 else -1.0
                        sy = 1.0 if dy >= 0 else -1.0
                        new_scene_rect = QRectF(anchor, QPointF(anchor.x() - sx * val, anchor.y() + sy * val / r)).normalized()
                    elif mode == "right":
                        new_w = pos.x() - start_rect.left()
                        if abs(new_w) < min_dim:
                            new_w = min_dim if new_w >= 0 else -min_dim
                        new_scene_rect = QRectF(start_rect.left(), start_rect.top(), new_w, start_rect.height()).normalized()
                    elif mode == "left":
                        new_w = start_rect.right() - pos.x()
                        if abs(new_w) < min_dim:
                            new_w = min_dim if new_w >= 0 else -min_dim
                        new_scene_rect = QRectF(start_rect.right() - new_w, start_rect.top(), new_w, start_rect.height()).normalized()
                    elif mode == "bottom":
                        new_h = pos.y() - start_rect.top()
                        if abs(new_h) < min_dim:
                            new_h = min_dim if new_h >= 0 else -min_dim
                        new_scene_rect = QRectF(start_rect.left(), start_rect.top(), start_rect.width(), new_h).normalized()
                    else:  # top
                        new_h = start_rect.bottom() - pos.y()
                        if abs(new_h) < min_dim:
                            new_h = min_dim if new_h >= 0 else -min_dim
                        new_scene_rect = QRectF(start_rect.left(), start_rect.bottom() - new_h, start_rect.width(), new_h).normalized()

                    item.setPos(new_scene_rect.topLeft())
                    item.setRect(QRectF(0, 0, new_scene_rect.width(), new_scene_rect.height()))

                elif self.resize_mode in ("shape_br", "shape_tl", "shape_tr", "shape_bl"):
                    target_local = snap_square_point(self.shape_anchor, local_pos) if shift_held else local_pos
                    rect = QRectF(self.shape_anchor, target_local).normalized()
                    if isinstance(item, (CustomRectItem, CustomEllipseItem, SpotlightItem)):
                        item.setRect(rect)
                    elif isinstance(item, CustomPolygonItem):
                        p1 = QPointF(rect.center().x(), rect.top())
                        p2 = QPointF(rect.left(), rect.bottom())
                        p3 = QPointF(rect.right(), rect.bottom())
                        item.setPolygon(QPolygonF([p1, p2, p3]))

                elif self.resize_mode == "callout_tip":
                    item.setTipPoint(local_pos)

                elif self.resize_mode in ("callout_br", "callout_tl", "callout_tr", "callout_bl"):
                    rect = QRectF(self.shape_anchor, local_pos).normalized()
                    item.setBoxRect(rect)

                elif self.resize_mode == "path_br":
                    rect = QRectF(self.shape_anchor, local_pos).normalized()
                    w = max(1.0, self.initial_rect.width())
                    h = max(1.0, self.initial_rect.height())
                    sx = max(0.05, rect.width() / w)
                    sy = max(0.05, rect.height() / h)
                    t = QTransform()
                    t.translate(self.shape_anchor.x(), self.shape_anchor.y())
                    t.scale(sx, sy)
                    t.translate(-self.shape_anchor.x(), -self.shape_anchor.y())
                    item.setPath(t.map(self.initial_path))

                elif self.resize_mode == "line_p1":
                    line = item.line()
                    target = snap_line_point(line.p2(), local_pos) if shift_held else local_pos
                    line.setP1(target)
                    item.setLine(line)

                elif self.resize_mode == "line_p2":
                    line = item.line()
                    target = snap_line_point(line.p1(), local_pos) if shift_held else local_pos
                    line.setP2(target)
                    item.setLine(line)

                elif self.resize_mode == "text_scale":
                    current_dist_x = pos.x() - item.scenePos().x()
                    current_dist_y = pos.y() - item.scenePos().y()
                    factor = max(current_dist_x / self.initial_dist_x, current_dist_y / self.initial_dist_y)
                    new_scale = max(0.15, min(20.0, self.initial_scale * factor))
                    item.setScale(new_scale)

                elif self.resize_mode == "stamp_radius":
                    dist = math.hypot(local_pos.x(), local_pos.y()) / math.sqrt(2.0)
                    item.setRadius(max(10.0, min(150.0, dist)))

                self.has_unsaved_changes = True
                self.was_modified = True
                self.invalidate_handles()
                event.accept()
                return

            super().mouseMoveEvent(event)
            if event.buttons() == Qt.MouseButton.LeftButton and self._drag_initial_positions:
                self.invalidate_handles()
            return

        if self.start_point is not None and self.temp_item is not None:
            end_point = event.scenePos()
            shift_held = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)

            if self.current_tool == "line":
                if self.current_line_type in ("line", "arrow", "double_arrow"):
                    target = snap_line_point(self.start_point, end_point) if shift_held else end_point
                    self.temp_item.setLine(QLineF(self.start_point, target))
                elif self.current_line_type in ("freehand", "marker"):
                    if shift_held:
                        # Shift押下時は始点から直線マーカー/直線フリーハンドとして描画
                        target = snap_line_point(self.start_point, end_point)
                        straight_path = QPainterPath(self.start_point)
                        straight_path.lineTo(target)
                        self.current_path = straight_path
                        self._last_freehand_point = target
                        self.temp_item.setPath(self.current_path)
                    else:
                        # 頂点間引きで軽量＆滑らかに描画
                        min_step = max(1.5, 2.5 / self.get_view_scale())
                        last = self._last_freehand_point or self.start_point
                        dx = end_point.x() - last.x()
                        dy = end_point.y() - last.y()
                        if dx * dx + dy * dy >= min_step * min_step:
                            self.current_path.lineTo(end_point)
                            self._last_freehand_point = end_point
                            self.temp_item.setPath(self.current_path)

            elif self.current_tool == "callout" and isinstance(self.temp_item, CalloutItem):
                box_w = 160.0
                box_h = 56.0
                box = QRectF(end_point.x() - box_w * 0.5, end_point.y() - box_h * 0.5, box_w, box_h)
                self.temp_item.setBoxRect(box)
                self.temp_item.setTipPoint(self._callout_drag_tip)

            elif self.current_tool == "shape":
                target = snap_square_point(self.start_point, end_point) if shift_held else end_point
                rect = QRectF(self.start_point, target).normalized()
                if self.current_shape_type in ("rect", "rounded_rect", "ellipse", "mosaic", "spotlight"):
                    self.temp_item.setRect(rect)
                elif self.current_shape_type == "triangle":
                    p1 = QPointF(rect.center().x(), rect.top())
                    p2 = QPointF(rect.left(), rect.bottom())
                    p3 = QPointF(rect.right(), rect.bottom())
                    self.temp_item.setPolygon(QPolygonF([p1, p2, p3]))

    def mouseReleaseEvent(self, event):
        if self.current_tool == "margin":
            super().mouseReleaseEvent(event)
            return

        if self.current_tool == "eyedropper":
            event.accept()
            return

        if self.current_tool == "crop":
            if self._crop_drag_mode is not None:
                self._crop_drag_mode = None
                self._crop_drag_start = None
                self._crop_orig_rect = None
                valid = bool(
                    self.crop_rect is not None
                    and self.crop_rect.width() >= 10.0
                    and self.crop_rect.height() >= 10.0
                )
                if not valid:
                    self.crop_rect = None
                self.cropSelectionChanged.emit(valid)
                self.invalidate(self.sceneRect(), QGraphicsScene.SceneLayer.ForegroundLayer)
                event.accept()
            return

        if self.current_tool == "select":
            if self.resizing_item is not None:
                if self.was_modified:
                    self.save_state()
                    self.was_modified = False
                self.resizing_item = None
                self.resize_mode = None
                self.shape_anchor = None
                self.initial_path = None
                self.initial_rect = None
                self.start_scene_rect = None
                self.invalidate_handles()
                event.accept()
                return

            super().mouseReleaseEvent(event)

            # 実際に位置が変わったアイテムがある場合のみ履歴に保存
            moved = False
            for it, old_pos in self._drag_initial_positions.items():
                if it.scene() is self:
                    diff = it.pos() - old_pos
                    if abs(diff.x()) > 0.01 or abs(diff.y()) > 0.01:
                        moved = True
                        break
            self._drag_initial_positions.clear()

            if moved:
                self.has_unsaved_changes = True
                self.save_state()
                self.invalidate_handles()
            return

        if event.button() == Qt.MouseButton.LeftButton and self.temp_item is not None:
            finished_item = self.temp_item
            self.temp_item = None
            self.start_point = None
            self._last_freehand_point = None

            # 吹き出し（コールアウト）の確定処理（テキスト入力ダイアログを表示）
            if self.current_tool == "callout" and isinstance(finished_item, CalloutItem):
                self._callout_drag_tip = None
                dlg = QuickTextDialog(
                    self.parent(),
                    title="吹き出しテキスト入力",
                    prompt="吹き出しに表示するコメントを入力してください (Ctrl+Enterで確定):",
                    recent_texts=self.recent_texts,
                    show_bg_option=False,
                )
                if dlg.exec() == QDialog.DialogCode.Accepted:
                    txt = dlg.get_text()
                    if txt:
                        self.remember_recent_text(txt)
                        finished_item.setText(txt)
                        finished_item.fit_box_to_text()
                        finished_item.setFlags(
                            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                            | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
                        )
                        self.has_unsaved_changes = True
                        self.save_state()
                        if hasattr(self.parent(), "set_tool"):
                            self.parent().set_tool("select")
                        self.clearSelection()
                        finished_item.setSelected(True)
                        self.invalidate_handles()
                        return
                self.removeItem(finished_item)
                return

            # モザイクツールの確定処理
            if self.current_tool == "shape" and self.current_shape_type == "mosaic":
                mosaic_rect = finished_item.rect()
                self.removeItem(finished_item)
                if mosaic_rect.width() >= 4.0 and mosaic_rect.height() >= 4.0:
                    mosaic_pix = self._capture_mosaic_region(mosaic_rect)
                    if not mosaic_pix.isNull():
                        patch = CustomPixmapItem(mosaic_pix, QRectF(0, 0, mosaic_rect.width(), mosaic_rect.height()))
                        patch.setPos(mosaic_rect.topLeft())
                        patch.setZValue(self.get_next_z_value())
                        self.addItem(patch)
                        self.has_unsaved_changes = True
                        self.save_state()
                self.current_path = None
                return

            # スポットライトは他の注釈が暗くならないよう背景のすぐ上へ配置
            if self.current_tool == "shape" and isinstance(finished_item, SpotlightItem):
                r = finished_item.rect()
                if r.width() < 6.0 and r.height() < 6.0:
                    self.removeItem(finished_item)
                    return
                others = [it for it in self.annotation_items() if it != finished_item]
                finished_item.setZValue(1.0)
                for idx, other in enumerate(others, start=2):
                    other.setZValue(float(idx))
                self.has_unsaved_changes = True
                self.save_state()
                self.update()
                return

            # 誤クリックによる0サイズゴミアイテムを自動除外
            is_trivial = False
            if isinstance(finished_item, CustomLineItem):
                if finished_item.line().length() < 2.0:
                    is_trivial = True
            elif isinstance(finished_item, (CustomRectItem, CustomEllipseItem)):
                r = finished_item.rect()
                if r.width() < 2.0 and r.height() < 2.0:
                    is_trivial = True
            elif isinstance(finished_item, CustomPolygonItem):
                r = finished_item.boundingRect()
                if r.width() < 2.0 and r.height() < 2.0:
                    is_trivial = True
            elif isinstance(finished_item, CustomPathItem):
                # クリックのみの場合は点として打てるよう極小セグメントを追加
                if self.current_path is not None and self.current_path.elementCount() <= 1:
                    pt = self.current_path.currentPosition()
                    self.current_path.lineTo(pt + QPointF(0.2, 0.2))
                    finished_item.setPath(self.current_path)

            self.current_path = None

            if is_trivial:
                self.removeItem(finished_item)
                return

            finished_item.setFlags(
                QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
                | QGraphicsItem.GraphicsItemFlag.ItemIsMovable
            )
            self.has_unsaved_changes = True
            self.save_state()

    def delete_selected_items(self):
        """選択されているアイテムを削除する"""
        deleted = False
        for item in list(self.selectedItems()):
            if item != self.bg_item and not isinstance(item, MarginHandleItem):
                self.removeItem(item)
                deleted = True
        if deleted:
            self.has_unsaved_changes = True
            self.save_state()
            self.invalidate_handles()

    def select_all_items(self):
        """背景以外の全注釈を選択する"""
        for item in self.annotation_items():
            item.setSelected(True)
        self.invalidate_handles()

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.pending_text_item is not None:
                self.removeItem(self.pending_text_item)
                self.pending_text_item = None
            self.clear_crop_selection()
            self.clear_eyedropper()
            self.clearSelection()
            if hasattr(self.parent(), "set_tool"):
                self.parent().set_tool("select")
            event.accept()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.current_tool == "crop" and self.crop_rect is not None and self.crop_rect.width() >= 10 and self.crop_rect.height() >= 10:
                main_win = self.parent()
                if hasattr(main_win, "confirm_crop"):
                    main_win.confirm_crop()
                event.accept()
                return

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected_items()
            event.accept()
            return

        # 矢印キーで選択アイテムを微調整移動（Shift併用で10px）
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            selected = [
                it for it in self.selectedItems()
                if it != self.bg_item and not isinstance(it, MarginHandleItem)
            ]
            if selected:
                step = 10.0 if (event.modifiers() & Qt.KeyboardModifier.ShiftModifier) else 1.0
                dx = -step if key == Qt.Key.Key_Left else (step if key == Qt.Key.Key_Right else 0.0)
                dy = -step if key == Qt.Key.Key_Up else (step if key == Qt.Key.Key_Down else 0.0)
                for it in selected:
                    it.moveBy(dx, dy)
                self.has_unsaved_changes = True
                self._arrow_key_moved = True
                self.invalidate_handles()
                event.accept()
                return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            if not event.isAutoRepeat() and self._arrow_key_moved:
                self._arrow_key_moved = False
                self.save_state()
        super().keyReleaseEvent(event)

    def contextMenuEvent(self, event):
        if self.current_tool != "select":
            super().contextMenuEvent(event)
            return

        pos = event.scenePos()
        transform = self.views()[0].transform() if self.views() else QTransform()
        target_item = self.itemAt(pos, transform)
        if target_item == self.bg_item or isinstance(target_item, MarginHandleItem):
            target_item = None

        if target_item is not None and not target_item.isSelected():
            self.clearSelection()
            target_item.setSelected(True)

        selected = [
            it for it in self.selectedItems()
            if it != self.bg_item and not isinstance(it, MarginHandleItem)
        ]
        has_target = target_item is not None or bool(selected)

        menu = QMenu()

        bring_front_action = menu.addAction("⏫ 最前面に配置")
        bring_front_action.setEnabled(target_item is not None)
        send_back_action = menu.addAction("⏬ 最背面に配置")
        send_back_action.setEnabled(target_item is not None)

        menu.addSeparator()

        copy_action = menu.addAction("コピー (Ctrl+C)")
        copy_action.setEnabled(has_target)
        duplicate_action = menu.addAction("複製 (Ctrl+D)")
        duplicate_action.setEnabled(has_target)
        paste_action = menu.addAction("貼り付け (Ctrl+V)")
        clipboard = QGuiApplication.clipboard()
        has_clip_image = bool(clipboard and clipboard.mimeData() and clipboard.mimeData().hasImage())
        paste_action.setEnabled(bool(self.copied_items) or has_clip_image)

        line_style_actions = {}
        if target_item is not None and isinstance(
            target_item,
            (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, CalloutItem, SpotlightItem),
        ):
            menu.addSeparator()
            style_menu = menu.addMenu("線スタイル")
            for label, st in (("実線", Qt.PenStyle.SolidLine), ("破線", Qt.PenStyle.DashLine), ("点線", Qt.PenStyle.DotLine)):
                act = style_menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(target_item.pen().style() == st)
                line_style_actions[act] = st

        edit_text_action = None
        edit_font_action = None
        if isinstance(target_item, CustomTextItem):
            menu.addSeparator()
            edit_text_action = menu.addAction("テキストを編集")
            edit_font_action = menu.addAction("フォント・書式を変更...")

        edit_callout_action = None
        edit_callout_font_action = None
        fit_callout_action = None
        if isinstance(target_item, CalloutItem):
            menu.addSeparator()
            edit_callout_action = menu.addAction("吹き出しの文字を編集")
            edit_callout_font_action = menu.addAction("フォント・書式を変更...")
            fit_callout_action = menu.addAction("枠サイズを文字に合わせる")

        spotlight_dim_actions = {}
        if isinstance(target_item, SpotlightItem):
            menu.addSeparator()
            dim_menu = menu.addMenu("周囲の暗さ")
            for label, alpha in (("薄め", 70), ("標準", 115), ("濃いめ", 165)):
                act = dim_menu.addAction(label)
                act.setCheckable(True)
                act.setChecked(abs(target_item.dim_alpha() - alpha) < 20)
                spotlight_dim_actions[act] = alpha

        edit_stamp_action = None
        if isinstance(target_item, NumberStampItem):
            menu.addSeparator()
            edit_stamp_action = menu.addAction("番号を変更...")

        reset_aspect_action = None
        if isinstance(target_item, CustomPixmapItem):
            menu.addSeparator()
            reset_aspect_action = menu.addAction("🔄 縦横比を元に戻す")

        menu.addSeparator()
        delete_action = menu.addAction("🗑️ 削除 (Del)")
        delete_action.setEnabled(has_target)

        action = menu.exec(event.screenPos())
        if action is None:
            return

        if action == bring_front_action:
            self.bring_to_front(target_item)
        elif action == send_back_action:
            self.send_to_back(target_item)
        elif action == copy_action:
            self.copy_selected_items(fallback_item=target_item)
        elif action == duplicate_action:
            self.duplicate_selected_items()
        elif action == paste_action:
            main_win = self.parent()
            if hasattr(main_win, "smart_paste"):
                main_win.smart_paste(pos)
            else:
                self.paste_items(pos)
        elif action in line_style_actions:
            st = line_style_actions[action]
            self.apply_pen_style_to_selected(st)
        elif edit_text_action and action == edit_text_action:
            self.edit_text_item(target_item)
        elif edit_font_action and action == edit_font_action:
            self.edit_text_font(target_item)
        elif edit_callout_action and action == edit_callout_action:
            self.edit_callout_item(target_item)
        elif edit_callout_font_action and action == edit_callout_font_action:
            self.edit_callout_font(target_item)
        elif fit_callout_action and action == fit_callout_action:
            target_item.fit_box_to_text()
            self.has_unsaved_changes = True
            self.save_state()
            self.invalidate_handles()
        elif action in spotlight_dim_actions:
            target_item.setDimAlpha(spotlight_dim_actions[action])
            self.has_unsaved_changes = True
            self.save_state()
        elif edit_stamp_action and action == edit_stamp_action:
            self.edit_stamp_number(target_item)
        elif reset_aspect_action and action == reset_aspect_action:
            self.reset_pixmap_aspect(target_item)
        elif action == delete_action:
            self.delete_selected_items()

    def apply_pen_style_to_selected(self, pen_style):
        self.current_pen_style = pen_style
        changed = False
        for item in self.selectedItems():
            if isinstance(
                item,
                (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, CalloutItem, SpotlightItem),
            ):
                pen = QPen(item.pen())
                pen.setStyle(pen_style)
                item.setPen(pen)
                changed = True
            elif isinstance(item, CustomTextItem) and item.pen().style() != Qt.PenStyle.NoPen:
                pen = QPen(item.pen())
                pen.setStyle(pen_style)
                item.setPen(pen)
                changed = True
        if changed:
            self.has_unsaved_changes = True
            self.save_state()

    def reset_pixmap_aspect(self, item):
        """挿入された画像の縦横比をオリジナルに合わせて復元する"""
        if isinstance(item, CustomPixmapItem):
            orig_w = float(item.original_pixmap.width())
            orig_h = float(item.original_pixmap.height())
            if orig_w > 0 and orig_h > 0:
                current_rect = item.rect()
                new_h = current_rect.width() * (orig_h / orig_w)
                item.setRect(QRectF(current_rect.left(), current_rect.top(), current_rect.width(), new_h))
                self.has_unsaved_changes = True
                self.save_state()
                self.invalidate_handles()

    def copy_selected_items(self, fallback_item=None):
        """選択中アイテムをすべてコピーする"""
        targets = [
            it for it in self.selectedItems()
            if it != self.bg_item and not isinstance(it, MarginHandleItem)
        ]
        if not targets and fallback_item is not None:
            targets = [fallback_item]
        targets.sort(key=lambda it: it.zValue())

        serialized = []
        for it in targets:
            d = self._serialize_item_to_dict(it)
            if d is not None:
                d["_scene_origin"] = QPointF(it.sceneBoundingRect().topLeft())
                serialized.append(d)

        if serialized:
            self.copied_items = serialized
            main_win = self.parent()
            if hasattr(main_win, "mark_clipboard_source_scene"):
                main_win.mark_clipboard_source_scene()
            return True
        return False

    def paste_items(self, pos=None):
        """コピーしたアイテム群を指定位置（省略時は少しずらした位置）に貼り付ける"""
        if not self.copied_items:
            return False

        self.clearSelection()
        min_x = min(d["_scene_origin"].x() for d in self.copied_items)
        min_y = min(d["_scene_origin"].y() for d in self.copied_items)

        if pos is None:
            offset = QPointF(24.0, 24.0)
        else:
            offset = QPointF(pos.x() - min_x, pos.y() - min_y)

        pasted = []
        for data in self.copied_items:
            new_item = self._create_item_from_dict(data)
            if new_item is not None:
                new_item.moveBy(offset.x(), offset.y())
                new_item.setZValue(self.get_next_z_value())
                self.addItem(new_item)
                new_item.setSelected(True)
                pasted.append(new_item)

        if pasted:
            # 連続ペースト時に重ならないよう元オフセットを更新
            if pos is None:
                for d in self.copied_items:
                    d["pos"] = QPointF(d["pos"]) + offset
                    d["_scene_origin"] = QPointF(d["_scene_origin"]) + offset
            self.has_unsaved_changes = True
            self.save_state()
            self.invalidate_handles()
            return True
        return False

    def duplicate_selected_items(self):
        """選択中アイテムを即複製する"""
        if self.copy_selected_items():
            self.paste_items(pos=None)

    def edit_text_item(self, item):
        if isinstance(item, CustomTextItem):
            current_text = item.toPlainText()
            dlg = QuickTextDialog(
                self.parent(),
                title="テキストの編集",
                prompt="文字を変更してください (Ctrl+Enterで確定):",
                initial_text=current_text,
                recent_texts=self.recent_texts,
                show_bg_option=False,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_text = dlg.get_text()
                if new_text and new_text != current_text:
                    self.remember_recent_text(new_text)
                    item.setPlainText(new_text)
                    self.has_unsaved_changes = True
                    self.save_state()
                    self.invalidate_handles()

    def edit_callout_item(self, item):
        if isinstance(item, CalloutItem):
            current_text = item.text()
            dlg = QuickTextDialog(
                self.parent(),
                title="吹き出しの文字を編集",
                prompt="コメントを変更してください (Ctrl+Enterで確定):",
                initial_text=current_text,
                recent_texts=self.recent_texts,
                show_bg_option=False,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted:
                new_text = dlg.get_text()
                if new_text and new_text != current_text:
                    self.remember_recent_text(new_text)
                    item.setText(new_text)
                    item.fit_box_to_text()
                    self.has_unsaved_changes = True
                    self.save_state()
                    self.invalidate_handles()

    def edit_callout_font(self, item):
        if isinstance(item, CalloutItem):
            font, ok = QFontDialog.getFont(item.font(), self.parent(), "フォントと書式を選択")
            if ok:
                item.setFont(font)
                self.current_font_family = font.family()
                if font.pointSizeF() > 0:
                    self.current_font_size = font.pointSizeF()
                self.current_font_bold = font.bold()
                self.current_font_italic = font.italic()
                self.has_unsaved_changes = True
                self.save_state()
                self.invalidate_handles()

    def edit_text_font(self, item):
        if isinstance(item, CustomTextItem):
            font, ok = QFontDialog.getFont(item.font(), self.parent(), "フォントと書式を選択")
            if ok:
                item.setFont(font)
                self.current_font_family = font.family()
                if font.pointSizeF() > 0:
                    self.current_font_size = font.pointSizeF()
                self.current_font_bold = font.bold()
                self.current_font_italic = font.italic()
                self.has_unsaved_changes = True
                self.save_state()
                self.invalidate_handles()

    def edit_stamp_number(self, item):
        if isinstance(item, NumberStampItem):
            val, ok = QInputDialog.getInt(
                self.parent(), "スタンプ番号の変更", "表示する番号を入力してください:",
                item.number, 1, 999, 1
            )
            if ok and val != item.number:
                item.setNumber(val)
                self.has_unsaved_changes = True
                self.save_state()


def color_to_hex(color):
    return color.name(QColor.NameFormat.HexArgb)


def hex_to_color(hex_str):
    return QColor(hex_str)


def serialize_pen(pen):
    return {
        "color": color_to_hex(pen.color()),
        "width": pen.widthF(),
        "style": pen.style().value if hasattr(pen.style(), "value") else int(pen.style()),
        "cap": pen.capStyle().value if hasattr(pen.capStyle(), "value") else int(pen.capStyle()),
        "join": pen.joinStyle().value if hasattr(pen.joinStyle(), "value") else int(pen.joinStyle()),
    }


def deserialize_pen(data):
    pen = QPen(hex_to_color(data.get("color", "#ffff0000")))
    pen.setWidthF(float(data.get("width", 5.0)))
    try:
        pen.setStyle(Qt.PenStyle(data.get("style", 1)))
    except Exception:
        pen.setStyle(Qt.PenStyle.SolidLine)
    try:
        pen.setCapStyle(Qt.PenCapStyle(data.get("cap", 0x20)))
    except Exception:
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    try:
        pen.setJoinStyle(Qt.PenJoinStyle(data.get("join", 0x80)))
    except Exception:
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


def serialize_brush(brush):
    return {
        "color": color_to_hex(brush.color()),
        "style": brush.style().value if hasattr(brush.style(), "value") else int(brush.style()),
    }


def deserialize_brush(data):
    brush = QBrush(hex_to_color(data.get("color", "#ffffffff")))
    try:
        brush.setStyle(Qt.BrushStyle(data.get("style", 0)))
    except Exception:
        brush.setStyle(Qt.BrushStyle.NoBrush)
    return brush


def pixmap_to_base64(pixmap, cache=None):
    if pixmap.isNull():
        return ""
    key = pixmap.cacheKey()
    if cache is not None and key in cache:
        return cache[key]
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    buffer.close()
    encoded = byte_array.toBase64().data().decode("utf-8")
    if cache is not None:
        cache[key] = encoded
    return encoded


def base64_to_pixmap(base64_str):
    if not base64_str:
        return QPixmap()
    byte_array = QByteArray.fromBase64(base64_str.encode("utf-8"))
    image = QImage.fromData(byte_array, "PNG")
    return QPixmap.fromImage(image)


def serialize_path(path):
    elements = []
    for i in range(path.elementCount()):
        el = path.elementAt(i)
        elements.append({
            "type": el.type.value if hasattr(el.type, "value") else int(el.type),
            "x": el.x,
            "y": el.y,
        })
    return elements


def deserialize_path(elements):
    path = QPainterPath()
    i = 0
    num_elements = len(elements)
    while i < num_elements:
        el = elements[i]
        t = el["type"]
        if t == 0:
            path.moveTo(el["x"], el["y"])
            i += 1
        elif t == 1:
            path.lineTo(el["x"], el["y"])
            i += 1
        elif t == 2:
            if i + 2 < num_elements:
                ctrl1 = elements[i]
                ctrl2 = elements[i + 1]
                end_pt = elements[i + 2]
                path.cubicTo(ctrl1["x"], ctrl1["y"], ctrl2["x"], ctrl2["y"], end_pt["x"], end_pt["y"])
                i += 3
            else:
                path.lineTo(el["x"], el["y"])
                i += 1
        else:
            i += 1
    return path


def serialize_project(scene):
    state = scene.get_scene_state()
    items_data = state["items"]
    pix_cache = {}

    serialized_items = []
    for item in items_data:
        item_type = item["type"]
        s_item = {
            "type": item_type,
            "pos": [item["pos"].x(), item["pos"].y()],
        }

        if "pen" in item:
            s_item["pen"] = serialize_pen(item["pen"])
        if "brush" in item:
            s_item["brush"] = serialize_brush(item["brush"])

        if item_type in ("line", "arrow"):
            line = item["line"]
            s_item["line"] = [line.p1().x(), line.p1().y(), line.p2().x(), line.p2().y()]
            if item_type == "arrow" and item.get("double_ended", False):
                s_item["double_ended"] = True
        elif item_type in ("rect", "ellipse"):
            rect = item["rect"]
            s_item["rect"] = [rect.x(), rect.y(), rect.width(), rect.height()]
            if item_type == "rect" and item.get("corner_radius", 0.0) > 0.0:
                s_item["corner_radius"] = item["corner_radius"]
        elif item_type == "polygon":
            poly = item["polygon"]
            s_item["polygon"] = [[pt.x(), pt.y()] for pt in poly]
        elif item_type == "path":
            s_item["path"] = serialize_path(item["path"])
        elif item_type == "text":
            s_item["text"] = item["text"]
            font = item["font"]
            size = font.pointSizeF() if font.pointSizeF() > 0 else 24.0
            s_item["font"] = {
                "family": font.family(),
                "size": size,
                "bold": font.bold(),
                "italic": font.italic(),
            }
            s_item["color"] = color_to_hex(item["color"])
            s_item["scale"] = item["scale"]
        elif item_type == "pixmap":
            s_item["pixmap"] = pixmap_to_base64(item["pixmap"], cache=pix_cache)
            rect = item["rect"]
            s_item["rect"] = [rect.x(), rect.y(), rect.width(), rect.height()]
        elif item_type == "stamp":
            s_item["number"] = item["number"]
            s_item["radius"] = item["radius"]
            s_item["bg_color"] = color_to_hex(item["bg_color"])
            s_item["text_color"] = color_to_hex(item["text_color"])
        elif item_type == "callout":
            br = item["box_rect"]
            tp = item["tip_point"]
            s_item["box_rect"] = [br.x(), br.y(), br.width(), br.height()]
            s_item["tip_point"] = [tp.x(), tp.y()]
            s_item["text"] = item["text"]
            font = item["font"]
            size = font.pointSizeF() if font.pointSizeF() > 0 else 20.0
            s_item["font"] = {
                "family": font.family(),
                "size": size,
                "bold": font.bold(),
                "italic": font.italic(),
            }
            s_item["color"] = color_to_hex(item["color"])
        elif item_type == "spotlight":
            rect = item["rect"]
            s_item["rect"] = [rect.x(), rect.y(), rect.width(), rect.height()]
            s_item["dim_alpha"] = item.get("dim_alpha", 115)
            s_item["corner_radius"] = item.get("corner_radius", 8.0)

        serialized_items.append(s_item)

    bg_pixmap_base64 = pixmap_to_base64(state["bg_pixmap"], cache=pix_cache)
    bg_rect = state["bg_rect"]
    original_image_rect = state["original_image_rect"]

    return {
        "version": PROJECT_FORMAT_VERSION,
        "bg_pixmap": bg_pixmap_base64,
        "bg_rect": [bg_rect.x(), bg_rect.y(), bg_rect.width(), bg_rect.height()],
        "original_image_rect": [
            original_image_rect.x(), original_image_rect.y(),
            original_image_rect.width(), original_image_rect.height()
        ],
        "items": serialized_items,
    }


def deserialize_project(project_data, scene):
    """プロジェクトデータを事前検証・構築してから安全にシーンへ適用する"""
    if not isinstance(project_data, dict) or "items" not in project_data:
        raise ValueError("プロジェクトファイルの形式が正しくありません。")

    bg_pixmap = base64_to_pixmap(project_data.get("bg_pixmap", ""))
    br = project_data.get("bg_rect")
    if br and len(br) == 4:
        bg_rect = QRectF(br[0], br[1], br[2], br[3])
    else:
        bg_rect = QRectF(bg_pixmap.rect())

    oir = project_data.get("original_image_rect")
    if oir and len(oir) == 4:
        orig_img_rect = QRectF(oir[0], oir[1], oir[2], oir[3])
    else:
        orig_img_rect = QRectF(bg_rect)

    built_items = []
    max_stamp = 0
    for item_data in project_data.get("items", []):
        item_type = item_data.get("type")
        pos_raw = item_data.get("pos", [0.0, 0.0])
        pos = QPointF(pos_raw[0], pos_raw[1])

        pen = deserialize_pen(item_data["pen"]) if "pen" in item_data else QPen(Qt.GlobalColor.red)
        brush = deserialize_brush(item_data["brush"]) if "brush" in item_data else None

        new_item = None
        if item_type == "line":
            c = item_data["line"]
            new_item = CustomLineItem(QLineF(c[0], c[1], c[2], c[3]), pen)
        elif item_type == "arrow":
            c = item_data["line"]
            new_item = ArrowItem(QLineF(c[0], c[1], c[2], c[3]), pen, item_data.get("double_ended", False))
        elif item_type == "rect":
            c = item_data["rect"]
            new_item = CustomRectItem(QRectF(c[0], c[1], c[2], c[3]), pen, item_data.get("corner_radius", 0.0))
            if brush is not None:
                new_item.setBrush(brush)
        elif item_type == "ellipse":
            c = item_data["rect"]
            new_item = CustomEllipseItem(QRectF(c[0], c[1], c[2], c[3]), pen)
            if brush is not None:
                new_item.setBrush(brush)
        elif item_type == "polygon":
            poly_pts = [QPointF(pt[0], pt[1]) for pt in item_data["polygon"]]
            new_item = CustomPolygonItem(QPolygonF(poly_pts), pen)
            if brush is not None:
                new_item.setBrush(brush)
        elif item_type == "path":
            path = deserialize_path(item_data["path"])
            new_item = CustomPathItem(path, pen)
            if brush is not None:
                new_item.setBrush(brush)
        elif item_type == "text":
            new_item = CustomTextItem(item_data.get("text", ""))
            f_data = item_data.get("font", {})
            font = QFont(f_data.get("family", DEFAULT_FONT_FAMILY))
            font.setPointSizeF(max(1.0, float(f_data.get("size", 24.0))))
            font.setBold(bool(f_data.get("bold", False)))
            font.setItalic(bool(f_data.get("italic", False)))
            new_item.setFont(font)
            new_item.setDefaultTextColor(hex_to_color(item_data.get("color", "#ffff0000")))
            if "pen" in item_data:
                new_item.setPen(pen)
            if brush is not None:
                new_item.setBrush(brush)
            new_item.setScale(float(item_data.get("scale", 1.0)))
        elif item_type == "pixmap":
            pix = base64_to_pixmap(item_data.get("pixmap", ""))
            c = item_data["rect"]
            new_item = CustomPixmapItem(pix, QRectF(c[0], c[1], c[2], c[3]))
        elif item_type == "stamp":
            num = int(item_data.get("number", 1))
            max_stamp = max(max_stamp, num)
            new_item = NumberStampItem(
                num,
                float(item_data.get("radius", 20.0)),
                hex_to_color(item_data.get("bg_color", "#ffe53935")),
                hex_to_color(item_data.get("text_color", "#ffffffff")),
            )
        elif item_type == "callout":
            br = item_data["box_rect"]
            tp = item_data["tip_point"]
            f_data = item_data.get("font", {})
            font = QFont(f_data.get("family", DEFAULT_FONT_FAMILY))
            font.setPointSizeF(max(1.0, float(f_data.get("size", 20.0))))
            font.setBold(bool(f_data.get("bold", False)))
            font.setItalic(bool(f_data.get("italic", False)))
            new_item = CalloutItem(
                QRectF(br[0], br[1], br[2], br[3]),
                QPointF(tp[0], tp[1]),
                item_data.get("text", ""),
                font,
                hex_to_color(item_data.get("color", "#ffff0000")),
                pen,
                brush if brush is not None else QBrush(Qt.GlobalColor.white),
            )
        elif item_type == "spotlight":
            c = item_data["rect"]
            new_item = SpotlightItem(
                QRectF(c[0], c[1], c[2], c[3]),
                pen,
                int(item_data.get("dim_alpha", 115)),
                float(item_data.get("corner_radius", 8.0)),
            )

        if new_item is not None:
            new_item.setPos(pos)
            built_items.append(new_item)

    # 事前構築に成功してからシーンを切り替え（失敗時の既存状態破壊を防止）
    scene._cancel_transient_operations()
    scene.clear_margin_handles()
    scene.clear()

    scene.bg_item = scene.addPixmap(bg_pixmap)
    scene.bg_item.setZValue(-1.0)
    scene.bg_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
    scene.setSceneRect(bg_rect)
    scene.original_image_rect = orig_img_rect
    scene.next_stamp_number = max_stamp + 1 if max_stamp > 0 else 1

    for idx, item in enumerate(built_items, start=1):
        item.setZValue(float(idx))
        scene.addItem(item)

    scene.undo_stack.clear()
    scene.redo_stack.clear()
    scene.save_state()
    scene.mark_as_saved()
    scene.update_margin_handles()


class NewCanvasDialog(QDialog):
    """新規白紙キャンバスのサイズ・背景色を指定するダイアログ"""
    PRESETS = [
        ("カスタム", None, None),
        ("HD (1280 × 720)", 1280, 720),
        ("フルHD (1920 × 1080)", 1920, 1080),
        ("A4 縦 (1240 × 1754)", 1240, 1754),
        ("A4 横 (1754 × 1240)", 1754, 1240),
        ("正方形 (1000 × 1000)", 1000, 1000),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新規キャンバスを作成")
        self.setModal(True)
        self.bg_color = QColor(Qt.GlobalColor.white)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.preset_combo = QComboBox(self)
        for name, _, _ in self.PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.setCurrentIndex(1)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)
        form.addRow("プリセット:", self.preset_combo)

        self.width_spin = QSpinBox(self)
        self.width_spin.setRange(50, 8000)
        self.width_spin.setValue(1280)
        self.width_spin.setSuffix(" px")
        form.addRow("幅:", self.width_spin)

        self.height_spin = QSpinBox(self)
        self.height_spin.setRange(50, 8000)
        self.height_spin.setValue(720)
        self.height_spin.setSuffix(" px")
        form.addRow("高さ:", self.height_spin)

        color_row = QHBoxLayout()
        self.color_btn = QPushButton("背景色を選択", self)
        self.color_btn.setIcon(create_color_icon(self.bg_color, 16))
        self.color_btn.clicked.connect(self._choose_color)
        color_row.addWidget(self.color_btn)
        color_row.addStretch()
        form.addRow("背景色:", color_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_preset(self, index):
        _, w, h = self.PRESETS[index]
        if w is not None and h is not None:
            self.width_spin.setValue(w)
            self.height_spin.setValue(h)

    def _choose_color(self):
        color = QColorDialog.getColor(
            self.bg_color, self, "キャンバスの背景色を選択",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            self.bg_color = color
            self.color_btn.setIcon(create_color_icon(self.bg_color, 16))

    def get_values(self):
        return self.width_spin.value(), self.height_spin.value(), self.bg_color


class _SubmitTextEdit(QTextEdit):
    """Ctrl+Enterで即座に確定できるマルチライン入力欄"""
    submitRequested = pyqtSignal()

    def keyPressEvent(self, event):
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and (event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        ):
            self.submitRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class QuickTextDialog(QDialog):
    """定型文ボタン・履歴・Ctrl+Enter即確定を備えた高速テキスト入力ダイアログ"""
    def __init__(
        self,
        parent=None,
        title="テキスト入力",
        prompt="文字を入力してください (Ctrl+Enterで確定):",
        initial_text="",
        recent_texts=None,
        show_bg_option=False,
        initial_bg_checked=False,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(440, 260)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt, self))

        # 定型文クイックチップ
        tpl_row = QHBoxLayout()
        tpl_row.setSpacing(4)
        for tpl in QUICK_TEXT_TEMPLATES:
            btn = QPushButton(tpl, self)
            btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn.setStyleSheet(
                "QPushButton { padding: 3px 8px; min-width: 0px; font-size: 9pt; "
                "background-color: #EEF3F8; border: 1px solid #C5D2E0; border-radius: 3px; }"
                "QPushButton:hover { background-color: #005FB8; color: #FFFFFF; border-color: #005FB8; }"
            )
            btn.clicked.connect(lambda checked=False, t=tpl: self._insert_template(t))
            tpl_row.addWidget(btn)
        tpl_row.addStretch()
        layout.addLayout(tpl_row)

        if recent_texts:
            hist_row = QHBoxLayout()
            hist_row.addWidget(QLabel("履歴:", self))
            self.hist_combo = QComboBox(self)
            self.hist_combo.addItem("（最近使った文章から選ぶ）")
            for rt in recent_texts:
                one_line = rt.replace("\n", " / ")
                self.hist_combo.addItem(one_line[:36], rt)
            self.hist_combo.currentIndexChanged.connect(self._apply_history)
            hist_row.addWidget(self.hist_combo, 1)
            layout.addLayout(hist_row)

        self.text_edit = _SubmitTextEdit(self)
        self.text_edit.setPlainText(initial_text)
        self.text_edit.setFont(QFont(DEFAULT_FONT_FAMILY, 10))
        self.text_edit.submitRequested.connect(self.accept)
        layout.addWidget(self.text_edit, 1)

        self.bg_checkbox = None
        if show_bg_option:
            self.bg_checkbox = QCheckBox("見やすい背景・枠を付ける（塗りつぶしON）", self)
            self.bg_checkbox.setChecked(bool(initial_bg_checked))
            layout.addWidget(self.bg_checkbox)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, self
        )
        ok_btn = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn is not None:
            ok_btn.setText("確定 (Ctrl+Enter)")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.text_edit.setFocus()
        if initial_text:
            self.text_edit.selectAll()

    def _insert_template(self, text):
        cur = self.text_edit.toPlainText()
        if not cur.strip():
            self.text_edit.setPlainText(text)
        else:
            self.text_edit.insertPlainText(text)
        self.text_edit.setFocus()

    def _apply_history(self, index):
        if index > 0:
            val = self.hist_combo.itemData(index)
            if val:
                self.text_edit.setPlainText(val)
                self.text_edit.setFocus()

    def get_text(self):
        return self.text_edit.toPlainText()

    def want_background(self):
        return bool(self.bg_checkbox.isChecked()) if self.bg_checkbox is not None else False


class ColorSwatchButton(QToolButton):
    """ワンクリックで定番色を切り替えられるクイックカラーボタン"""
    leftPicked = pyqtSignal(QColor, bool)   # (color, shift_held)
    rightPicked = pyqtSignal(QColor)

    def __init__(self, name, hex_color, parent=None):
        super().__init__(parent)
        self._color = QColor(hex_color)
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(
            f"{name} ({hex_color})\n"
            "左クリック: 線/枠色（文字選択中は文字色）\n"
            "Shift+左クリック: 文字色 / 右クリック: 背景/塗色"
        )
        border = "#888888" if hex_color.upper() == "#FFFFFF" else "#555555"
        self.setStyleSheet(
            f"QToolButton {{ background-color: {hex_color}; border: 1px solid {border}; "
            f"border-radius: 3px; padding: 0px; min-height: 0px; }}"
            f"QToolButton:hover {{ border: 2px solid #005FB8; }}"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.rightPicked.emit(QColor(self._color))
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            self.leftPicked.emit(QColor(self._color), shift)
            event.accept()
            return
        super().mousePressEvent(event)


class CropActionBar(QFrame):
    """切り抜き範囲確定・キャンセル用のフローティングバー"""
    confirmClicked = pyqtSignal()
    cancelClicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "QFrame { background-color: #FFFFFF; border: 1px solid #005FB8; border-radius: 6px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        ok_btn = QPushButton("✓ 切り抜き実行 (Enter)", self)
        ok_btn.setStyleSheet(
            "QPushButton { background-color: #005FB8; color: #FFFFFF; border: none; "
            "border-radius: 4px; padding: 4px 12px; font-weight: bold; font-size: 9pt; min-width: 0px; }"
            "QPushButton:hover { background-color: #004B94; }"
        )
        ok_btn.clicked.connect(self.confirmClicked.emit)

        cancel_btn = QPushButton("✕ キャンセル (Esc)", self)
        cancel_btn.setStyleSheet(
            "QPushButton { background-color: #F0F2F5; color: #333333; border: 1px solid #C8CDD4; "
            "border-radius: 4px; padding: 4px 10px; font-size: 9pt; min-width: 0px; }"
            "QPushButton:hover { background-color: #E2E6EC; }"
        )
        cancel_btn.clicked.connect(self.cancelClicked.emit)

        layout.addWidget(ok_btn)
        layout.addWidget(cancel_btn)
        self.adjustSize()
        self.hide()

    def reposition(self):
        parent = self.parentWidget()
        if parent is not None:
            self.adjustSize()
            x = max(12, (parent.width() - self.width()) // 2)
            y = max(12, parent.height() - self.height() - 16)
            self.move(x, y)


class ScreenCaptureOverlay(QWidget):
    """Windows画面上の任意範囲をドラッグで高解像度キャプチャする全画面オーバーレイ"""
    captured = pyqtSignal(object)  # QPixmap or None

    def __init__(self, full_pixmap, screen_geometry):
        super().__init__(None)
        self.full_pixmap = full_pixmap
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setGeometry(screen_geometry)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._start_pos = None
        self._current_rect = QRect()
        self._done = False

    def _finish(self, result_pixmap):
        if self._done:
            return
        self._done = True
        self.hide()
        self.captured.emit(result_pixmap)
        self.deleteLater()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.drawPixmap(self.rect(), self.full_pixmap)

        if not self._current_rect.isNull() and self._current_rect.width() > 1 and self._current_rect.height() > 1:
            dim = QPainterPath()
            dim.setFillRule(Qt.FillRule.OddEvenFill)
            dim.addRect(QRectF(self.rect()))
            dim.addRect(QRectF(self._current_rect))
            painter.fillPath(dim, QColor(0, 0, 0, 110))

            painter.setPen(QPen(QColor("#0078D7"), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(self._current_rect)

            rx = self.full_pixmap.width() / max(1.0, float(self.width()))
            ry = self.full_pixmap.height() / max(1.0, float(self.height()))
            pw = int(round(self._current_rect.width() * rx))
            ph = int(round(self._current_rect.height() * ry))
            label = f"{pw} × {ph} px"
            font = QFont(DEFAULT_FONT_FAMILY, 9)
            font.setBold(True)
            painter.setFont(font)
            fm = QFontMetricsF(font)
            bw = int(fm.horizontalAdvance(label)) + 16
            bh = int(fm.height()) + 8
            bx = self._current_rect.left()
            by = self._current_rect.top() - bh - 6
            if by < 8:
                by = self._current_rect.top() + 6
            badge = QRect(bx, by, bw, bh)
            painter.fillRect(badge, QColor(0, 95, 184, 230))
            painter.setPen(Qt.GlobalColor.white)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, label)
        else:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 95))
            banner_text = "ドラッグして撮影範囲を選択してください（Enter: 全画面撮影 / Esc・右クリック: キャンセル）"
            font = QFont(DEFAULT_FONT_FAMILY, 10)
            font.setBold(True)
            painter.setFont(font)
            fm = QFontMetricsF(font)
            bw = int(fm.horizontalAdvance(banner_text)) + 32
            bh = int(fm.height()) + 16
            bx = (self.width() - bw) // 2
            badge = QRect(bx, 24, bw, bh)
            painter.setBrush(QColor(255, 255, 255, 240))
            painter.setPen(QPen(QColor("#005FB8"), 1))
            painter.drawRoundedRect(badge, 6, 6)
            painter.setPen(QColor("#222222"))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, banner_text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self._finish(None)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.position().toPoint()
            self._current_rect = QRect(self._start_pos, self._start_pos)
            self.update()

    def mouseMoveEvent(self, event):
        if self._start_pos is not None:
            cur = event.position().toPoint()
            self._current_rect = QRect(self._start_pos, cur).normalized().intersected(self.rect())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._start_pos is not None:
            rect = self._current_rect
            self._start_pos = None
            if rect.width() >= 6 and rect.height() >= 6:
                rx = self.full_pixmap.width() / max(1.0, float(self.width()))
                ry = self.full_pixmap.height() / max(1.0, float(self.height()))
                src = QRect(
                    int(round(rect.x() * rx)),
                    int(round(rect.y() * ry)),
                    max(1, int(round(rect.width() * rx))),
                    max(1, int(round(rect.height() * ry))),
                )
                cropped = self.full_pixmap.copy(src)
                cropped.setDevicePixelRatio(1.0)
                self._finish(cropped)
            else:
                self._current_rect = QRect()
                self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self._finish(None)
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            full_copy = self.full_pixmap.copy()
            full_copy.setDevicePixelRatio(1.0)
            self._finish(full_copy)


class ToastBanner(QLabel):
    """作業を中断させずに保存完了や通知をスマートに表示する非モーダル通知"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "QLabel {"
            "  background-color: #1F4E79;"
            "  color: #FFFFFF;"
            "  border-radius: 6px;"
            "  padding: 8px 18px;"
            "  font-size: 10pt;"
            "  font-weight: bold;"
            "}"
        )
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text, duration_ms=2500):
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(duration_ms)

    def _reposition(self):
        parent = self.parentWidget()
        if parent is not None:
            margin = 18
            x = max(margin, parent.width() - self.width() - margin)
            y = max(margin, parent.height() - self.height() - margin)
            self.move(x, y)

    def mousePressEvent(self, event):
        self.hide()
        self._timer.stop()


class AboutDialog(QDialog):
    """アプリアイコン・バージョン・v2.0.0ハイライトを見やすく表示するバージョン情報ダイアログ"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} について")
        self.setModal(True)
        self.setFixedSize(480, 410)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        # ヘッダー（アイコン + アプリ名 + バージョンバッジ）
        header = QFrame(self)
        header.setStyleSheet(
            "QFrame { background-color: #EAF3FC; border: 1px solid #C5DCF5; border-radius: 8px; }"
        )
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 14, 16, 14)
        header_layout.setSpacing(14)

        icon_label = QLabel(header)
        icon_label.setStyleSheet("border: none; background: transparent;")
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            pix = QIcon(icon_path).pixmap(52, 52)
            icon_label.setPixmap(pix)
        else:
            icon_label.setText("✏️")
            icon_label.setFont(QFont(DEFAULT_FONT_FAMILY, 24))
        header_layout.addWidget(icon_label)

        title_col = QVBoxLayout()
        title_col.setSpacing(4)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_lbl = QLabel(APP_NAME, header)
        name_lbl.setStyleSheet("border: none; background: transparent; color: #163B65; font-size: 14pt; font-weight: bold;")
        ver_lbl = QLabel(f" {APP_VERSION} ", header)
        ver_lbl.setStyleSheet(
            "background-color: #005FB8; color: #FFFFFF; border: none; "
            "border-radius: 9px; padding: 2px 9px; font-size: 9pt; font-weight: bold;"
        )
        name_row.addWidget(name_lbl)
        name_row.addWidget(ver_lbl)
        name_row.addStretch()
        title_col.addLayout(name_row)

        sub_lbl = QLabel("素早く書いて、相手に早く伝える画像・PDF注釈ツール", header)
        sub_lbl.setStyleSheet("border: none; background: transparent; color: #3A5575; font-size: 9pt;")
        title_col.addWidget(sub_lbl)
        header_layout.addLayout(title_col, 1)
        layout.addWidget(header)

        # v2.0.0 ハイライトカード
        info_browser = QTextBrowser(self)
        info_browser.setStyleSheet(
            "QTextBrowser { background-color: #FFFFFF; border: 1px solid #D5DBE2; border-radius: 6px; padding: 6px; }"
        )
        info_browser.setHtml(
            f"""
            <div style="font-family: '{DEFAULT_FONT_FAMILY}', sans-serif; font-size: 9pt; color: #222222; line-height: 1.55;">
              <div style="font-weight: bold; color: #005FB8; font-size: 10pt; margin-bottom: 6px;">
                ✨ {APP_VERSION} の主なハイライト
              </div>
              <table width="100%" cellpadding="3" cellspacing="0">
                <tr><td width="24" valign="top">📸</td><td><b>画面撮影 ＆ ワンクリック画像コピー</b>：撮って書いて即チャットへ貼付</td></tr>
                <tr><td valign="top">💬</td><td><b>吹き出し（コールアウト）</b>：矢印しっぽ付きコメントをドラッグ1発作成</td></tr>
                <tr><td valign="top">🔦</td><td><b>注目スポットライト ＆ モザイク目隠し</b>：強調と個人情報保護を素早く</td></tr>
                <tr><td valign="top">🎨</td><td><b>8色クイックパレット ＆ スポイト</b>：1クリック色変更・修正液テクニック</td></tr>
                <tr><td valign="top">✂️</td><td><b>切り抜き・ドラッグ余白調整・複数ページPDF完全対応</b></td></tr>
                <tr><td valign="top">⌨️</td><td><b>1キー切替 ＆ 定型文 / Ctrl+Enter 高速入力</b></td></tr>
              </table>
              <hr style="border: none; border-top: 1px solid #E5E9EF; margin: 8px 0;">
              <div style="color: #666666; font-size: 8pt;">
                動作環境: Windows 10 / Windows 11 &nbsp;|&nbsp; プロジェクト形式: .hwi ({PROJECT_FORMAT_VERSION})
              </div>
            </div>
            """
        )
        layout.addWidget(info_browser, 1)

        # フッターボタン
        btn_row = QHBoxLayout()
        help_btn = QPushButton("📖 ヘルプセンターを開く", self)
        help_btn.clicked.connect(self._open_help_from_about)
        close_btn = QPushButton("閉じる", self)
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(help_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _open_help_from_about(self):
        parent = self.parent()
        self.accept()
        if parent is not None and hasattr(parent, "show_help_center"):
            parent.show_help_center(0)


class HelpCenterDialog(QDialog):
    """検索対応・タブ切替式のわかりやすい統合ヘルプセンター"""

    TOOL_GUIDE_DATA = [
        (
            "取り込み・共有（最短フロー）",
            "#EAF3FC",
            "#005FB8",
            [
                ("📸 画面撮影", "Ctrl+Shift+A", "画面上の好きな範囲をドラッグして撮影し、そのまま編集を始められます（Enterで全画面撮影）。"),
                ("📋 画像コピー", "Ctrl+Shift+C", "完成した注釈画像をクリップボードにコピーします。Teams・Slack・メール・Wordへすぐ貼り付けできます。"),
                ("📂 開く / D&D", "Ctrl+O", "PNG・JPG・BMP・GIF・WebP・PDF・プロジェクト(.hwi)を開けます。ウィンドウへのドラッグ＆ドロップにも対応しています。"),
                ("🖼️ 画像挿入", "Ctrl+ドロップ", "別の画像やPDFの指定ページを注釈として重ねて配置できます。右クリックから縦横比リセットも可能です。"),
                ("📄 新規キャンバス", "Ctrl+N", "白紙キャンバスを好きなサイズ・背景色で作成します。未開閉のまま描画ツールを選ぶと自動で白紙を作成します。"),
            ],
        ),
        (
            "線・マーカー・図形・目隠し・強調",
            "#EEF8F0",
            "#2E7D32",
            [
                ("📏 直線 / 矢印 / 両矢印", "L / A", "ドラッグで描画します。Shiftキーを押しながら描くと水平・垂直・45°にきれいに揃います。右クリックで実線・破線・点線に変更できます。"),
                ("🖊️ 曲線 / マーカー", "P / H", "自由な手描き線や半透明の蛍光ペン（マーカー）を引けます。Shiftキーを押しながら引くと真っ直ぐな蛍光マーカーになります。"),
                ("🔲 四角 / 角丸 / 丸 / 三角", "R / O", "枠のみ・塗りつぶし・半透明塗りの3モードから選べます。Shiftキーを押しながら描くと正方形・正円になります。"),
                ("🔦 スポットライト", "S", "ドラッグした範囲だけ明るく残し、周囲を暗くして見てほしい場所を一瞬で伝えます。右クリックで周囲の暗さを3段階調整できます。"),
                ("🏁 モザイク（目隠し）", "M", "個人情報や機密部分を四角くドラッグするだけでモザイク処理をかけます。後から移動・削除も自由です。"),
                ("🔢 連番スタンプ", "N", "クリックするだけで 1, 2, 3... の丸数字バッジを順番に配置できます。ダブルクリックで番号変更、編集メニューから開始番号リセットが可能です。"),
            ],
        ),
        (
            "文字・吹き出し・色・キャンバス調整",
            "#FFF8EC",
            "#C66A00",
            [
                ("💬 吹き出し", "B", "指したい場所からコメントを置きたい場所へドラッグ→文字入力で、矢印しっぽ付き吹き出しを1発作成。オレンジ丸ハンドルで先端だけ動かせます。"),
                ("🔤 文字入力", "T", "定型文ボタン・入力履歴・Ctrl+Enter即確定に対応。「見やすい背景・枠を付ける」にチェックすれば背景写真の上でもくっきり読めます。"),
                ("🎨 8色クイックカラー", "左/右クリック", "ツールバー上段の8色から1クリックで色変更。左クリックで線/枠色（文字選択中は文字色）、Shift+左で文字色、右クリックで背景/塗色が変わります。"),
                ("💉 スポイト", "I", "画像上の任意の色を吸い取ります。左クリックで線/枠色、右クリック（またはShift+左クリック）で背景/塗色へセットします。"),
                ("✂️ 切り抜き", "C", "必要な部分だけをドラッグ選択し、Enterキー・ダブルクリック・下部ボタンでトリミングします。既存注釈も自動で位置補正されます。"),
                ("⏹️ 余白調整", "ドラッグ", "周囲の青いバーを外へドラッグすると余白が広がり、広げた余白は内へドラッグして削れます（元画像自体は保護されます）。"),
            ],
        ),
        (
            "PDF編集・保存・プロジェクト管理",
            "#F5EFFA",
            "#6A1B9A",
            [
                ("📑 複数ページPDF", "前/次ページ", "ページを切り替えても各ページの注釈が保持されます。ページ番号表示をクリックすると指定ページへ直接ジャンプできます。"),
                ("💾 保存 / 名前を付けて保存", "Ctrl+S / Shift+S", "JPG・PNG・PDFで保存できます。複数ページPDFは編集していないページも元の高画質のまま維持して1つのPDFに保存します。"),
                ("📦 プロジェクト保存 (.hwi)", "Ctrl+P", "すべての注釈を動かせる状態のまま保存します。後日開いて文字修正や位置調整ができます。"),
            ],
        ),
    ]

    SHORTCUT_DATA = [
        (
            "ファイル・画面撮影・すぐ共有",
            [
                ("Ctrl + Shift + A", "画面を範囲選択して撮影し、すぐ編集を開始"),
                ("Ctrl + Shift + C", "完成画像をクリップボードにコピー（チャットや資料へ即貼付）"),
                ("Ctrl + Shift + V", "クリップボードの画像を新規キャンバスとして開く"),
                ("Ctrl + N", "新規白紙キャンバスを作成"),
                ("Ctrl + O", "画像・PDF・プロジェクト(.hwi)を開く"),
                ("Ctrl + S", "上書き保存"),
                ("Ctrl + Shift + S", "名前を付けて保存（JPG / PNG / PDF）"),
                ("Ctrl + P", "再編集用プロジェクト(.hwi)として保存"),
            ],
        ),
        (
            "1キーで瞬時にツール切替（文字入力欄以外）",
            [
                ("V / Esc", "選択・移動ツールへ戻る（配置待ち・切り抜きキャンセルも可）"),
                ("L / A", "直線 / 矢印ツール"),
                ("P / H", "曲線（フリーハンド） / マーカー（蛍光ペン）"),
                ("R / O", "四角 / 丸・楕円"),
                ("T / B", "文字入力 / 吹き出し（コールアウト）"),
                ("N / M / S", "連番スタンプ / モザイク（目隠し） / スポットライト（注目枠）"),
                ("C / I", "切り抜き（トリミング） / スポイト（色取得）"),
                ("[ / ]", "線の太さを1段階 細く / 太くする"),
            ],
        ),
        (
            "編集・配置・微調整",
            [
                ("Ctrl + Z / Ctrl + Y", "元に戻す / やり直す（Ctrl + Shift + Z も対応）"),
                ("Ctrl + C / Ctrl + V", "選択注釈のコピー / 貼り付け（外部スクショ画像もそのまま貼付）"),
                ("Ctrl + D", "選択中の注釈を複製"),
                ("Ctrl + A / Delete", "すべての注釈を選択 / 選択中の注釈を削除（Backspaceも可）"),
                ("矢印キー / Shift + 矢印", "選択中の注釈を 1px / 10px ずつ微調整移動"),
                ("Ctrl + B / Ctrl + I", "テキスト・吹き出しの 太字 / 斜体 を切り替え"),
                ("Ctrl + Enter", "テキスト・吹き出し入力ダイアログをすぐ確定"),
                ("Enter", "切り抜き範囲を確定（切り抜きツール中）"),
            ],
        ),
        (
            "表示・ズーム・マウス便利操作",
            [
                ("Ctrl + ホイール", "マウスカーソル位置を中心に拡大・縮小"),
                ("Shift + ホイール", "横スクロール"),
                ("Space + ドラッグ / 中ボタン", "キャンバスを手のひらスクロール（パン移動）"),
                ("Ctrl + + / Ctrl + -", "拡大 / 縮小"),
                ("Ctrl + 0 / Ctrl + 9", "100%表示 / 画面サイズに合わせる"),
                ("Ctrl + G", "位置合わせ用の補助グリッド表示を切り替え"),
                ("Shift + ドラッグ描画", "線・矢印を水平/垂直/45°固定、図形を正方形/正円に固定"),
                ("ダブルクリック", "文字・吹き出し・連番スタンプの内容をその場で編集"),
                ("Ctrl + ファイルドロップ", "ドロップした画像を注釈として既存キャンバス内へ挿入"),
                ("F1", "このヘルプセンターを開く"),
            ],
        ),
    ]

    TIPS_AND_FAQ_DATA = [
        (
            "⚡ レシピ1：5秒で画面を撮ってチャットに送る",
            "1. ツールバーの「📸 画面撮影」（Ctrl+Shift+A）を押して欲しい範囲をドラッグします。\n"
            "2. 「B」キーで吹き出し、または「A」キーで矢印をサッと描きます。\n"
            "3. 「📋 画像コピー」（Ctrl+Shift+C）を1クリックして、Teams・Slack・メール上で Ctrl+V するだけで完了です！保存ファイルでデスクトップが散らかりません。",
        ),
        (
            "🪄 レシピ2：修正液テクニック（画像上の不要文字を自然に消す）",
            "1. 「I」キーでスポイトを選び、消したい文字の周りの背景色を「右クリック」で吸い取ります（背景/塗色が自動設定されます）。\n"
            "2. 「R」キーで四角ツールを選び、線/枠色も背景色に合わせるか細くして、消したい部分を四角く囲めば綺麗に隠せます。",
        ),
        (
            "🔦 レシピ3：複雑な画面で「ここを見て！」を一瞬で伝える",
            "1. 「S」キー（スポットライト）で注目箇所をドラッグすると周囲が暗くなり視線が一点に集中します。\n"
            "2. 「N」キー（連番スタンプ）で操作順に 1, 2, 3 と番号を打ち、「B」キー（吹き出し）で一言添えると、誰でも迷わない手順書が一瞬で完成します。",
        ),
        (
            "📑 レシピ4：複数ページPDFを劣化させずまとめて注釈保存",
            "PDFを開いてページをめくりながら注釈を入れていくと、全ページの編集内容が自動で記憶されます。"
            "最後に「💾 保存」または「名前を付けて保存（PDF）」を実行すると、編集していないページは元の鮮明な文字データのまま保持して1つのPDFに書き出します。",
        ),
        (
            "❓ Q. 後から文字を直したり矢印を動かしたりしたい",
            "JPGやPNGで保存すると画像として焼き込まれます。後から修正する可能性がある資料は「📦 プロジェクト保存」（Ctrl+P）で .hwi 形式でも保存しておくと、いつでも注釈を編集できる状態で再開できます。",
        ),
        (
            "❓ Q. 余白調整で元画像の内側まで切れないのはなぜ？",
            "「⏹️ 余白調整」はうっかり元画像を削りすぎないよう元画像を保護する設計です。画像自体を切り詰めたい場合は、隣の「✂️ 切り抜き」（Cキー）をお使いください。",
        ),
        (
            "❓ Q. 塗りつぶし図形の内側をクリックしても動かせますか？",
            "はい。塗りつぶし・半透明塗りの図形は内側どこをクリックしても掴んで移動できます。透過（枠のみ）の図形は、枠の中にある別の文字を選びやすいよう枠線部分のみ掴める設計になっています。",
        ),
    ]

    def __init__(self, parent=None, initial_tab=0):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} ヘルプセンター ({APP_VERSION})")
        self.resize(800, 600)
        self.setMinimumSize(640, 480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        # 上部ヘッダーバナー＋リアルタイム検索欄
        header = QFrame(self)
        header.setStyleSheet(
            "QFrame { background-color: #EAF3FC; border: 1px solid #C5DCF5; border-radius: 7px; }"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(14, 10, 14, 10)
        h_layout.setSpacing(12)

        icon_lbl = QLabel(header)
        icon_lbl.setStyleSheet("border: none; background: transparent;")
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            icon_lbl.setPixmap(QIcon(icon_path).pixmap(34, 34))
        else:
            icon_lbl.setText("📖")
            icon_lbl.setFont(QFont(DEFAULT_FONT_FAMILY, 18))
        h_layout.addWidget(icon_lbl)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        t_lbl = QLabel(f"{APP_NAME} ヘルプセンター  ({APP_VERSION})", header)
        t_lbl.setStyleSheet("border: none; background: transparent; color: #163B65; font-size: 12pt; font-weight: bold;")
        s_lbl = QLabel("素早く書いて、相手に早く伝えるための操作ガイド", header)
        s_lbl.setStyleSheet("border: none; background: transparent; color: #3A5575; font-size: 9pt;")
        title_box.addWidget(t_lbl)
        title_box.addWidget(s_lbl)
        h_layout.addLayout(title_box, 1)

        self.search_input = QLineEdit(header)
        self.search_input.setPlaceholderText("🔍 キーワード検索（例: 吹き出し, PDF, 色, 切り抜き）")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(285)
        self.search_input.textChanged.connect(self._on_search_changed)
        h_layout.addWidget(self.search_input)

        layout.addWidget(header)

        # 5つのタブ構成
        self.tabs = QTabWidget(self)
        self.quick_browser = self._make_browser()
        self.guide_browser = self._make_browser()
        self.shortcut_browser = self._make_browser()
        self.tips_browser = self._make_browser()
        self.readme_browser = self._make_browser()

        self.tabs.addTab(self.quick_browser, "🚀 かんたんスタート")
        self.tabs.addTab(self.guide_browser, "🎨 ツール・機能ガイド")
        self.tabs.addTab(self.shortcut_browser, "⌨️ ショートカット一覧")
        self.tabs.addTab(self.tips_browser, "💡 活用コツ・Q&A")
        self.tabs.addTab(self.readme_browser, "📄 Readme")

        layout.addWidget(self.tabs, 1)

        # フッター
        footer = QHBoxLayout()
        hint = QLabel("ヒント: F1キーでいつでもこのヘルプを開けます。上部検索欄でツールやショートカットを絞り込めます。", self)
        hint.setStyleSheet("color: #666666; font-size: 9pt;")
        footer.addWidget(hint, 1)

        about_btn = QPushButton("ℹ️ バージョン情報", self)
        about_btn.clicked.connect(self._open_about)
        close_btn = QPushButton("閉じる", self)
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(about_btn)
        footer.addWidget(close_btn)
        layout.addLayout(footer)

        self._render_quick_start()
        self._render_readme()
        self._apply_filter("")

        if 0 <= initial_tab < self.tabs.count():
            self.tabs.setCurrentIndex(initial_tab)

    def _make_browser(self):
        b = QTextBrowser(self)
        b.setOpenExternalLinks(True)
        b.setFont(QFont(DEFAULT_FONT_FAMILY, 9))
        b.setStyleSheet("QTextBrowser { background-color: #FFFFFF; border: none; padding: 8px; }")
        return b

    def _open_about(self):
        dlg = AboutDialog(self.parent() or self)
        dlg.exec()

    def _render_quick_start(self):
        html = f"""
        <div style="font-family: '{DEFAULT_FONT_FAMILY}', sans-serif; font-size: 9pt; color: #222222;">
          <div style="font-size: 11pt; font-weight: bold; color: #163B65; margin-bottom: 8px;">
            最短 3 ステップで「撮って・書いて・すぐ伝える」
          </div>

          <table width="100%" cellpadding="10" cellspacing="6">
            <tr>
              <td width="33%" valign="top" style="background-color: #EEF5FD; border: 1px solid #C6DDF5;">
                <div style="font-size: 10pt; font-weight: bold; color: #005FB8; margin-bottom: 4px;">STEP 1. 用意する</div>
                <div>
                  ・<b>📸 画面撮影</b>（Ctrl+Shift+A）で画面を切り取り<br>
                  ・<b>📂 開く</b> またはドラッグ＆ドロップで画像・PDFを開く<br>
                  ・スクショ後に <b>Ctrl+V</b> で即貼り付け
                </div>
              </td>
              <td width="33%" valign="top" style="background-color: #EEF8F0; border: 1px solid #C3E3C8;">
                <div style="font-size: 10pt; font-weight: bold; color: #2E7D32; margin-bottom: 4px;">STEP 2. サッと書く</div>
                <div>
                  ・<b>💬 吹き出し (B)</b> や <b>矢印 (A)</b> で指し示す<br>
                  ・<b>🔦 スポットライト (S)</b> で注目箇所を際立たせる<br>
                  ・上段の<b>8色パレット</b>で1クリック色変更
                </div>
              </td>
              <td width="33%" valign="top" style="background-color: #FFF6E8; border: 1px solid #F3D4A5;">
                <div style="font-size: 10pt; font-weight: bold; color: #C66A00; margin-bottom: 4px;">STEP 3. すぐ送る</div>
                <div>
                  ・<b>📋 画像コピー</b>（Ctrl+Shift+C）を1クリック<br>
                  ・チャットやメール・資料に <b>Ctrl+V</b> で送信完了<br>
                  ・必要なら <b>💾 保存</b> や <b>📦 .hwi保存</b> で残す
                </div>
              </td>
            </tr>
          </table>

          <div style="font-size: 10pt; font-weight: bold; color: #163B65; margin-top: 12px; margin-bottom: 6px;">
            よく使うおすすめ機能ピックアップ
          </div>
          <table width="100%" cellpadding="6" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #F4F6F9;">
              <td width="160" style="border-bottom: 1px solid #E1E5EB;"><b>💬 吹き出し (B)</b></td>
              <td style="border-bottom: 1px solid #E1E5EB;">指したい場所からドラッグしてコメント入力。しっぽ先端は後からオレンジ丸ハンドルで自由に動かせます。</td>
            </tr>
            <tr>
              <td style="border-bottom: 1px solid #E1E5EB;"><b>🔦 スポットライト (S)</b></td>
              <td style="border-bottom: 1px solid #E1E5EB;">見せたい部分だけ明るく残して周囲を暗く強調。複雑な画面でも一目で伝わります。</td>
            </tr>
            <tr style="background-color: #F4F6F9;">
              <td style="border-bottom: 1px solid #E1E5EB;"><b>🏁 モザイク (M)</b></td>
              <td style="border-bottom: 1px solid #E1E5EB;">名前や住所・金額などの機密情報をドラッグするだけで手軽に目隠しできます。</td>
            </tr>
            <tr>
              <td style="border-bottom: 1px solid #E1E5EB;"><b>🔢 連番スタンプ (N)</b></td>
              <td style="border-bottom: 1px solid #E1E5EB;">クリックするだけで 1, 2, 3... の丸数字を順番に配置。手順説明に便利です。</td>
            </tr>
            <tr style="background-color: #F4F6F9;">
              <td style="border-bottom: 1px solid #E1E5EB;"><b>✂️ 切り抜き (C)</b></td>
              <td style="border-bottom: 1px solid #E1E5EB;">不要な余白や周辺部分をカットして、伝えたい部分だけをスッキリ送れます。</td>
            </tr>
            <tr>
              <td style="border-bottom: 1px solid #E1E5EB;"><b>💉 スポイト (I)</b></td>
              <td style="border-bottom: 1px solid #E1E5EB;">左クリックで線色、右クリックで背景/塗色に画像の色を取得。文字の消し込みにも活躍します。</td>
            </tr>
          </table>
        </div>
        """
        self.quick_browser.setHtml(html)

    def _render_readme(self):
        readme_path = find_readme_path()
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = f"ファイルの読み込みに失敗しました:\n{e}"
        else:
            content = f"READMEファイルが見つかりませんでした。\n検索パス: {readme_path}"
        self.readme_browser.setMarkdown(content)

    def _on_search_changed(self, text):
        query = text.strip()
        g_cnt, s_cnt, t_cnt = self._apply_filter(query)
        if query:
            self.tabs.setTabText(1, f"🎨 ツールガイド ({g_cnt})")
            self.tabs.setTabText(2, f"⌨️ ショートカット ({s_cnt})")
            self.tabs.setTabText(3, f"💡 活用コツ・Q&A ({t_cnt})")
            # かんたんスタートまたはReadmeタブで検索を始めたら最初にヒットしたタブへ自動誘導
            cur = self.tabs.currentIndex()
            if cur in (0, 4):
                if g_cnt > 0:
                    self.tabs.setCurrentIndex(1)
                elif s_cnt > 0:
                    self.tabs.setCurrentIndex(2)
                elif t_cnt > 0:
                    self.tabs.setCurrentIndex(3)
        else:
            self.tabs.setTabText(1, "🎨 ツール・機能ガイド")
            self.tabs.setTabText(2, "⌨️ ショートカット一覧")
            self.tabs.setTabText(3, "💡 活用コツ・Q&A")

    def _apply_filter(self, query):
        q = query.lower()

        # 1. ツールガイド
        guide_parts = [f"<div style=\"font-family: '{DEFAULT_FONT_FAMILY}', sans-serif; font-size: 9pt; color: #222222;\">"]
        guide_hits = 0
        for cat_title, bg_hex, accent_hex, rows in self.TOOL_GUIDE_DATA:
            matched = [
                r for r in rows
                if not q or q in cat_title.lower() or q in r[0].lower() or q in r[1].lower() or q in r[2].lower()
            ]
            if not matched:
                continue
            guide_hits += len(matched)
            guide_parts.append(
                f"<div style='background-color: {bg_hex}; border-left: 4px solid {accent_hex}; "
                f"padding: 5px 10px; font-weight: bold; color: {accent_hex}; font-size: 10pt; margin-top: 8px;'>"
                f"{cat_title}</div>"
                "<table width='100%' cellpadding='6' cellspacing='0' style='border-collapse: collapse; margin-bottom: 6px;'>"
            )
            for name, key_hint, desc in matched:
                guide_parts.append(
                    f"<tr>"
                    f"<td width='165' valign='top' style='border-bottom: 1px solid #E5E9EF;'><b>{name}</b></td>"
                    f"<td width='105' valign='top' style='border-bottom: 1px solid #E5E9EF;'>"
                    f"<span style='background-color: #EEF1F5; border: 1px solid #CFD6DF; padding: 1px 6px; color: #333333; font-size: 8pt;'>{key_hint}</span></td>"
                    f"<td valign='top' style='border-bottom: 1px solid #E5E9EF;'>{desc}</td>"
                    f"</tr>"
                )
            guide_parts.append("</table>")
        if guide_hits == 0:
            guide_parts.append("<p style='color: #777777; padding: 16px;'>該当するツール・機能が見つかりませんでした。</p>")
        guide_parts.append("</div>")
        self.guide_browser.setHtml("".join(guide_parts))

        # 2. ショートカット一覧
        sc_parts = [f"<div style=\"font-family: '{DEFAULT_FONT_FAMILY}', sans-serif; font-size: 9pt; color: #222222;\">"]
        sc_hits = 0
        for cat_title, rows in self.SHORTCUT_DATA:
            matched = [
                r for r in rows
                if not q or q in cat_title.lower() or q in r[0].lower() or q in r[1].lower()
            ]
            if not matched:
                continue
            sc_hits += len(matched)
            sc_parts.append(
                f"<div style='background-color: #F0F4F9; border-left: 4px solid #005FB8; "
                f"padding: 5px 10px; font-weight: bold; color: #163B65; font-size: 10pt; margin-top: 8px;'>"
                f"{cat_title}</div>"
                "<table width='100%' cellpadding='5' cellspacing='0' style='border-collapse: collapse; margin-bottom: 6px;'>"
            )
            for idx, (keys, desc) in enumerate(matched):
                row_bg = "#FAFBFD" if idx % 2 == 1 else "#FFFFFF"
                sc_parts.append(
                    f"<tr style='background-color: {row_bg};'>"
                    f"<td width='205' style='border-bottom: 1px solid #E6EAEF;'>"
                    f"<span style='background-color: #EEF2F7; border: 1px solid #C4CEDB; padding: 2px 7px; font-weight: bold; color: #1A3C66;'>{keys}</span></td>"
                    f"<td style='border-bottom: 1px solid #E6EAEF;'>{desc}</td>"
                    f"</tr>"
                )
            sc_parts.append("</table>")
        if sc_hits == 0:
            sc_parts.append("<p style='color: #777777; padding: 16px;'>該当するショートカットが見つかりませんでした。</p>")
        sc_parts.append("</div>")
        self.shortcut_browser.setHtml("".join(sc_parts))

        # 3. 活用コツ・Q&A
        tips_parts = [f"<div style=\"font-family: '{DEFAULT_FONT_FAMILY}', sans-serif; font-size: 9pt; color: #222222;\">"]
        tips_hits = 0
        for title, body in self.TIPS_AND_FAQ_DATA:
            if q and q not in title.lower() and q not in body.lower():
                continue
            tips_hits += 1
            is_faq = title.startswith("❓")
            bg = "#F8F9FB" if is_faq else "#F2F7FD"
            accent = "#5C6BC0" if is_faq else "#005FB8"
            body_html = body.replace("\n", "<br>")
            tips_parts.append(
                f"<table width='100%' cellpadding='8' cellspacing='0' style='margin-bottom: 8px; background-color: {bg}; border-left: 4px solid {accent}; border-top: 1px solid #E2E7EE; border-right: 1px solid #E2E7EE; border-bottom: 1px solid #E2E7EE;'>"
                f"<tr><td>"
                f"<div style='font-weight: bold; color: #163B65; font-size: 10pt; margin-bottom: 4px;'>{title}</div>"
                f"<div style='color: #333333; line-height: 1.5;'>{body_html}</div>"
                f"</td></tr></table>"
            )
        if tips_hits == 0:
            tips_parts.append("<p style='color: #777777; padding: 16px;'>該当する活用コツ・Q&amp;Aが見つかりませんでした。</p>")
        tips_parts.append("</div>")
        self.tips_browser.setHtml("".join(tips_parts))

        return guide_hits, sc_hits, tips_hits


class AdvancedAnnotationApp(QMainWindow):
    TOOL_HINTS = {
        "select": "クリックで選択・移動 / ダブルクリックで文字編集 / 矢印キーで微調整 / V・A・R・T・B等で素早くツール切替",
        "line": "ドラッグで描画 / Shiftキーを押しながらで水平・垂直・45°にスナップ / [ ] キーで太さ変更",
        "shape": "ドラッグで図形を描画（連番スタンプはクリック配置）/ Shiftキーで正方形・正円",
        "text": "左クリックで文字を配置 / 右クリックまたはEscキーでキャンセル",
        "callout": "指したい場所から吹き出しを置きたい場所へドラッグ → コメント入力で一発作成",
        "crop": "残したい範囲をドラッグして選択 → Enterキーまたは下のボタンで切り抜き確定（Escでキャンセル）",
        "margin": "周囲の青いバーを外へドラッグで余白拡張・内へドラッグで余白削減（色は背景/塗色）",
        "eyedropper": "左クリックで線/枠色に色を取得 / 右クリック(またはShift+左クリック)で背景/塗色に取得",
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setGeometry(100, 100, 1280, 820)

        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.settings = QSettings(APP_NAME, APP_NAME)
        self.recent_files = self._load_recent_files()

        self.scene = AnnotationScene(self)
        self.scene.selectionChanged.connect(self.sync_properties_from_selection)
        self.scene.stateChanged.connect(self.update_ui_state)
        self.scene.mouseSceneMoved.connect(self._update_cursor_coords)
        self.scene.statusMessageRequested.connect(self._show_status_hint)
        self.scene.cropSelectionChanged.connect(self._on_crop_selection_changed)

        self.view = CustomGraphicsView(self.scene, self)
        self.view.zoomChanged.connect(self._on_zoom_changed)
        self.view.fileDropped.connect(self._on_file_dropped)
        self.setCentralWidget(self.view)

        self.toast = ToastBanner(self.view.viewport())
        self.crop_bar = CropActionBar(self.view.viewport())
        self.crop_bar.confirmClicked.connect(self.confirm_crop)
        self.crop_bar.cancelClicked.connect(self.cancel_crop)

        self._prev_tool_before_eyedropper = "select"
        self._capture_overlay = None
        self._capture_insert_mode = False
        self._capture_was_maximized = False

        self.current_pdf_doc = None
        self.current_pdf_page = 0
        self.pdf_page_states = {}
        self.pdf_modified_pages = set()
        self.current_filename = ""
        self.current_dir = ""
        self.current_ext = ""
        self.current_file_path = ""

        # クリップボードの直近コピー元（アプリ内アイテム vs OSクリップボード）を追跡
        self._clipboard_source = "system"
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.dataChanged.connect(self._on_system_clipboard_changed)

        # 線太さ・文字サイズの手入力時デバウンスUndo保存タイマー
        self._pen_width_save_timer = QTimer(self)
        self._pen_width_save_timer.setSingleShot(True)
        self._pen_width_save_timer.setInterval(450)
        self._pen_width_save_timer.timeout.connect(self._commit_pending_property_state)
        self._pending_property_commit = False

        self.init_menubar()
        self.init_toolbar()
        self.init_statusbar()

        self.set_tool("select")
        self.update_color_icons()
        self.update_ui_state()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.toast.isVisible():
            self.toast._reposition()
        if self.crop_bar.isVisible():
            self.crop_bar.reposition()

    def keyPressEvent(self, event):
        """テキスト入力中でなければ1キーでツールや太さを瞬時に切り替える"""
        if not self._is_text_input_focused():
            mods = event.modifiers()
            if mods == Qt.KeyboardModifier.NoModifier:
                key = event.key()
                if key == Qt.Key.Key_V:
                    self.set_tool("select")
                    event.accept()
                    return
                if key == Qt.Key.Key_L:
                    self._select_line_combo_type("line")
                    event.accept()
                    return
                if key == Qt.Key.Key_A:
                    self._select_line_combo_type("arrow")
                    event.accept()
                    return
                if key == Qt.Key.Key_P:
                    self._select_line_combo_type("freehand")
                    event.accept()
                    return
                if key == Qt.Key.Key_H:
                    self._select_line_combo_type("marker")
                    event.accept()
                    return
                if key == Qt.Key.Key_R:
                    self._select_shape_combo_type("rect")
                    event.accept()
                    return
                if key == Qt.Key.Key_O:
                    self._select_shape_combo_type("ellipse")
                    event.accept()
                    return
                if key == Qt.Key.Key_M:
                    self._select_shape_combo_type("mosaic")
                    event.accept()
                    return
                if key == Qt.Key.Key_N:
                    self._select_shape_combo_type("stamp")
                    event.accept()
                    return
                if key == Qt.Key.Key_S:
                    self._select_shape_combo_type("spotlight")
                    event.accept()
                    return
                if key == Qt.Key.Key_T:
                    self.set_tool("text")
                    event.accept()
                    return
                if key == Qt.Key.Key_B:
                    self.set_tool("callout")
                    event.accept()
                    return
                if key == Qt.Key.Key_C:
                    self.set_tool("crop")
                    event.accept()
                    return
                if key == Qt.Key.Key_I:
                    self.set_tool("eyedropper")
                    event.accept()
                    return
                if key == Qt.Key.Key_BracketLeft:
                    self._step_pen_width(-1)
                    event.accept()
                    return
                if key == Qt.Key.Key_BracketRight:
                    self._step_pen_width(1)
                    event.accept()
                    return
        super().keyPressEvent(event)

    def _select_line_combo_type(self, line_type):
        line_types = ["line", "arrow", "double_arrow", "freehand", "marker"]
        if line_type in line_types:
            idx = line_types.index(line_type)
            self.line_combo.blockSignals(True)
            self.line_combo.setCurrentIndex(idx)
            self.line_combo.blockSignals(False)
            self.scene.current_line_type = line_type
            self.set_tool("line")

    def _select_shape_combo_type(self, shape_type):
        shape_types = ["rect", "rounded_rect", "ellipse", "triangle", "mosaic", "stamp", "spotlight"]
        if shape_type in shape_types:
            idx = shape_types.index(shape_type)
            self.shape_combo.blockSignals(True)
            self.shape_combo.setCurrentIndex(idx)
            self.shape_combo.blockSignals(False)
            self.scene.current_shape_type = shape_type
            self.set_tool("shape")

    def _step_pen_width(self, delta):
        steps = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 30.0, 50.0]
        cur = self.scene.pen_width
        nearest = min(range(len(steps)), key=lambda i: abs(steps[i] - cur))
        nxt = max(0, min(len(steps) - 1, nearest + delta))
        new_val = steps[nxt]
        self.width_combo.blockSignals(True)
        self.width_combo.setCurrentText(str(new_val))
        self.width_combo.blockSignals(False)
        self.change_pen_width(new_val)
        self._commit_pending_property_state()
        self.show_toast(f"線の太さ: {new_val} px", 1000)

    def _on_system_clipboard_changed(self):
        self._clipboard_source = "system"

    def mark_clipboard_source_scene(self):
        self._clipboard_source = "scene"

    def _load_recent_files(self):
        val = self.settings.value("recent_files", [])
        if isinstance(val, str):
            val = [val] if val else []
        elif not isinstance(val, list):
            val = []
        return [p for p in val if isinstance(p, str) and p][:MAX_RECENT_FILES]

    def _add_recent_file(self, file_path):
        norm = os.path.normpath(file_path)
        self.recent_files = [p for p in self.recent_files if os.path.normcase(p) != os.path.normcase(norm)]
        self.recent_files.insert(0, norm)
        self.recent_files = self.recent_files[:MAX_RECENT_FILES]
        self.settings.setValue("recent_files", self.recent_files)
        self._rebuild_recent_menu()

    def _rebuild_recent_menu(self):
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        if not self.recent_files:
            empty_act = self.recent_menu.addAction("（履歴なし）")
            empty_act.setEnabled(False)
            return
        for path in self.recent_files:
            act = self.recent_menu.addAction(os.path.basename(path))
            act.setToolTip(path)
            act.triggered.connect(lambda checked=False, p=path: self.open_file_path(p))
        self.recent_menu.addSeparator()
        clear_act = self.recent_menu.addAction("履歴をクリア")
        clear_act.triggered.connect(self._clear_recent_files)

    def _clear_recent_files(self):
        self.recent_files.clear()
        self.settings.setValue("recent_files", [])
        self._rebuild_recent_menu()

    def init_menubar(self):
        """メニューバーを構築する"""
        menubar = self.menuBar()

        # --- ファイルメニュー ---
        file_menu = menubar.addMenu("ファイル")

        new_canvas_act = QAction("新規キャンバス作成...", self)
        new_canvas_act.setShortcut(QKeySequence("Ctrl+N"))
        new_canvas_act.triggered.connect(self.create_new_canvas)
        file_menu.addAction(new_canvas_act)

        open_act = QAction("開く...", self)
        open_act.triggered.connect(self.open_file)
        file_menu.addAction(open_act)

        open_clip_act = QAction("クリップボードから新規作成", self)
        open_clip_act.setShortcut(QKeySequence("Ctrl+Shift+V"))
        open_clip_act.triggered.connect(self.open_from_clipboard)
        file_menu.addAction(open_clip_act)

        capture_act = QAction("画面を撮影して開く (範囲選択)", self)
        capture_act.setShortcut(QKeySequence("Ctrl+Shift+A"))
        capture_act.triggered.connect(lambda: self.start_screen_capture(insert_as_annotation=False))
        file_menu.addAction(capture_act)

        capture_ins_act = QAction("画面を撮影して注釈画像として挿入", self)
        capture_ins_act.triggered.connect(lambda: self.start_screen_capture(insert_as_annotation=True))
        file_menu.addAction(capture_ins_act)

        self.recent_menu = file_menu.addMenu("最近使ったファイル")
        self._rebuild_recent_menu()

        file_menu.addSeparator()

        save_act = QAction("上書き保存", self)
        save_act.triggered.connect(self.save_file)
        file_menu.addAction(save_act)

        save_as_act = QAction("名前を付けて保存...", self)
        save_as_act.triggered.connect(self.save_file_as)
        file_menu.addAction(save_as_act)

        save_proj_act = QAction("プロジェクト保存 (.hwi)", self)
        save_proj_act.triggered.connect(self.save_project)
        file_menu.addAction(save_proj_act)

        save_proj_as_act = QAction("名前を付けてプロジェクト保存...", self)
        save_proj_as_act.triggered.connect(self.save_project_as)
        file_menu.addAction(save_proj_as_act)

        file_menu.addSeparator()

        self.copy_canvas_action = QAction("完成画像をクリップボードにコピー", self)
        self.copy_canvas_action.setShortcut(QKeySequence("Ctrl+Shift+C"))
        self.copy_canvas_action.triggered.connect(self.copy_canvas_to_clipboard)
        file_menu.addAction(self.copy_canvas_action)

        file_menu.addSeparator()

        exit_act = QAction("終了", self)
        exit_act.setShortcut(QKeySequence("Alt+F4"))
        exit_act.triggered.connect(self.close)
        file_menu.addAction(exit_act)

        # --- 編集メニュー ---
        edit_menu = menubar.addMenu("編集")

        menu_undo = QAction("元に戻す (Ctrl+Z)", self)
        menu_undo.triggered.connect(self.scene.undo)
        edit_menu.addAction(menu_undo)

        menu_redo = QAction("やり直す (Ctrl+Y)", self)
        menu_redo.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        menu_redo.triggered.connect(self.scene.redo)
        edit_menu.addAction(menu_redo)

        edit_menu.addSeparator()

        copy_act = QAction("コピー", self)
        copy_act.setShortcut(QKeySequence("Ctrl+C"))
        copy_act.triggered.connect(self._shortcut_copy)
        edit_menu.addAction(copy_act)

        paste_act = QAction("貼り付け", self)
        paste_act.setShortcut(QKeySequence("Ctrl+V"))
        paste_act.triggered.connect(self._shortcut_paste)
        edit_menu.addAction(paste_act)

        dup_act = QAction("複製", self)
        dup_act.setShortcut(QKeySequence("Ctrl+D"))
        dup_act.triggered.connect(self._shortcut_duplicate)
        edit_menu.addAction(dup_act)

        sel_all_act = QAction("すべて選択", self)
        sel_all_act.setShortcut(QKeySequence("Ctrl+A"))
        sel_all_act.triggered.connect(self._shortcut_select_all)
        edit_menu.addAction(sel_all_act)

        edit_menu.addSeparator()

        crop_menu_act = QAction("切り抜き (トリミング) (C)", self)
        crop_menu_act.triggered.connect(lambda: self.set_tool("crop"))
        edit_menu.addAction(crop_menu_act)

        rotate_menu = edit_menu.addMenu("キャンバスを回転")
        rot_cw = QAction("右に90°回転", self)
        rot_cw.triggered.connect(lambda: self.rotate_canvas(90))
        rotate_menu.addAction(rot_cw)

        rot_ccw = QAction("左に90°回転", self)
        rot_ccw.triggered.connect(lambda: self.rotate_canvas(-90))
        rotate_menu.addAction(rot_ccw)

        rot_180 = QAction("180°回転", self)
        rot_180.triggered.connect(lambda: self.rotate_canvas(180))
        rotate_menu.addAction(rot_180)

        edit_menu.addSeparator()

        stamp_num_act = QAction("連番スタンプの次番号を設定...", self)
        stamp_num_act.triggered.connect(self.configure_next_stamp_number)
        edit_menu.addAction(stamp_num_act)

        # --- 描画メニュー ---
        draw_menu = menubar.addMenu("描画")

        style_menu = draw_menu.addMenu("線スタイル")
        self.pen_style_group = QActionGroup(self)
        self.pen_style_group.setExclusive(True)
        self.pen_style_actions = {}
        for label, style in (
            ("実線", Qt.PenStyle.SolidLine),
            ("破線", Qt.PenStyle.DashLine),
            ("点線", Qt.PenStyle.DotLine),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setChecked(style == Qt.PenStyle.SolidLine)
            act.triggered.connect(lambda checked=False, st=style: self.change_pen_style(st))
            self.pen_style_group.addAction(act)
            style_menu.addAction(act)
            self.pen_style_actions[style] = act

        draw_menu.addSeparator()

        font_act = QAction("テキストのフォント設定...", self)
        font_act.triggered.connect(self.choose_default_font)
        draw_menu.addAction(font_act)

        self.bold_action = QAction("太字", self)
        self.bold_action.setCheckable(True)
        self.bold_action.setShortcut(QKeySequence("Ctrl+B"))
        self.bold_action.triggered.connect(self.toggle_text_bold)
        draw_menu.addAction(self.bold_action)

        self.italic_action = QAction("斜体", self)
        self.italic_action.setCheckable(True)
        self.italic_action.setShortcut(QKeySequence("Ctrl+I"))
        self.italic_action.triggered.connect(self.toggle_text_italic)
        draw_menu.addAction(self.italic_action)

        # --- 表示メニュー ---
        view_menu = menubar.addMenu("表示")

        zi_act = QAction("拡大", self)
        zi_act.setShortcuts([QKeySequence("Ctrl++"), QKeySequence("Ctrl+=")])
        zi_act.triggered.connect(self.zoom_in)
        view_menu.addAction(zi_act)

        zo_act = QAction("縮小", self)
        zo_act.setShortcut(QKeySequence("Ctrl+-"))
        zo_act.triggered.connect(self.zoom_out)
        view_menu.addAction(zo_act)

        zr_act = QAction("100%表示", self)
        zr_act.setShortcut(QKeySequence("Ctrl+0"))
        zr_act.triggered.connect(self.zoom_reset)
        view_menu.addAction(zr_act)

        zf_act = QAction("画面に合わせる", self)
        zf_act.setShortcut(QKeySequence("Ctrl+9"))
        zf_act.triggered.connect(self.fit_to_view)
        view_menu.addAction(zf_act)

        view_menu.addSeparator()

        self.grid_action = QAction("補助グリッドを表示", self)
        self.grid_action.setCheckable(True)
        self.grid_action.setShortcut(QKeySequence("Ctrl+G"))
        self.grid_action.triggered.connect(self.toggle_grid)
        view_menu.addAction(self.grid_action)

        # --- ヘルプメニュー ---
        help_menu = menubar.addMenu("ヘルプ")

        help_center_action = QAction("📖 使い方ガイド / ヘルプセンター", self)
        help_center_action.setShortcut(QKeySequence("F1"))
        help_center_action.triggered.connect(lambda: self.show_help_center(0))
        help_menu.addAction(help_center_action)

        tool_guide_action = QAction("🎨 ツール・機能ガイド", self)
        tool_guide_action.triggered.connect(lambda: self.show_help_center(1))
        help_menu.addAction(tool_guide_action)

        shortcuts_action = QAction("⌨️ キーボードショートカット一覧", self)
        shortcuts_action.triggered.connect(self.show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)

        tips_action = QAction("💡 素早く伝えるコツ・Q&A", self)
        tips_action.triggered.connect(lambda: self.show_help_center(3))
        help_menu.addAction(tips_action)

        readme_action = QAction("📄 Readmeを表示", self)
        readme_action.triggered.connect(self.show_readme)
        help_menu.addAction(readme_action)

        help_menu.addSeparator()

        version_action = QAction("ℹ️ バージョン情報", self)
        version_action.triggered.connect(self.show_version_info)
        help_menu.addAction(version_action)

    def show_help_center(self, initial_tab=0):
        """検索対応・タブ切替式の統合ヘルプセンターを開く"""
        dialog = HelpCenterDialog(self, initial_tab=initial_tab)
        dialog.exec()

    def show_shortcuts_dialog(self):
        """統合ヘルプセンターのショートカット一覧タブを開く"""
        self.show_help_center(2)

    def show_readme(self):
        """統合ヘルプセンターのReadmeタブを開く"""
        self.show_help_center(4)

    def show_version_info(self):
        """リッチなバージョン情報ダイアログを表示する"""
        dialog = AboutDialog(self)
        dialog.exec()

    def init_toolbar(self):
        # ＝＝＝ 1段目のツールバー（ファイル操作、表示、ページ遷移） ＝＝＝
        toolbar1 = QToolBar("File and View Toolbar")
        toolbar1.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar1)

        # 1. ファイル操作
        self.save_action = QAction("💾 保存", self)
        self.save_action.setShortcut("Ctrl+S")
        self.save_action.setToolTip("上書き保存 (Ctrl+S)")
        self.save_action.triggered.connect(self.save_file)
        toolbar1.addAction(self.save_action)

        self.save_as_action = QAction("💾 名前を付けて保存", self)
        self.save_as_action.setShortcut("Ctrl+Shift+S")
        self.save_as_action.setToolTip("画像やPDFとして別名保存 (Ctrl+Shift+S)")
        self.save_as_action.triggered.connect(self.save_file_as)
        toolbar1.addAction(self.save_as_action)

        # 2. プロジェクトの個別保存
        self.save_project_action = QAction("📦 プロジェクト保存", self)
        self.save_project_action.setShortcut("Ctrl+P")
        self.save_project_action.setToolTip("再編集可能なプロジェクト(.hwi)として保存 (Ctrl+P)")
        self.save_project_action.triggered.connect(self.save_project)
        toolbar1.addAction(self.save_project_action)

        open_action = QAction("📂 開く", self)
        open_action.setShortcut("Ctrl+O")
        open_action.setToolTip("画像・PDF・プロジェクトファイルを開く (Ctrl+O)")
        open_action.triggered.connect(self.open_file)
        toolbar1.addAction(open_action)

        capture_toolbar_action = QAction("📸 画面撮影", self)
        capture_toolbar_action.setToolTip("画面の任意範囲を撮影してすぐ編集 (Ctrl+Shift+A)")
        capture_toolbar_action.triggered.connect(lambda: self.start_screen_capture(insert_as_annotation=False))
        toolbar1.addAction(capture_toolbar_action)

        copy_img_toolbar_action = QAction("📋 画像コピー", self)
        copy_img_toolbar_action.setToolTip("完成画像をクリップボードへコピーして即貼り付け共有 (Ctrl+Shift+C)")
        copy_img_toolbar_action.triggered.connect(self.copy_canvas_to_clipboard)
        toolbar1.addAction(copy_img_toolbar_action)

        toolbar1.addSeparator()

        # Undo/Redo
        self.undo_action = QAction("↩️ 戻る", self)
        self.undo_action.setShortcut("Ctrl+Z")
        self.undo_action.setToolTip("直前の操作を取り消す (Ctrl+Z)")
        self.undo_action.triggered.connect(self.scene.undo)
        toolbar1.addAction(self.undo_action)

        self.redo_action = QAction("↪️ 進む", self)
        self.redo_action.setShortcut("Ctrl+Y")
        self.redo_action.setToolTip("取り消した操作をやり直す (Ctrl+Y)")
        self.redo_action.triggered.connect(self.scene.redo)
        toolbar1.addAction(self.redo_action)

        toolbar1.addSeparator()

        # ズーム操作
        zoom_out_action = QAction("🔍- 縮小", self)
        zoom_out_action.setToolTip("表示を縮小 (Ctrl+- / Ctrl+ホイール下)")
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar1.addAction(zoom_out_action)

        zoom_in_action = QAction("🔍+ 拡大", self)
        zoom_in_action.setToolTip("表示を拡大 (Ctrl++ / Ctrl+ホイール上)")
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar1.addAction(zoom_in_action)

        zoom_reset_action = QAction("🔍 100%", self)
        zoom_reset_action.setToolTip("等倍(100%)表示に戻す (Ctrl+0)")
        zoom_reset_action.triggered.connect(self.zoom_reset)
        toolbar1.addAction(zoom_reset_action)

        zoom_fit_action = QAction("🖥️ 画面に合わせる", self)
        zoom_fit_action.setToolTip("画像全体が収まる倍率に調整 (Ctrl+9)")
        zoom_fit_action.triggered.connect(self.fit_to_view)
        toolbar1.addAction(zoom_fit_action)

        toolbar1.addSeparator()

        # クイックカラーパレット（1クリック色切替）＋ スポイト
        palette_widget = QWidget(self)
        palette_layout = QHBoxLayout(palette_widget)
        palette_layout.setContentsMargins(2, 0, 2, 0)
        palette_layout.setSpacing(3)
        for cname, chex in QUICK_COLORS:
            sw = ColorSwatchButton(cname, chex, palette_widget)
            sw.leftPicked.connect(self._apply_quick_color_left)
            sw.rightPicked.connect(self._apply_quick_color_right)
            palette_layout.addWidget(sw)
        toolbar1.addWidget(palette_widget)

        self.tool_actions = {}
        act_eyedropper = QAction("💉 スポイト", self)
        act_eyedropper.setCheckable(True)
        act_eyedropper.setToolTip("画像上の色を取得 (I) [左クリック: 線/枠色 / 右クリック: 背景/塗色]")
        act_eyedropper.triggered.connect(lambda checked: self.set_tool("eyedropper"))
        toolbar1.addAction(act_eyedropper)
        self.tool_actions["eyedropper"] = act_eyedropper

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar1.addWidget(spacer)

        # ページ遷移
        self.prev_page_action = QAction("◀ 前ページ", self)
        self.prev_page_action.setToolTip("PDFの前のページへ移動")
        self.prev_page_action.triggered.connect(lambda: self.change_page(-1))
        self.prev_page_action.setEnabled(False)
        toolbar1.addAction(self.prev_page_action)

        self.page_jump_action = QAction("", self)
        self.page_jump_action.setToolTip("クリックしてページ番号を指定移動")
        self.page_jump_action.triggered.connect(self.jump_to_pdf_page)
        self.page_jump_action.setVisible(False)
        toolbar1.addAction(self.page_jump_action)

        self.next_page_action = QAction("次ページ ▶", self)
        self.next_page_action.setToolTip("PDFの次のページへ移動")
        self.next_page_action.triggered.connect(lambda: self.change_page(1))
        self.next_page_action.setEnabled(False)
        toolbar1.addAction(self.next_page_action)

        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)

        # ＝＝＝ 2段目のツールバー（描画ツール、色、太さ・サイズ） ＝＝＝
        toolbar2 = QToolBar("Draw Toolbar")
        toolbar2.setMovable(False)
        toolbar2.setIconSize(QSize(14, 14))
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar2)

        act_sel = QAction("↖️ 選択/移動", self)
        act_sel.setCheckable(True)
        act_sel.setToolTip("注釈の選択・移動・リサイズ (V / Esc)")
        act_sel.triggered.connect(lambda checked: self.set_tool("select"))
        toolbar2.addAction(act_sel)
        self.tool_actions["select"] = act_sel

        toolbar2.addSeparator()

        act_line = QAction("📏 線", self)
        act_line.setCheckable(True)
        act_line.setToolTip("線・矢印・曲線・マーカーを描画 (L / A / P / H / Shiftで角度固定)")
        act_line.triggered.connect(lambda checked: self.set_tool("line"))
        toolbar2.addAction(act_line)
        self.tool_actions["line"] = act_line

        self.line_combo = QComboBox(self)
        self.line_combo.addItems(["直線", "矢印", "両矢印", "曲線", "マーカー"])
        self.line_combo.setToolTip("線の種類を選択")
        self.line_combo.currentIndexChanged.connect(self.change_line_type)
        toolbar2.addWidget(self.line_combo)

        act_shape = QAction("🔲 図形", self)
        act_shape.setCheckable(True)
        act_shape.setToolTip("図形・モザイク・連番スタンプ・スポットライト (R / O / M / N / S)")
        act_shape.triggered.connect(lambda checked: self.set_tool("shape"))
        toolbar2.addAction(act_shape)
        self.tool_actions["shape"] = act_shape

        self.shape_combo = QComboBox(self)
        self.shape_combo.addItems(["四角", "角丸四角", "丸/楕円", "三角", "モザイク", "連番スタンプ", "スポットライト"])
        self.shape_combo.setToolTip("図形・目隠し・スタンプ・注目枠を選択")
        self.shape_combo.currentIndexChanged.connect(self.change_shape_type)
        toolbar2.addWidget(self.shape_combo)

        act_text = QAction("🔤 文字", self)
        act_text.setCheckable(True)
        act_text.setToolTip("テキストを入力して好きな位置へ配置 (T)")
        act_text.triggered.connect(lambda checked: self.set_tool("text"))
        toolbar2.addAction(act_text)
        self.tool_actions["text"] = act_text

        act_callout = QAction("💬 吹き出し", self)
        act_callout.setCheckable(True)
        act_callout.setToolTip("矢印しっぽ付き吹き出しをドラッグで一発作成 (B)")
        act_callout.triggered.connect(lambda checked: self.set_tool("callout"))
        toolbar2.addAction(act_callout)
        self.tool_actions["callout"] = act_callout

        act_insert_img = QAction("🖼️ 画像挿入", self)
        act_insert_img.setToolTip("別の画像やPDFページを注釈として挿入")
        act_insert_img.triggered.connect(self.insert_image)
        toolbar2.addAction(act_insert_img)

        act_crop = QAction("✂️ 切り抜き", self)
        act_crop.setCheckable(True)
        act_crop.setToolTip("必要な範囲だけをドラッグしてトリミング (C)")
        act_crop.triggered.connect(lambda checked: self.set_tool("crop"))
        toolbar2.addAction(act_crop)
        self.tool_actions["crop"] = act_crop

        act_add_margin = QAction("⏹️ 余白調整", self)
        act_add_margin.setCheckable(True)
        act_add_margin.setToolTip("周囲の青いバーをドラッグして余白を拡張・削減")
        act_add_margin.triggered.connect(lambda checked: self.set_tool("margin"))
        toolbar2.addAction(act_add_margin)
        self.tool_actions["margin"] = act_add_margin

        self.tool_actions["select"].setChecked(True)
        toolbar2.addSeparator()

        self.delete_action = QAction("🗑️ 削除", self)
        self.delete_action.setToolTip("選択中の注釈を削除 (Delete)")
        self.delete_action.triggered.connect(self._safe_delete_selected)
        toolbar2.addAction(self.delete_action)

        toolbar2.addSeparator()

        # 色設定（現在の選択色をスウォッチアイコンで可視化）
        self.pen_color_action = QAction("線/枠色", self)
        self.pen_color_action.setToolTip("線・枠線・吹き出し枠・スタンプの色を選択")
        self.pen_color_action.triggered.connect(self.choose_pen_color)
        toolbar2.addAction(self.pen_color_action)

        self.text_color_action = QAction("文字色", self)
        self.text_color_action.setToolTip("テキスト・吹き出しの文字色を選択")
        self.text_color_action.triggered.connect(self.choose_text_color)
        toolbar2.addAction(self.text_color_action)

        self.brush_color_action = QAction("背景/塗色", self)
        self.brush_color_action.setToolTip("図形・吹き出し・文字背景・余白の塗りつぶし色を選択")
        self.brush_color_action.triggered.connect(self.choose_brush_color)
        toolbar2.addAction(self.brush_color_action)

        self.fill_combo = QComboBox(self)
        self.fill_combo.addItems(["透過(枠)", "塗りつぶし", "半透明塗り"])
        self.fill_combo.setToolTip("図形やテキスト背景の塗りつぶしモードを選択")
        self.fill_combo.currentIndexChanged.connect(self.change_fill_mode)
        toolbar2.addWidget(self.fill_combo)

        toolbar2.addSeparator()

        # --- 図形・線の太さコントロール (分離) ---
        toolbar2.addWidget(QLabel("🖊️ 線太さ:"))
        self.width_combo = QComboBox(self)
        self.width_combo.setEditable(True)
        self.width_combo.setValidator(QDoubleValidator(0.1, 200.0, 1, self.width_combo))
        width_options = ["0.5", "1.0", "1.5", "2.0", "3.0", "4.0", "5.0", "6.0", "8.0", "10.0", "12.0", "15.0", "20.0", "30.0", "50.0"]
        self.width_combo.addItems(width_options)
        self.width_combo.setCurrentText(str(float(self.scene.pen_width)))
        self.width_combo.setToolTip("線・図形枠の太さを指定")
        self.width_combo.activated.connect(self._on_width_combo_activated)
        self.width_combo.currentTextChanged.connect(self.change_pen_width_text)
        if self.width_combo.lineEdit():
            self.width_combo.lineEdit().editingFinished.connect(self._commit_pending_property_state)
        toolbar2.addWidget(self.width_combo)

        # --- 文字のフォントサイズコントロール (分離) ---
        toolbar2.addWidget(QLabel("🔤 文字サイズ:"))
        self.font_size_combo = QComboBox(self)
        self.font_size_combo.setEditable(True)
        self.font_size_combo.setValidator(QDoubleValidator(1.0, 500.0, 1, self.font_size_combo))
        font_size_options = ["8", "10", "12", "14", "16", "18", "20", "24", "28", "32", "36", "48", "60", "72", "96", "120"]
        self.font_size_combo.addItems(font_size_options)
        self.font_size_combo.setCurrentText(str(int(self.scene.current_font_size)))
        self.font_size_combo.setToolTip("テキストの文字サイズ(pt)を指定")
        self.font_size_combo.activated.connect(self._on_font_size_combo_activated)
        self.font_size_combo.currentTextChanged.connect(self.change_font_size_text)
        if self.font_size_combo.lineEdit():
            self.font_size_combo.lineEdit().editingFinished.connect(self._commit_pending_property_state)
        toolbar2.addWidget(self.font_size_combo)

    def init_statusbar(self):
        """現在のツール・座標・キャンバスサイズ・ズーム率を表示するステータスバーを構築"""
        sb = QStatusBar(self)
        self.setStatusBar(sb)

        self.status_hint_label = QLabel(self.TOOL_HINTS["select"])
        self.status_hint_label.setStyleSheet("color: #333333; padding: 2px 6px;")
        sb.addWidget(self.status_hint_label, 1)

        self.status_coords_label = QLabel("X: -, Y: -")
        sb.addPermanentWidget(self.status_coords_label)

        self.status_canvas_label = QLabel("キャンバス: なし")
        sb.addPermanentWidget(self.status_canvas_label)

        self.status_zoom_label = QLabel("ズーム: 100%")
        sb.addPermanentWidget(self.status_zoom_label)

    def _update_cursor_coords(self, scene_pos):
        if self.scene.bg_item is not None:
            self.status_coords_label.setText(f"X: {int(round(scene_pos.x()))}, Y: {int(round(scene_pos.y()))}")
        else:
            self.status_coords_label.setText("X: -, Y: -")

    def _show_status_hint(self, text, timeout_ms=0):
        if timeout_ms > 0:
            self.statusBar().showMessage(text, timeout_ms)
        else:
            self.status_hint_label.setText(text)

    def _on_zoom_changed(self, zoom_factor):
        pct = int(round(zoom_factor * 100.0))
        self.status_zoom_label.setText(f"ズーム: {pct}%")
        if self.scene.current_tool == "margin":
            self.scene.update_margin_handles()
        self.scene.invalidate_handles()

    def _on_file_dropped(self, file_path, insert_as_annotation):
        if insert_as_annotation and self.scene.bg_item is not None and os.path.splitext(file_path)[1].lower() != ".hwi":
            self._insert_image_from_path(file_path)
        else:
            self.open_file_path(file_path)

    def update_color_icons(self):
        """ツールバーの色ボタンに現在の選択色をリアルタイム反映する"""
        self.pen_color_action.setIcon(create_color_icon(self.scene.current_pen_color, 14))
        self.text_color_action.setIcon(create_color_icon(self.scene.current_text_color, 14))
        self.brush_color_action.setIcon(create_color_icon(self.scene.current_brush_color, 14))

    def _has_any_unsaved_changes(self):
        return self.scene.has_unsaved_changes or bool(self.pdf_modified_pages)

    def update_window_title(self):
        base = APP_NAME
        if self.current_file_path:
            name = os.path.basename(self.current_file_path)
            if self.current_pdf_doc:
                title = f"{base} - {name} (Page {self.current_pdf_page + 1}/{len(self.current_pdf_doc)})"
            else:
                title = f"{base} - {name}"
        elif self.scene.bg_item is not None:
            title = f"{base} - 無題キャンバス"
        else:
            title = base

        if self._has_any_unsaved_changes():
            title = f"* {title}"
        self.setWindowTitle(title)

    def update_ui_state(self):
        """ボタンの有効状態・タイトル・キャンバス情報表示を一括同期する"""
        self.undo_action.setEnabled(self.scene.can_undo())
        self.redo_action.setEnabled(self.scene.can_redo())

        has_selection = any(
            it != self.scene.bg_item and not isinstance(it, MarginHandleItem)
            for it in self.scene.selectedItems()
        )
        self.delete_action.setEnabled(has_selection)

        rect = self.scene.sceneRect()
        if self.scene.bg_item is not None and not rect.isEmpty():
            item_count = len(self.scene.annotation_items())
            self.status_canvas_label.setText(
                f"サイズ: {int(round(rect.width()))} × {int(round(rect.height()))} px  (注釈: {item_count})"
            )
        else:
            self.status_canvas_label.setText("キャンバス: なし")

        if self.current_pdf_doc is not None and len(self.current_pdf_doc) > 0:
            total = len(self.current_pdf_doc)
            self.prev_page_action.setEnabled(self.current_pdf_page > 0)
            self.next_page_action.setEnabled(self.current_pdf_page < total - 1)
            self.page_jump_action.setText(f"{self.current_pdf_page + 1} / {total}")
            self.page_jump_action.setVisible(True)
        else:
            self.prev_page_action.setEnabled(False)
            self.next_page_action.setEnabled(False)
            self.page_jump_action.setVisible(False)

        self.update_window_title()

    def _is_text_input_focused(self):
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QTextEdit, QSpinBox))

    def _safe_delete_selected(self):
        if not self._is_text_input_focused():
            self.scene.delete_selected_items()

    def _shortcut_copy(self):
        if self._is_text_input_focused():
            w = QApplication.focusWidget()
            if hasattr(w, "copy"):
                w.copy()
            return
        if self.scene.copy_selected_items():
            self.show_toast("選択した注釈をコピーしました", 1500)

    def _shortcut_paste(self):
        if self._is_text_input_focused():
            w = QApplication.focusWidget()
            if hasattr(w, "paste"):
                w.paste()
            return
        self.smart_paste()

    def _shortcut_duplicate(self):
        if not self._is_text_input_focused():
            self.scene.duplicate_selected_items()

    def _shortcut_select_all(self):
        if self._is_text_input_focused():
            w = QApplication.focusWidget()
            if hasattr(w, "selectAll"):
                w.selectAll()
            return
        self.set_tool("select")
        self.scene.select_all_items()

    def smart_paste(self, scene_pos=None):
        """直近のコピー元に応じてシーン内注釈またはクリップボード画像を賢く貼り付ける"""
        clipboard = QGuiApplication.clipboard()
        has_clip_image = bool(clipboard and clipboard.mimeData() and clipboard.mimeData().hasImage())

        if self._clipboard_source == "scene" and self.scene.copied_items:
            self.scene.paste_items(scene_pos)
            return

        if has_clip_image:
            img = clipboard.image()
            if not img.isNull():
                pixmap = QPixmap.fromImage(img)
                if self.scene.bg_item is None:
                    self._load_pixmap_as_new_canvas(pixmap, "クリップボード画像")
                else:
                    self._insert_pixmap_annotation(pixmap, scene_pos)
                return

        if self.scene.copied_items:
            self.scene.paste_items(scene_pos)

    def set_tool(self, tool_id):
        if tool_id != "text" and self.scene.pending_text_item is not None:
            self.scene.removeItem(self.scene.pending_text_item)
            self.scene.pending_text_item = None

        if tool_id != "crop":
            self.scene.clear_crop_selection()
            self.crop_bar.hide()

        if tool_id != "eyedropper":
            self.scene.clear_eyedropper()

        if tool_id in ("margin", "crop", "eyedropper") and self.scene.bg_item is None:
            tool_names = {"margin": "余白調整", "crop": "切り抜き", "eyedropper": "スポイト"}
            QMessageBox.information(
                self, "案内",
                f"{tool_names[tool_id]}を使うには、先に画像やPDFを開くか画面撮影・新規キャンバス作成を行ってください。"
            )
            tool_id = "select"

        if tool_id == "eyedropper":
            if self.scene.current_tool not in ("eyedropper", "crop", "margin"):
                self._prev_tool_before_eyedropper = self.scene.current_tool
            sampled = self._render_scene_to_image(self.scene, Qt.GlobalColor.white)
            self.scene.set_eyedropper_image(sampled)

        if tool_id in ("line", "shape", "text", "callout") and self.scene.bg_item is None:
            blank = QPixmap(1280, 720)
            blank.fill(Qt.GlobalColor.white)
            self._load_pixmap_as_new_canvas(blank, "canvas")
            self.show_toast("白紙キャンバス (1280 × 720 px) を自動作成しました", 2000)

        if tool_id == "text":
            dlg = QuickTextDialog(
                self,
                title="テキスト入力",
                prompt="キャンバスに配置する文字を入力してください (Ctrl+Enterで確定):",
                recent_texts=self.scene.recent_texts,
                show_bg_option=True,
                initial_bg_checked=self.scene.use_fill,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.get_text():
                text = dlg.get_text()
                self.scene.remember_recent_text(text)
                want_bg = dlg.want_background()
                font = QFont(self.scene.current_font_family)
                font.setPointSizeF(max(4.0, self.scene.current_font_size))
                font.setBold(self.scene.current_font_bold)
                font.setItalic(self.scene.current_font_italic)

                if want_bg:
                    bg_color = QColor(self.scene.current_brush_color)
                    if self.scene.current_fill_mode == 2 and bg_color.alpha() == 255:
                        bg_color.setAlpha(95)
                    brush = QBrush(bg_color)
                    pen = QPen(self.scene.current_pen_color)
                    pen.setWidthF(self.scene.pen_width)
                    pen.setStyle(self.scene.current_pen_style)
                else:
                    brush = QBrush(Qt.BrushStyle.NoBrush)
                    pen = QPen(Qt.PenStyle.NoPen)

                text_item = CustomTextItem(text)
                text_item.setFont(font)
                text_item.setDefaultTextColor(self.scene.current_text_color)
                text_item.setBrush(brush)
                text_item.setPen(pen)
                text_item.setZValue(self.scene.get_next_z_value())

                # 最初から現在のカーソル位置付近に表示して違和感をなくす
                vp_pos = self.view.viewport().mapFromGlobal(QCursor.pos())
                if self.view.viewport().rect().contains(vp_pos):
                    init_pos = self.view.mapToScene(vp_pos)
                else:
                    init_pos = self.view.mapToScene(self.view.viewport().rect().center())
                text_item.setPos(init_pos)

                self.scene.addItem(text_item)
                self.scene.pending_text_item = text_item
            else:
                self.set_tool("select")
                return

        self.scene.current_tool = tool_id
        for tid, action in self.tool_actions.items():
            action.setChecked(tid == tool_id)

        self.scene.update_margin_handles()
        self.scene.invalidate_handles()

        if tool_id == "select":
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
            self.view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        elif tool_id == "margin":
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.scene.clearSelection()
            self.view.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
            self.scene.clearSelection()
            self.view.viewport().setCursor(Qt.CursorShape.CrossCursor)

        self.status_hint_label.setText(self.TOOL_HINTS.get(tool_id, ""))
        self.view.setFocus()

    def change_line_type(self, index):
        line_types = ["line", "arrow", "double_arrow", "freehand", "marker"]
        if 0 <= index < len(line_types):
            self.scene.current_line_type = line_types[index]
            self.set_tool("line")

    def change_shape_type(self, index):
        shape_types = ["rect", "rounded_rect", "ellipse", "triangle", "mosaic", "stamp", "spotlight"]
        if 0 <= index < len(shape_types):
            self.scene.current_shape_type = shape_types[index]
            self.set_tool("shape")

    def change_pen_style(self, pen_style):
        self.scene.apply_pen_style_to_selected(pen_style)
        act = self.pen_style_actions.get(pen_style)
        if act:
            act.setChecked(True)

    def choose_default_font(self):
        current = QFont(self.scene.current_font_family)
        current.setPointSizeF(max(4.0, self.scene.current_font_size))
        current.setBold(self.scene.current_font_bold)
        current.setItalic(self.scene.current_font_italic)

        font, ok = QFontDialog.getFont(current, self, "テキストのフォント設定")
        if ok:
            self.scene.current_font_family = font.family()
            if font.pointSizeF() > 0:
                self.scene.current_font_size = font.pointSizeF()
                self.font_size_combo.blockSignals(True)
                self.font_size_combo.setCurrentText(str(round(self.scene.current_font_size, 1)))
                self.font_size_combo.blockSignals(False)
            self.scene.current_font_bold = font.bold()
            self.scene.current_font_italic = font.italic()
            self.bold_action.setChecked(font.bold())
            self.italic_action.setChecked(font.italic())

            changed = False
            for item in self.scene.selectedItems():
                if isinstance(item, (CustomTextItem, CalloutItem)):
                    item.setFont(font)
                    changed = True
            if changed:
                self.scene.has_unsaved_changes = True
                self.scene.save_state()
                self.scene.invalidate_handles()

    def toggle_text_bold(self, checked):
        self.scene.current_font_bold = bool(checked)
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomTextItem, CalloutItem)):
                f = item.font()
                f.setBold(bool(checked))
                item.setFont(f)
                changed = True
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()
            self.scene.invalidate_handles()

    def toggle_text_italic(self, checked):
        self.scene.current_font_italic = bool(checked)
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomTextItem, CalloutItem)):
                f = item.font()
                f.setItalic(bool(checked))
                item.setFont(f)
                changed = True
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()
            self.scene.invalidate_handles()

    def toggle_grid(self, checked):
        self.scene.show_grid = bool(checked)
        self.scene.invalidate(self.scene.sceneRect(), QGraphicsScene.SceneLayer.ForegroundLayer)

    def configure_next_stamp_number(self):
        val, ok = QInputDialog.getInt(
            self, "連番スタンプの開始番号",
            "次に配置する連番スタンプの番号を入力してください:",
            self.scene.next_stamp_number, 1, 999, 1
        )
        if ok:
            self.scene.next_stamp_number = val
            self.show_toast(f"次のスタンプ番号を {val} に設定しました", 2000)

    def zoom_in(self):
        self.view.zoom_by(1.25)

    def zoom_out(self):
        self.view.zoom_by(0.8)

    def zoom_reset(self):
        self.view.reset_zoom()

    def fit_to_view(self):
        self.view.fit_scene_in_view()

    def sync_properties_from_selection(self):
        """選択アイテムからの各種プロパティ（色・線スタイル・太さ・文字サイズ・書式）同期処理"""
        items = [
            it for it in self.scene.selectedItems()
            if it != self.scene.bg_item and not isinstance(it, MarginHandleItem)
        ]
        if not items:
            return

        item = items[-1]

        self.width_combo.blockSignals(True)
        self.font_size_combo.blockSignals(True)
        self.fill_combo.blockSignals(True)

        if isinstance(item, (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, SpotlightItem)):
            pen = item.pen()
            self.scene.current_pen_color = pen.color()
            self.scene.pen_width = max(0.5, pen.widthF())
            self.scene.current_pen_style = pen.style()
            if pen.style() in self.pen_style_actions:
                self.pen_style_actions[pen.style()].setChecked(True)
            self.width_combo.setCurrentText(str(round(self.scene.pen_width, 1)))

            if hasattr(item, "brush"):
                brush = item.brush()
                if brush.style() != Qt.BrushStyle.NoBrush:
                    bc = QColor(brush.color())
                    if bc.alpha() < 255:
                        self.scene.current_fill_mode = 2
                        self.fill_combo.setCurrentIndex(2)
                        bc.setAlpha(255)
                    else:
                        self.scene.current_fill_mode = 1
                        self.fill_combo.setCurrentIndex(1)
                    self.scene.current_brush_color = bc
                else:
                    self.scene.current_fill_mode = 0
                    self.fill_combo.setCurrentIndex(0)

        elif isinstance(item, (CustomTextItem, CalloutItem)):
            self.scene.current_text_color = item.defaultTextColor()
            font = item.font()
            self.scene.current_font_family = font.family()
            if font.pointSizeF() > 0:
                self.scene.current_font_size = font.pointSizeF()
            self.scene.current_font_bold = font.bold()
            self.scene.current_font_italic = font.italic()
            self.bold_action.setChecked(font.bold())
            self.italic_action.setChecked(font.italic())
            self.font_size_combo.setCurrentText(str(round(self.scene.current_font_size, 1)))

            pen = item.pen()
            if pen.style() != Qt.PenStyle.NoPen:
                self.scene.current_pen_color = pen.color()
                self.scene.pen_width = max(0.5, pen.widthF())
                self.scene.current_pen_style = pen.style()
                if pen.style() in self.pen_style_actions:
                    self.pen_style_actions[pen.style()].setChecked(True)
                self.width_combo.setCurrentText(str(round(self.scene.pen_width, 1)))

            brush = item.brush()
            if brush.style() != Qt.BrushStyle.NoBrush:
                bc = QColor(brush.color())
                if bc.alpha() < 255:
                    self.scene.current_fill_mode = 2
                    self.fill_combo.setCurrentIndex(2)
                    bc.setAlpha(255)
                else:
                    self.scene.current_fill_mode = 1
                    self.fill_combo.setCurrentIndex(1)
                self.scene.current_brush_color = bc
            else:
                self.scene.current_fill_mode = 0
                self.fill_combo.setCurrentIndex(0)

        elif isinstance(item, NumberStampItem):
            self.scene.current_pen_color = QColor(item.bg_color())
            self.scene.current_text_color = QColor(item.text_color())

        self.width_combo.blockSignals(False)
        self.font_size_combo.blockSignals(False)
        self.fill_combo.blockSignals(False)
        self.update_color_icons()

    def _apply_quick_color_left(self, color, shift_held):
        selected = [
            it for it in self.scene.selectedItems()
            if it != self.scene.bg_item and not isinstance(it, MarginHandleItem)
        ]
        if shift_held or (selected and all(isinstance(it, CustomTextItem) for it in selected)):
            self._apply_text_color_value(color)
            self.show_toast(f"文字色を {color.name().upper()} に変更しました", 1200)
        else:
            self._apply_pen_color_value(color)
            self.show_toast(f"線/枠色を {color.name().upper()} に変更しました", 1200)

    def _apply_quick_color_right(self, color):
        self._apply_brush_color_value(color, enable_fill_if_needed=True)
        self.show_toast(f"背景/塗色を {color.name().upper()} に変更しました", 1200)

    def apply_eyedropper_color(self, color, target="pen"):
        if target == "brush":
            self._apply_brush_color_value(color, enable_fill_if_needed=True)
            self.show_toast(f"スポイト: 背景/塗色に {color.name().upper()} を取得しました", 2000)
        else:
            self._apply_pen_color_value(color)
            self.show_toast(f"スポイト: 線/枠色に {color.name().upper()} を取得しました", 2000)
        self.set_tool(self._prev_tool_before_eyedropper or "select")

    def _apply_pen_color_value(self, color):
        self.scene.current_pen_color = QColor(color)
        self.update_color_icons()
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, CalloutItem, SpotlightItem)):
                pen = QPen(item.pen())
                pen.setColor(color)
                item.setPen(pen)
                changed = True
            elif isinstance(item, CustomTextItem):
                if item.pen().style() != Qt.PenStyle.NoPen:
                    pen = QPen(item.pen())
                    pen.setColor(color)
                    item.setPen(pen)
                    changed = True
            elif isinstance(item, NumberStampItem):
                item.setBgColor(color)
                changed = True
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()

    def _apply_text_color_value(self, color):
        self.scene.current_text_color = QColor(color)
        self.update_color_icons()
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomTextItem, CalloutItem)):
                item.setDefaultTextColor(color)
                changed = True
            elif isinstance(item, NumberStampItem):
                item.setTextColor(color)
                changed = True
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()

    def _apply_brush_color_value(self, color, enable_fill_if_needed=False):
        self.scene.current_brush_color = QColor(color)
        if enable_fill_if_needed and not self.scene.use_fill:
            self.scene.current_fill_mode = 1
            self.fill_combo.blockSignals(True)
            self.fill_combo.setCurrentIndex(1)
            self.fill_combo.blockSignals(False)
        self.update_color_icons()
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, CustomTextItem, CalloutItem)):
                if item.brush().style() != Qt.BrushStyle.NoBrush or self.scene.use_fill:
                    item.setBrush(self.scene.get_current_brush())
                    changed = True
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()

    def choose_pen_color(self):
        """線や枠・スタンプの色を変更"""
        color = QColorDialog.getColor(
            self.scene.current_pen_color, self, "線・枠の色を選択",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            self._apply_pen_color_value(color)

    def choose_text_color(self):
        """文字の色を変更"""
        color = QColorDialog.getColor(
            self.scene.current_text_color, self, "文字の色を選択",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            self._apply_text_color_value(color)

    def choose_brush_color(self):
        """背景や塗りつぶしの色を変更"""
        color = QColorDialog.getColor(
            self.scene.current_brush_color, self, "背景・塗りつぶしの色を選択",
            QColorDialog.ColorDialogOption.ShowAlphaChannel
        )
        if color.isValid():
            self._apply_brush_color_value(color)

    def change_fill_mode(self, index):
        """透過モード・塗りつぶしモード・半透明塗りを切り替え"""
        self.scene.current_fill_mode = index
        brush = self.scene.get_current_brush()
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, CalloutItem)):
                item.setBrush(brush)
                changed = True
            elif isinstance(item, CustomTextItem):
                item.setBrush(brush)
                if self.scene.use_fill:
                    pen = QPen(self.scene.current_pen_color)
                    pen.setWidthF(self.scene.pen_width)
                    pen.setStyle(self.scene.current_pen_style)
                    item.setPen(pen)
                else:
                    item.setPen(QPen(Qt.PenStyle.NoPen))
                changed = True

        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()

    def _commit_pending_property_state(self):
        self._pen_width_save_timer.stop()
        if self._pending_property_commit:
            self._pending_property_commit = False
            self.scene.has_unsaved_changes = True
            self.scene.save_state()

    def _on_width_combo_activated(self, _index):
        self._commit_pending_property_state()

    def _on_font_size_combo_activated(self, _index):
        self._commit_pending_property_state()

    def change_pen_width_text(self, text):
        """線の太さ（図形/線）用コンボボックスの変更ハンドラ"""
        try:
            value = float(text)
            if value < 0.1:
                value = 0.1
            self.change_pen_width(value)
        except ValueError:
            pass

    def change_pen_width(self, value):
        """図形や線の太さ（枠線）を更新（手入力時はUndo履歴をデバウンス）"""
        self.scene.pen_width = value
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, CalloutItem, SpotlightItem)):
                pen = QPen(item.pen())
                pen.setWidthF(value)
                item.setPen(pen)
                changed = True
            elif isinstance(item, CustomTextItem):
                if item.pen().style() != Qt.PenStyle.NoPen:
                    pen = QPen(item.pen())
                    pen.setWidthF(value)
                    item.setPen(pen)
                    changed = True
        if changed:
            self._pending_property_commit = True
            self._pen_width_save_timer.start()

    def change_font_size_text(self, text):
        """文字サイズ（テキスト）用コンボボックスの変更ハンドラ"""
        try:
            value = float(text)
            if value < 1.0:
                value = 1.0
            self.change_font_size(value)
        except ValueError:
            pass

    def change_font_size(self, value):
        """テキスト・吹き出しのフォントサイズを更新（図形の太さとは独立）"""
        self.scene.current_font_size = value
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomTextItem, CalloutItem)):
                font = item.font()
                font.setPointSizeF(value)
                item.setFont(font)
                changed = True
        if changed:
            self._pending_property_commit = True
            self._pen_width_save_timer.start()
            self.scene.invalidate_handles()

    def check_unsaved_changes(self):
        self._commit_pending_property_state()
        if self._has_any_unsaved_changes():
            reply = QMessageBox.question(
                self, "確認", "保存されていない変更があります。\n現在の変更を破棄してもよろしいですか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            return reply == QMessageBox.StandardButton.Yes
        return True

    def _close_current_pdf(self):
        if self.current_pdf_doc is not None:
            try:
                self.current_pdf_doc.close()
            except Exception:
                pass
            self.current_pdf_doc = None
        self.current_pdf_page = 0
        self.pdf_page_states.clear()
        self.pdf_modified_pages.clear()

    def _load_pixmap_as_new_canvas(self, pixmap, display_name=""):
        self._close_current_pdf()
        self.current_file_path = ""
        self.current_filename = display_name
        self.current_ext = ""
        self.zoom_reset()
        self.scene.set_background(pixmap)
        self.fit_to_view()
        self.update_ui_state()

    def create_new_canvas(self):
        """新規白紙キャンバスを作成する"""
        if not self.check_unsaved_changes():
            return
        dialog = NewCanvasDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            w, h, bg_color = dialog.get_values()
            pixmap = QPixmap(w, h)
            pixmap.fill(bg_color)
            self._load_pixmap_as_new_canvas(pixmap, "canvas")
            self.show_toast(f"新規キャンバス ({w} × {h} px) を作成しました")

    def open_from_clipboard(self):
        """クリップボードにある画像を新規キャンバスとして開く"""
        clipboard = QGuiApplication.clipboard()
        if not clipboard or not clipboard.mimeData() or not clipboard.mimeData().hasImage():
            QMessageBox.information(self, "案内", "クリップボードに画像が見つかりませんでした。")
            return
        img = clipboard.image()
        if img.isNull():
            QMessageBox.warning(self, "エラー", "クリップボードから画像を読み込めませんでした。")
            return
        if not self.check_unsaved_changes():
            return
        self._load_pixmap_as_new_canvas(QPixmap.fromImage(img), "clipboard")
        self.show_toast("クリップボードの画像を開きました")

    def open_file(self):
        if not self.check_unsaved_changes():
            return
        default_dir = self.current_dir if self.current_dir else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ファイルを開く", default_dir,
            "Supported Files (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.pdf *.hwi);;"
            "Images/PDF (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.pdf);;"
            "HandwrittenImage Projects (*.hwi)"
        )
        if file_path:
            self.open_file_path(file_path, skip_confirm=True)

    def open_file_path(self, file_path, skip_confirm=False):
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "エラー", f"ファイルが見つかりませんでした。\n{file_path}")
            self.recent_files = [p for p in self.recent_files if os.path.normcase(p) != os.path.normcase(file_path)]
            self.settings.setValue("recent_files", self.recent_files)
            self._rebuild_recent_menu()
            return

        if not skip_confirm and not self.check_unsaved_changes():
            return

        ext = os.path.splitext(file_path)[1].lower()
        if ext not in SUPPORTED_OPEN_EXTS:
            QMessageBox.warning(self, "エラー", f"未対応のファイル形式です: {ext}")
            return

        try:
            if ext == ".hwi":
                with open(file_path, "r", encoding="utf-8") as f:
                    project_data = json.load(f)
                self._close_current_pdf()
                self.zoom_reset()
                deserialize_project(project_data, self.scene)
                self.current_file_path = file_path
                self.current_dir = os.path.dirname(file_path)
                self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                self.current_ext = ".hwi"
                self.fit_to_view()
                self._add_recent_file(file_path)
                self.update_ui_state()

            elif ext == ".pdf":
                doc = pymupdf.open(file_path)
                if doc.needs_pass:
                    pw, ok = QInputDialog.getText(
                        self, "パスワード保護されたPDF", "PDFを開くパスワードを入力してください:",
                        QLineEdit.EchoMode.Password
                    )
                    if not ok or not doc.authenticate(pw):
                        doc.close()
                        if ok:
                            QMessageBox.warning(self, "エラー", "パスワードが正しくありません。")
                        return
                if len(doc) == 0:
                    doc.close()
                    QMessageBox.warning(self, "エラー", "このPDFにはページが含まれていません。")
                    return

                self._close_current_pdf()
                self.current_pdf_doc = doc
                self.current_pdf_page = 0
                self.current_file_path = file_path
                self.current_dir = os.path.dirname(file_path)
                self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                self.current_ext = ".pdf"
                self.zoom_reset()
                self.load_pdf_page()
                self._add_recent_file(file_path)
                self.update_ui_state()

            else:
                reader = QImageReader(file_path)
                reader.setAutoTransform(True)
                image = reader.read()
                if image.isNull():
                    QMessageBox.warning(self, "エラー", f"画像の読み込みに失敗しました。\n{reader.errorString()}")
                    return
                self._close_current_pdf()
                self.current_file_path = file_path
                self.current_dir = os.path.dirname(file_path)
                self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                self.current_ext = ext
                self.zoom_reset()
                self.scene.set_background(QPixmap.fromImage(image))
                self.fit_to_view()
                self._add_recent_file(file_path)
                self.update_ui_state()

        except Exception as e:
            QMessageBox.warning(self, "エラー", f"ファイルの読み込みに失敗しました。\n{e}")

    def _stash_current_pdf_page_state(self):
        """現在のPDFページの注釈状態をメモリへ退避する"""
        if self.current_pdf_doc is None or self.scene.bg_item is None:
            return
        self._commit_pending_property_state()
        if self.scene.has_unsaved_changes or self.current_pdf_page in self.pdf_modified_pages:
            self.pdf_page_states[self.current_pdf_page] = self.scene.get_scene_state()
            self.pdf_modified_pages.add(self.current_pdf_page)

    def load_pdf_page(self):
        if self.current_pdf_doc is None:
            return
        if self.current_pdf_page in self.pdf_page_states:
            state = self.pdf_page_states[self.current_pdf_page]
            self.scene.load_state_as_clean(state, is_modified=(self.current_pdf_page in self.pdf_modified_pages))
        else:
            page = self.current_pdf_doc.load_page(self.current_pdf_page)
            pixmap = render_pdf_page_to_pixmap(page)
            self.scene.set_background(pixmap, reset_stamp_counter=False)
        self.fit_to_view()
        self.update_ui_state()

    def change_page(self, delta):
        if self.current_pdf_doc is None:
            return
        new_page = self.current_pdf_page + delta
        if 0 <= new_page < len(self.current_pdf_doc):
            self._stash_current_pdf_page_state()
            self.current_pdf_page = new_page
            self.load_pdf_page()

    def jump_to_pdf_page(self):
        if self.current_pdf_doc is None or len(self.current_pdf_doc) <= 1:
            return
        total = len(self.current_pdf_doc)
        val, ok = QInputDialog.getInt(
            self, "ページ移動", f"移動先のページ番号を入力してください (1〜{total}):",
            self.current_pdf_page + 1, 1, total, 1
        )
        if ok and (val - 1) != self.current_pdf_page:
            self._stash_current_pdf_page_state()
            self.current_pdf_page = val - 1
            self.load_pdf_page()

    def insert_image(self):
        """外部画像またはPDFページを注釈としてキャンバスの中に挿入する"""
        default_dir = self.current_dir if self.current_dir else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "挿入する画像またはPDFを選択", default_dir,
            "Images/PDF (*.png *.jpg *.jpeg *.bmp *.gif *.webp *.pdf)"
        )
        if file_path:
            self._insert_image_from_path(file_path)

    def _insert_image_from_path(self, file_path):
        ext = os.path.splitext(file_path)[1].lower()
        pixmap = None

        try:
            if ext == ".pdf":
                doc = pymupdf.open(file_path)
                try:
                    if doc.needs_pass:
                        pw, ok = QInputDialog.getText(
                            self, "パスワード保護されたPDF", "PDFのパスワードを入力してください:",
                            QLineEdit.EchoMode.Password
                        )
                        if not ok or not doc.authenticate(pw):
                            if ok:
                                QMessageBox.warning(self, "エラー", "パスワードが正しくありません。")
                            return
                    if len(doc) > 0:
                        page_num = 0
                        if len(doc) > 1:
                            val, ok = QInputDialog.getInt(
                                self, "ページ選択", f"挿入するPDFのページ番号を入力してください (1-{len(doc)}):",
                                1, 1, len(doc), 1
                            )
                            if ok:
                                page_num = val - 1
                            else:
                                return
                        page = doc.load_page(page_num)
                        pixmap = render_pdf_page_to_pixmap(page)
                finally:
                    doc.close()
            else:
                reader = QImageReader(file_path)
                reader.setAutoTransform(True)
                image = reader.read()
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image)

            if pixmap and not pixmap.isNull():
                self._insert_pixmap_annotation(pixmap)
            else:
                QMessageBox.warning(self, "エラー", "ファイルの読み込みに失敗しました。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"画像の挿入中にエラーが発生しました。\n{e}")

    def _insert_pixmap_annotation(self, pixmap, scene_pos=None):
        if scene_pos is None:
            view_rect = self.view.viewport().rect()
            scene_pos = self.view.mapToScene(view_rect.center())

        w = float(pixmap.width())
        h = float(pixmap.height())
        max_size = 320.0
        if w > max_size or h > max_size:
            ratio = min(max_size / w, max_size / h)
            w *= ratio
            h *= ratio

        rect = QRectF(0.0, 0.0, w, h)
        item = CustomPixmapItem(pixmap, rect)
        item.setPos(scene_pos - QPointF(w * 0.5, h * 0.5))
        item.setZValue(self.scene.get_next_z_value())
        self.scene.addItem(item)

        self.scene.clearSelection()
        item.setSelected(True)
        self.scene.has_unsaved_changes = True
        self.scene.save_state()
        self.set_tool("select")

    def rotate_canvas(self, angle_deg):
        """背景画像とすべての注釈を90度単位で回転する（Undo完全対応）"""
        if self.scene.bg_item is None:
            QMessageBox.information(self, "案内", "回転する画像が開かれていません。")
            return

        bg = self.scene.bg_item.pixmap()
        old_w = float(bg.width())
        old_h = float(bg.height())
        if old_w <= 0 or old_h <= 0:
            return

        t_img = QTransform().rotate(angle_deg)
        new_bg = bg.transformed(t_img, Qt.TransformationMode.SmoothTransformation)

        def rot_pt(p):
            if angle_deg == 90:
                return QPointF(old_h - p.y(), p.x())
            if angle_deg == -90:
                return QPointF(p.y(), old_w - p.x())
            return QPointF(old_w - p.x(), old_h - p.y())

        t_scene = QTransform()
        if angle_deg == 90:
            t_scene.translate(old_h, 0.0)
            t_scene.rotate(90.0)
        elif angle_deg == -90:
            t_scene.translate(0.0, old_w)
            t_scene.rotate(-90.0)
        else:
            t_scene.translate(old_w, old_h)
            t_scene.rotate(180.0)

        for item in self.scene.annotation_items():
            if isinstance(item, CustomLineItem):
                p1 = rot_pt(item.mapToScene(item.line().p1()))
                p2 = rot_pt(item.mapToScene(item.line().p2()))
                item.setPos(QPointF(0, 0))
                item.setLine(QLineF(p1, p2))
            elif isinstance(item, (CustomRectItem, CustomEllipseItem, SpotlightItem)):
                tl = rot_pt(item.mapToScene(item.rect().topLeft()))
                br = rot_pt(item.mapToScene(item.rect().bottomRight()))
                item.setPos(QPointF(0, 0))
                item.setRect(QRectF(tl, br).normalized())
            elif isinstance(item, CalloutItem):
                tl = rot_pt(item.mapToScene(item.box_rect().topLeft()))
                br = rot_pt(item.mapToScene(item.box_rect().bottomRight()))
                tp = rot_pt(item.mapToScene(item.tip_point()))
                item.setPos(QPointF(0, 0))
                item.setBoxRect(QRectF(tl, br).normalized())
                item.setTipPoint(tp)
            elif isinstance(item, CustomPolygonItem):
                new_pts = [rot_pt(item.mapToScene(pt)) for pt in item.polygon()]
                item.setPos(QPointF(0, 0))
                item.setPolygon(QPolygonF(new_pts))
            elif isinstance(item, CustomPathItem):
                scene_path = item.path().translated(item.pos())
                item.setPos(QPointF(0, 0))
                item.setPath(t_scene.map(scene_path))
            elif isinstance(item, CustomPixmapItem):
                tl = rot_pt(item.mapToScene(item.rect().topLeft()))
                br = rot_pt(item.mapToScene(item.rect().bottomRight()))
                nr = QRectF(tl, br).normalized()
                item.original_pixmap = item.original_pixmap.transformed(
                    t_img, Qt.TransformationMode.SmoothTransformation
                )
                item.setPos(nr.topLeft())
                item.setRect(QRectF(0, 0, nr.width(), nr.height()))
            elif isinstance(item, (CustomTextItem, NumberStampItem)):
                center = item.sceneBoundingRect().center()
                new_center = rot_pt(center)
                delta = new_center - center
                item.moveBy(delta.x(), delta.y())

        self.scene.bg_item.setPixmap(new_bg)
        self.scene.setSceneRect(QRectF(new_bg.rect()))
        if not self.scene.original_image_rect.isEmpty():
            r = self.scene.original_image_rect
            self.scene.original_image_rect = QRectF(rot_pt(r.topLeft()), rot_pt(r.bottomRight())).normalized()

        self.scene.update_margin_handles()
        self.scene.has_unsaved_changes = True
        self.scene.save_state()
        self.fit_to_view()
        self.show_toast(f"キャンバスを {angle_deg}° 回転しました", 1800)

    def _on_crop_selection_changed(self, has_valid):
        if has_valid and self.scene.current_tool == "crop":
            self.crop_bar.reposition()
            self.crop_bar.show()
            self.crop_bar.raise_()
        else:
            self.crop_bar.hide()

    def confirm_crop(self):
        if self.scene.crop_rect is not None and self.scene.crop_rect.width() >= 10 and self.scene.crop_rect.height() >= 10:
            self.apply_crop(QRectF(self.scene.crop_rect))

    def cancel_crop(self):
        self.scene.clear_crop_selection()
        self.crop_bar.hide()
        self.set_tool("select")

    def apply_crop(self, crop_rect):
        """指定範囲で背景画像と注釈を切り抜く（Undo完全対応）"""
        if self.scene.bg_item is None:
            return
        try:
            sr = self.scene.sceneRect()
            clamped = crop_rect.intersected(sr)
            x = int(round(clamped.left() - sr.left()))
            y = int(round(clamped.top() - sr.top()))
            w = max(10, int(round(clamped.width())))
            h = max(10, int(round(clamped.height())))

            bg = self.scene.bg_item.pixmap()
            x = max(0, min(bg.width() - 1, x))
            y = max(0, min(bg.height() - 1, y))
            w = min(bg.width() - x, w)
            h = min(bg.height() - y, h)
            if w < 10 or h < 10:
                return

            cropped_bg = bg.copy(x, y, w, h)
            for item in self.scene.annotation_items():
                item.moveBy(float(-x), float(-y))

            self.scene.bg_item.setPixmap(cropped_bg)
            self.scene.setSceneRect(QRectF(cropped_bg.rect()))
            self.scene.original_image_rect = QRectF(cropped_bg.rect())
            self.scene.clear_crop_selection()
            self.crop_bar.hide()
            self.scene.has_unsaved_changes = True
            self.scene.save_state()
            self.set_tool("select")
            self.fit_to_view()
            self.show_toast(f"切り抜きました ({w} × {h} px)")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"切り抜き処理中にエラーが発生しました。\n{e}")

    def start_screen_capture(self, insert_as_annotation=False):
        """ウィンドウを一時的に隠してデスクトップ画面の任意範囲を撮影する"""
        if not insert_as_annotation and not self.check_unsaved_changes():
            return
        if insert_as_annotation and self.scene.bg_item is None:
            insert_as_annotation = False

        self._capture_insert_mode = insert_as_annotation
        self._capture_was_maximized = self.isMaximized()
        self.hide()
        QApplication.processEvents()
        QTimer.singleShot(280, self._launch_capture_overlay)

    def _launch_capture_overlay(self):
        try:
            screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
            if screen is None:
                self._restore_after_capture()
                QMessageBox.warning(self, "エラー", "画面の取得に失敗しました。")
                return
            full_pixmap = screen.grabWindow(0)
            if full_pixmap.isNull():
                self._restore_after_capture()
                QMessageBox.warning(self, "エラー", "スクリーンショットの取得に失敗しました。")
                return
            self._capture_overlay = ScreenCaptureOverlay(full_pixmap, screen.geometry())
            self._capture_overlay.captured.connect(self._on_capture_finished)
            self._capture_overlay.show()
            self._capture_overlay.raise_()
            self._capture_overlay.activateWindow()
        except Exception as e:
            self._restore_after_capture()
            QMessageBox.critical(self, "エラー", f"画面撮影の開始に失敗しました。\n{e}")

    def _restore_after_capture(self):
        if self._capture_was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def _on_capture_finished(self, pixmap):
        self._capture_overlay = None
        self._restore_after_capture()
        if pixmap is None or pixmap.isNull():
            return
        if self._capture_insert_mode and self.scene.bg_item is not None:
            self._insert_pixmap_annotation(pixmap)
            self.show_toast("撮影した画像を注釈として挿入しました")
        else:
            self._load_pixmap_as_new_canvas(pixmap, "screenshot")
            self.show_toast(f"画面を撮影しました ({pixmap.width()} × {pixmap.height()} px)")

    def apply_margin(self, top, bottom, left, right, color):
        """余白を作成・削減して背景画像に適用し、既存の注釈をシフトして位置を補正する"""
        if self.scene.bg_item is None:
            return
        try:
            current_bg_pixmap = self.scene.bg_item.pixmap()
            orig_w = current_bg_pixmap.width()
            orig_h = current_bg_pixmap.height()

            new_w = max(10, orig_w + left + right)
            new_h = max(10, orig_h + top + bottom)

            new_pixmap = QPixmap(new_w, new_h)
            new_pixmap.fill(color)

            src_x = -left if left < 0 else 0
            src_y = -top if top < 0 else 0
            src_w = max(1, orig_w - (-left if left < 0 else 0) - (-right if right < 0 else 0))
            src_h = max(1, orig_h - (-top if top < 0 else 0) - (-bottom if bottom < 0 else 0))

            dest_x = left if left >= 0 else 0
            dest_y = top if top >= 0 else 0

            painter = QPainter(new_pixmap)
            painter.drawPixmap(dest_x, dest_y, current_bg_pixmap, src_x, src_y, src_w, src_h)
            painter.end()

            for item in self.scene.annotation_items():
                item.moveBy(float(left), float(top))

            self.scene.bg_item.setPixmap(new_pixmap)
            self.scene.setSceneRect(QRectF(new_pixmap.rect()))

            if not self.scene.original_image_rect.isEmpty():
                self.scene.original_image_rect.translate(float(left), float(top))

            self.scene.update_margin_handles()
            self.scene.has_unsaved_changes = True
            self.scene.save_state()
            self.fit_to_view()

        except Exception as e:
            QMessageBox.critical(self, "エラー", f"余白追加・削減の実行中にエラーが発生しました。\n{e}")

    def _render_scene_to_image(self, scene, bg_fill_color):
        """指定シーンをハンドル・選択枠・グリッドなしで高画質にQImageへ書き出す"""
        rect = scene.sceneRect()
        w = max(1, int(round(rect.width())))
        h = max(1, int(round(rect.height())))

        prev_selected = list(scene.selectedItems())
        scene.clearSelection()
        scene.set_margin_handles_visible(False)
        scene._is_exporting = True

        image = QImage(w, h, QImage.Format.Format_ARGB32)
        image.fill(bg_fill_color)
        painter = QPainter(image)
        painter.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
            | QPainter.RenderHint.TextAntialiasing
        )
        scene.render(painter, QRectF(0, 0, w, h), rect)
        painter.end()

        scene._is_exporting = False
        scene.set_margin_handles_visible(True)
        for it in prev_selected:
            if it.scene() is scene:
                it.setSelected(True)
        scene.invalidate_handles()
        return image

    def _render_state_to_image(self, state, bg_fill_color):
        """退避されたPDFページ状態をオフスクリーンシーンで高画質にQImageへ書き出す"""
        temp_scene = AnnotationScene()
        temp_scene.restore_scene_state(state)
        return self._render_scene_to_image(temp_scene, bg_fill_color)

    def copy_canvas_to_clipboard(self):
        """注釈済みの完成画像をそのままクリップボードにコピーする"""
        rect = self.scene.sceneRect()
        if rect.isEmpty() or rect.width() <= 0 or rect.height() <= 0:
            QMessageBox.warning(self, "エラー", "コピーする内容がありません。")
            return
        self._commit_pending_property_state()
        image = self._render_scene_to_image(self.scene, Qt.GlobalColor.white)
        clipboard = QGuiApplication.clipboard()
        if clipboard is not None:
            clipboard.setImage(image)
            self._clipboard_source = "system"
            self.show_toast("完成画像をクリップボードにコピーしました")

    def save_file(self):
        """開いたファイル形式と同じ形式で上書き保存（パスがない場合は新規画像保存へ）"""
        if not self.current_file_path:
            return self.save_file_as()
        self.perform_actual_save(self.current_file_path)

    def save_file_as(self):
        """名前を付けて保存（エクスポート専用、デフォルトは.jpg）"""
        default_ext = ".jpg"
        initial_name = f"{self.current_filename}_After{default_ext}" if self.current_filename else f"untitled{default_ext}"
        initial_path = os.path.join(self.current_dir, initial_name) if self.current_dir else initial_name

        filter_str = "JPEG Image (*.jpg);;PNG Image (*.png);;PDF Document (*.pdf)"
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "名前を付けて保存", initial_path, filter_str
        )
        if not file_path:
            return

        if not os.path.splitext(file_path)[1]:
            if "*.png" in selected_filter:
                file_path += ".png"
            elif "*.pdf" in selected_filter:
                file_path += ".pdf"
            else:
                file_path += ".jpg"

        self.perform_actual_save(file_path)

    def save_project(self):
        """プロジェクト（.hwi）を上書き保存"""
        if self.current_file_path and self.current_ext == ".hwi":
            self.perform_actual_save(self.current_file_path)
        else:
            self.save_project_as()

    def save_project_as(self):
        """名前を付けてプロジェクト（.hwi）を保存"""
        default_ext = ".hwi"
        initial_name = f"{self.current_filename}{default_ext}" if self.current_filename else f"untitled{default_ext}"
        initial_path = os.path.join(self.current_dir, initial_name) if self.current_dir else initial_name

        filter_str = "HandwrittenImage Projects (*.hwi)"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "プロジェクトを保存", initial_path, filter_str
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".hwi"):
            file_path += ".hwi"

        self.perform_actual_save(file_path)

    def _save_pdf_file(self, file_path):
        """オンメモリ処理と全ページ維持に対応した安全なPDF保存"""
        out_doc = pymupdf.open()
        try:
            if self.current_pdf_doc is not None and len(self.current_pdf_doc) > 0:
                self._stash_current_pdf_page_state()
                total_pages = len(self.current_pdf_doc)

                for i in range(total_pages):
                    if i in self.pdf_modified_pages:
                        if i == self.current_pdf_page:
                            img = self._render_scene_to_image(self.scene, Qt.GlobalColor.white)
                        else:
                            img = self._render_state_to_image(self.pdf_page_states[i], Qt.GlobalColor.white)
                        img_bytes = qimage_to_bytes(img, "JPEG", 95)

                        orig_page = self.current_pdf_doc.load_page(i)
                        orig_rect = orig_page.rect
                        # 余白変更による縦横比変化があれば反映
                        scale_pt = orig_rect.width / max(1.0, float(img.width()))
                        page_w = orig_rect.width
                        page_h = float(img.height()) * scale_pt
                        new_page = out_doc.new_page(width=page_w, height=page_h)
                        new_page.insert_image(new_page.rect, stream=img_bytes)
                    else:
                        out_doc.insert_pdf(self.current_pdf_doc, from_page=i, to_page=i)
            else:
                img = self._render_scene_to_image(self.scene, Qt.GlobalColor.white)
                img_bytes = qimage_to_bytes(img, "JPEG", 95)
                new_page = out_doc.new_page(width=float(img.width()), height=float(img.height()))
                new_page.insert_image(new_page.rect, stream=img_bytes)

            # 現在開いているPDFと同一パスへの上書き時は一時ファイル経由で安全置換
            is_same_open_pdf = (
                self.current_pdf_doc is not None
                and self.current_file_path
                and os.path.normcase(os.path.abspath(file_path)) == os.path.normcase(os.path.abspath(self.current_file_path))
            )

            if is_same_open_pdf:
                target_dir = os.path.dirname(os.path.abspath(file_path))
                fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=target_dir)
                os.close(fd)
                try:
                    out_doc.save(tmp_path, deflate=True)
                    out_doc.close()
                    out_doc = None

                    keep_page = self.current_pdf_page
                    self.current_pdf_doc.close()
                    self.current_pdf_doc = None
                    os.replace(tmp_path, file_path)
                    self.current_pdf_doc = pymupdf.open(file_path)
                    self.current_pdf_page = min(keep_page, len(self.current_pdf_doc) - 1)
                except Exception:
                    if os.path.exists(tmp_path):
                        try:
                            os.remove(tmp_path)
                        except OSError:
                            pass
                    if self.current_pdf_doc is None and os.path.exists(file_path):
                        self.current_pdf_doc = pymupdf.open(file_path)
                    raise
            else:
                out_doc.save(file_path, deflate=True)
                out_doc.close()
                out_doc = None

                # 別名PDF保存した場合は新しいPDFを開き直して整合性を維持
                keep_page = self.current_pdf_page if self.current_pdf_doc is not None else 0
                self._close_current_pdf()
                self.current_pdf_doc = pymupdf.open(file_path)
                self.current_pdf_page = min(keep_page, len(self.current_pdf_doc) - 1)
        finally:
            if out_doc is not None:
                out_doc.close()

        self.pdf_page_states.clear()
        self.pdf_modified_pages.clear()
        self.scene.mark_as_saved()
        self.current_file_path = file_path
        self.current_dir = os.path.dirname(file_path)
        self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
        self.current_ext = ".pdf"
        self._add_recent_file(file_path)
        self.update_ui_state()
        self.show_toast("PDFとして保存しました")

    def perform_actual_save(self, file_path):
        """指定されたパスに実際に保存処理を行う"""
        self._commit_pending_property_state()
        save_ext = os.path.splitext(file_path)[1].lower()
        rect = self.scene.sceneRect()
        if rect.isEmpty() or rect.width() <= 0 or rect.height() <= 0:
            QMessageBox.warning(self, "エラー", "保存する内容がありません（画面サイズが無効です）。")
            return

        try:
            if self.scene.pending_text_item is not None:
                self.scene.removeItem(self.scene.pending_text_item)
                self.scene.pending_text_item = None
                self.set_tool("select")

            if save_ext == ".hwi":
                other_modified = self.pdf_modified_pages - {self.current_pdf_page}
                if self.current_pdf_doc is not None and other_modified:
                    reply = QMessageBox.question(
                        self,
                        "確認",
                        "現在表示中のページのみプロジェクト(.hwi)として保存します。\n"
                        "PDFの他ページへの未保存の変更は破棄されますが、続行しますか？\n"
                        "（全ページを保存する場合はPDF形式で保存してください）",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if reply != QMessageBox.StandardButton.Yes:
                        return
                project_data = serialize_project(self.scene)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(project_data, f, ensure_ascii=False, separators=(",", ":"))
                self._close_current_pdf()
                self.scene.mark_as_saved()
                self.current_file_path = file_path
                self.current_dir = os.path.dirname(file_path)
                self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                self.current_ext = ".hwi"
                self._add_recent_file(file_path)
                self.update_ui_state()
                self.show_toast("プロジェクトファイル (.hwi) として保存しました")
                return

            if save_ext == ".pdf":
                self._save_pdf_file(file_path)
                return

            # 画像保存（JPEGは白背景＋高品質95で透過黒化を防止、PNGは透過維持）
            is_jpeg = save_ext in (".jpg", ".jpeg")
            bg_fill = Qt.GlobalColor.white if is_jpeg else Qt.GlobalColor.transparent
            image = self._render_scene_to_image(self.scene, bg_fill)

            saved = image.save(file_path, "JPEG", 95) if is_jpeg else image.save(file_path)
            if saved:
                # 複数ページPDFを編集中に単ページ画像へエクスポートした場合はPDF状態を壊さない
                if self.current_pdf_doc is None:
                    self.scene.mark_as_saved()
                    self.current_file_path = file_path
                    self.current_dir = os.path.dirname(file_path)
                    self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                    self.current_ext = save_ext
                    self._add_recent_file(file_path)
                self.update_ui_state()
                self.show_toast(f"{save_ext.upper()} として保存しました")
            else:
                QMessageBox.warning(self, "エラー", "保存に失敗しました。")

        except Exception as e:
            QMessageBox.critical(self, "致命的なエラー", f"保存処理中にエラーが発生しました。\n{e}")

    def show_toast(self, text, duration_ms=2500):
        """操作をブロックせずに完了メッセージを表示する"""
        self.toast.show_message(text, duration_ms)
        self.statusBar().showMessage(text, duration_ms)

    def closeEvent(self, event):
        if self.check_unsaved_changes():
            self._close_current_pdf()
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_light_theme(app)
    window = AdvancedAnnotationApp()
    window.showMaximized()
    sys.exit(app.exec())

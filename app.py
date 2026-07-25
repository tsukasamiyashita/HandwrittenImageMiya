import sys
import os
import math
import json
import fitz # PyMuPDF
import tempfile # 一時ファイルを安全に処理するため
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QToolBar, QFileDialog, QInputDialog, QColorDialog,
    QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem,
    QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsPathItem,
    QGraphicsItem, QMessageBox, QLabel, QMenu, QComboBox,
    QWidget, QSizePolicy, QDialog, QVBoxLayout, QTextEdit, QPushButton,
    QHBoxLayout
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QPolygonF, QFont, QAction, QTransform,
    QPainterPath, QPainterPathStroker, QImageReader, QBrush, QPalette, QIcon
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF, QTimer, QBuffer, QByteArray, QIODevice

def resource_path(relative_path):
    """実行時（exe）でも通常時（.pyw）でも正しいファイルパスを取得する"""
    try:
        # PyInstallerで展開された時の一時フォルダパス
        base_path = sys._MEIPASS
    except Exception:
        # 通常のPythonスクリプトとして実行した時のパス
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class CustomGraphicsView(QGraphicsView):
    """拡大縮小、横スクロールのジェスチャに対応したカスタムQGraphicsView"""
    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setMouseTracking(True) # マウス追従プレビューのために必要

    def wheelEvent(self, event):
        modifiers = event.modifiers()
        
        # Ctrl + 上下スクロール = 拡大・縮小
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.25 if angle > 0 else 0.8
            self.scale(factor, factor)
            event.accept()
            
        # Shift + 上下スクロール = 横スクロール
        elif modifiers & Qt.KeyboardModifier.ShiftModifier:
            angle = event.angleDelta().y()
            h_bar = self.horizontalScrollBar()
            if h_bar:
                # スクロールバーの位置を調節
                h_bar.setValue(h_bar.value() - angle)
            event.accept()
            
        else:
            # 通常のスクロール動作（上下スクロール）
            super().wheelEvent(event)


class CustomLineItem(QGraphicsLineItem):
    """線を描画し、当たり判定（ドラッグ範囲）を広げたカスタムアイテム"""
    def __init__(self, line, pen):
        super().__init__(line)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def shape(self):
        path = QPainterPath()
        path.moveTo(self.line().p1())
        path.lineTo(self.line().p2())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 30.0))
        return stroker.createStroke(path)

class ArrowItem(CustomLineItem):
    """矢印を描画するカスタムアイテム（くの字形状）"""
    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        line = self.line()
        if line.length() == 0:
            return

        angle = math.atan2(-line.dy(), line.dx())
        arrow_size = max(10.0, self.pen().widthF() * 3.5)
        
        p1 = line.p2() - QPointF(math.sin(angle + math.pi / 3) * arrow_size,
                                 math.cos(angle + math.pi / 3) * arrow_size)
        p2 = line.p2() - QPointF(math.sin(angle + math.pi - math.pi / 3) * arrow_size,
                                 math.cos(angle + math.pi - math.pi / 3) * arrow_size)

        painter.setPen(self.pen())
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPolyline(QPolygonF([p1, line.p2(), p2]))


class CustomPathItem(QGraphicsPathItem):
    """フリーハンドを描画し、当たり判定を広げたカスタムアイテム"""
    def __init__(self, path, pen):
        super().__init__(path)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def shape(self):
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 30.0))
        return stroker.createStroke(self.path())

class CustomRectItem(QGraphicsRectItem):
    """四角を描画し、当たり判定を広げたカスタムアイテム"""
    def __init__(self, rect, pen):
        super().__init__(rect)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 30.0))
        return stroker.createStroke(path)

class CustomEllipseItem(QGraphicsEllipseItem):
    """楕円/丸を描画し、当たり判定を広げたカスタムアイテム"""
    def __init__(self, rect, pen):
        super().__init__(rect)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def shape(self):
        path = QPainterPath()
        path.addEllipse(self.rect())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 30.0))
        return stroker.createStroke(path)

class CustomPolygonItem(QGraphicsPolygonItem):
    """多角形（三角）を描画し、当たり判定を広げたカスタムアイテム"""
    def __init__(self, polygon, pen):
        super().__init__(polygon)
        self.setPen(pen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def shape(self):
        path = QPainterPath()
        path.addPolygon(self.polygon())
        stroker = QPainterPathStroker()
        stroker.setWidth(max(self.pen().widthF(), 30.0))
        return stroker.createStroke(path)

class CustomTextItem(QGraphicsTextItem):
    """背景色や枠線を設定できるカスタムテキストアイテム"""
    def __init__(self, text):
        super().__init__(text)
        self._bg_brush = QBrush(Qt.BrushStyle.NoBrush)
        self._border_pen = QPen(Qt.PenStyle.NoPen)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def brush(self): 
        return self._bg_brush
        
    def setBrush(self, brush):
        self._bg_brush = brush
        self.update()

    def pen(self): 
        return self._border_pen
        
    def setPen(self, pen):
        self._border_pen = pen
        self.update()

    def paint(self, painter, option, widget):
        # 背景と枠線が設定されていれば描画
        if self._bg_brush.style() != Qt.BrushStyle.NoBrush or self._border_pen.style() != Qt.PenStyle.NoPen:
            painter.setBrush(self._bg_brush)
            painter.setPen(self._border_pen)
            painter.drawRect(self.boundingRect())
        super().paint(painter, option, widget)


class CustomPixmapItem(QGraphicsItem):
    """注釈として挿入された画像アイテム"""
    def __init__(self, pixmap, rect, parent=None):
        super().__init__(parent)
        self.original_pixmap = pixmap
        self._rect = rect
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

    def boundingRect(self):
        return self._rect

    def setRect(self, rect):
        self.prepareGeometryChange()
        self._rect = rect
        self.update()

    def rect(self):
        return self._rect

    def paint(self, painter, option, widget=None):
        painter.drawPixmap(self._rect, self.original_pixmap, QRectF(self.original_pixmap.rect()))

    def shape(self):
        """画像の内側でも判定できるように矩形全体をパスとする"""
        path = QPainterPath()
        path.addRect(self._rect)
        return path


class MarginHandleItem(QGraphicsRectItem):
    """余白をドラッグ操作で直観的に追加・削減するための専用ハンドル"""
    def __init__(self, side, rect, parent_scene):
        super().__init__(rect)
        self.side = side # 'top', 'bottom', 'left', 'right'
        self.parent_scene = parent_scene
        self.setAcceptHoverEvents(True)
        self.setBrush(QBrush(QColor(0, 120, 255, 120))) # 半透明な薄いブルー
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setZValue(999999) # 常に最前面
        self.press_pos = None
        self.orig_rect = None
        self.preview_rect = None

    def hoverEnterEvent(self, event):
        if self.side in ['top', 'bottom']:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        self.setBrush(QBrush(QColor(0, 120, 255, 200))) # ホバー時に強調
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setBrush(QBrush(QColor(0, 120, 255, 120)))
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_pos = event.scenePos()
            self.orig_rect = self.parent_scene.sceneRect()
            # プレビュー用の破線枠を作成
            self.preview_rect = QGraphicsRectItem(self.orig_rect)
            self.preview_rect.setPen(QPen(QColor(0, 120, 255), 2, Qt.PenStyle.DashLine))
            self.preview_rect.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            self.preview_rect.setZValue(999998)
            self.parent_scene.addItem(self.preview_rect)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_pos and self.preview_rect:
            delta = event.scenePos() - self.press_pos
            new_rect = QRectF(self.orig_rect)
            min_size = 50.0 # 削りすぎ防止の最小サイズガード（50px）
            
            orig_img_rect = getattr(self.parent_scene, 'original_image_rect', None)
            
            if self.side == 'top':
                new_top = self.orig_rect.top() + delta.y()
                if new_top > self.orig_rect.bottom() - min_size:
                    new_top = self.orig_rect.bottom() - min_size
                if orig_img_rect and new_top > orig_img_rect.top():
                    new_top = orig_img_rect.top()
                new_rect.setTop(new_top)
            elif self.side == 'bottom':
                new_bottom = self.orig_rect.bottom() + delta.y()
                if new_bottom < self.orig_rect.top() + min_size:
                    new_bottom = self.orig_rect.top() + min_size
                if orig_img_rect and new_bottom < orig_img_rect.bottom():
                    new_bottom = orig_img_rect.bottom()
                new_rect.setBottom(new_bottom)
            elif self.side == 'left':
                new_left = self.orig_rect.left() + delta.x()
                if new_left > self.orig_rect.right() - min_size:
                    new_left = self.orig_rect.right() - min_size
                if orig_img_rect and new_left > orig_img_rect.left():
                    new_left = orig_img_rect.left()
                new_rect.setLeft(new_left)
            elif self.side == 'right':
                new_right = self.orig_rect.right() + delta.x()
                if new_right < self.orig_rect.left() + min_size:
                    new_right = self.orig_rect.left() + min_size
                if orig_img_rect and new_right < orig_img_rect.right():
                    new_right = orig_img_rect.right()
                new_rect.setRight(new_right)
                
            self.preview_rect.setRect(new_rect)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.preview_rect:
            final_rect = self.preview_rect.rect()
            self.parent_scene.removeItem(self.preview_rect)
            self.preview_rect = None
            self.press_pos = None
            
            top_margin = int(self.orig_rect.top() - final_rect.top())
            bottom_margin = int(final_rect.bottom() - self.orig_rect.bottom())
            left_margin = int(self.orig_rect.left() - final_rect.left())
            right_margin = int(final_rect.right() - self.orig_rect.right())
            
            if top_margin != 0 or bottom_margin != 0 or left_margin != 0 or right_margin != 0:
                main_win = self.parent_scene.parent()
                if hasattr(main_win, 'apply_margin'):
                    color = self.parent_scene.current_brush_color if self.parent_scene.use_fill else QColor(Qt.GlobalColor.white)
                    main_win.apply_margin(top_margin, bottom_margin, left_margin, right_margin, color)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class AnnotationScene(QGraphicsScene):
    """画像と注釈を管理するシーン"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tool = "select"
        self.current_line_type = "line"
        self.current_shape_type = "rect"
        
        # 色管理（ペン・文字・ブラシ）
        self.current_pen_color = QColor(Qt.GlobalColor.red)
        self.current_text_color = QColor(Qt.GlobalColor.red)
        self.current_brush_color = QColor(Qt.GlobalColor.white)
        self.use_fill = False
        
        # 図形線太さと文字サイズを明確に分離
        self.pen_width = 5.0          # 図形/線の太さ
        self.current_font_size = 24.0 # 文字のフォントサイズ (pt)
        
        self.start_point = None
        self.temp_item = None
        self.bg_item = None
        self.pending_text_item = None

        self.resizing_item = None
        self.resize_mode = None
        self.initial_scale = 1.0
        self.initial_dist_x = 1.0
        self.initial_dist_y = 1.0
        self.shape_anchor = None
        self.initial_path = None
        self.initial_rect = None
        self.start_scene_rect = None
        
        self.current_path = None
        self.copied_data = None
        
        self.has_unsaved_changes = False
        self.margin_handles = []
        self.original_image_rect = QRectF()
        
        self.undo_stack = []
        self.redo_stack = []
        self.was_modified = False

    def get_next_z_value(self):
        """シーン内で最も前面に配置するためのZ値を取得"""
        max_z = 0.0
        for item in self.items():
            if item != self.bg_item and item.zValue() > max_z and not isinstance(item, MarginHandleItem):
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


    def get_scene_state(self):
        """現在のシーンのアイテム状態をシリアライズして取得"""
        state = []
        for item in self.items():
            if item == self.bg_item or item.zValue() < 0 or item == self.pending_text_item or isinstance(item, MarginHandleItem):
                continue
            if isinstance(item, ArrowItem):
                state.append({'type': 'arrow', 'line': item.line(), 'pen': QPen(item.pen()), 'pos': item.pos()})
            elif isinstance(item, CustomLineItem):
                state.append({'type': 'line', 'line': item.line(), 'pen': QPen(item.pen()), 'pos': item.pos()})
            elif isinstance(item, CustomRectItem):
                state.append({'type': 'rect', 'rect': item.rect(), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush()), 'pos': item.pos()})
            elif isinstance(item, CustomEllipseItem):
                state.append({'type': 'ellipse', 'rect': item.rect(), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush()), 'pos': item.pos()})
            elif isinstance(item, CustomPolygonItem):
                state.append({'type': 'polygon', 'polygon': item.polygon(), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush()), 'pos': item.pos()})
            elif isinstance(item, CustomPathItem):
                state.append({'type': 'path', 'path': QPainterPath(item.path()), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush()), 'pos': item.pos()})
            elif isinstance(item, CustomTextItem):
                state.append({
                    'type': 'text', 'text': item.toPlainText(),
                    'font': QFont(item.font()), 'color': QColor(item.defaultTextColor()),
                    'pen': QPen(item.pen()), 'brush': QBrush(item.brush()),
                    'scale': item.scale(), 'pos': item.pos()
                })
            elif isinstance(item, CustomPixmapItem):
                state.append({'type': 'pixmap', 'pixmap': item.original_pixmap, 'rect': item.rect(), 'pos': item.pos()})
        
        bg_pixmap = self.bg_item.pixmap() if self.bg_item else QPixmap()
        bg_rect = self.sceneRect()
        original_image_rect = getattr(self, 'original_image_rect', QRectF())
        
        return {
            'items': list(reversed(state)),
            'bg_pixmap': bg_pixmap,
            'bg_rect': bg_rect,
            'original_image_rect': original_image_rect
        }

    def restore_scene_state(self, state):
        """保存された状態からシーンを復元"""
        if isinstance(state, dict):
            items_data = state['items']
            bg_pixmap = state.get('bg_pixmap')
            bg_rect = state.get('bg_rect')
            original_image_rect = state.get('original_image_rect', QRectF())
        else:
            items_data = state
            bg_pixmap = None
            bg_rect = None
            original_image_rect = QRectF()

        for item in self.items():
            if item != self.bg_item and not isinstance(item, MarginHandleItem):
                self.removeItem(item)
        
        self.clearSelection()

        if bg_pixmap and self.bg_item:
            self.bg_item.setPixmap(bg_pixmap)
        if bg_rect:
            self.setSceneRect(bg_rect)
            
        self.original_image_rect = original_image_rect

        for i, data in enumerate(items_data):
            item_type = data['type']
            new_item = None
            if item_type == 'arrow':
                new_item = ArrowItem(data['line'], data['pen'])
            elif item_type == 'line':
                new_item = CustomLineItem(data['line'], data['pen'])
            elif item_type == 'rect':
                new_item = CustomRectItem(data['rect'], data['pen'])
                new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))
            elif item_type == 'ellipse':
                new_item = CustomEllipseItem(data['rect'], data['pen'])
                new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))
            elif item_type == 'polygon':
                new_item = CustomPolygonItem(data['polygon'], data['pen'])
                new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))
            elif item_type == 'path':
                new_item = CustomPathItem(data['path'], data['pen'])
                new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))
            elif item_type == 'text':
                new_item = CustomTextItem(data['text'])
                new_item.setFont(data['font'])
                new_item.setDefaultTextColor(data['color'])
                new_item.setPen(data.get('pen', QPen(Qt.PenStyle.NoPen)))
                new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))
                new_item.setScale(data['scale'])
            elif item_type == 'pixmap':
                new_item = CustomPixmapItem(data['pixmap'], data['rect'])
            
            if new_item:
                new_item.setZValue(float(i + 1))
                new_item.setPos(data['pos'])
                self.addItem(new_item)

        self.update_margin_handles()

    def save_state(self):
        """操作のたびに状態をスタックに保存"""
        state = self.get_scene_state()
        self.undo_stack.append(state)
        self.redo_stack.clear()
        if len(self.undo_stack) > 30:
            self.undo_stack.pop(0)

    def undo(self):
        """戻る"""
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self.restore_scene_state(self.undo_stack[-1])
            self.has_unsaved_changes = True

    def redo(self):
        """進む"""
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            self.restore_scene_state(state)
            self.has_unsaved_changes = True

    def set_background(self, pixmap):
        self.clear()
        self.margin_handles.clear()
        self.bg_item = self.addPixmap(pixmap)
        self.bg_item.setZValue(-1.0) 
        self.bg_item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable ^ QGraphicsItem.GraphicsItemFlag.ItemIsFocusable) 
        self.setSceneRect(QRectF(pixmap.rect()))
        
        self.original_image_rect = QRectF(0, 0, pixmap.width(), pixmap.height())
        
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.save_state()
        self.has_unsaved_changes = False

    def update_margin_handles(self):
        """現在のツールモードに応じて余白ドラッグハンドルを同期配置する"""
        self.clear_margin_handles()
        if self.current_tool == "margin" and self.bg_item:
            r = self.sceneRect()
            thickness = 24.0
            half = thickness / 2.0
            
            top_h = MarginHandleItem('top', QRectF(r.left(), r.top() - half, r.width(), thickness), self)
            bot_h = MarginHandleItem('bottom', QRectF(r.left(), r.bottom() - half, r.width(), thickness), self)
            left_h = MarginHandleItem('left', QRectF(r.left() - half, r.top(), thickness, r.height()), self)
            right_h = MarginHandleItem('right', QRectF(r.right() - half, r.top(), thickness, r.height()), self)
            
            for h in [top_h, bot_h, left_h, right_h]:
                self.addItem(h)
                self.margin_handles.append(h)

    def clear_margin_handles(self):
        """一時的な余白ドラッグハンドルをシーンから消去する"""
        for h in self.margin_handles:
            self.removeItem(h)
        self.margin_handles.clear()


    def drawForeground(self, painter, rect):
        """選択アイテムにサイズ変更用のハンドルを描画"""
        super().drawForeground(painter, rect)
        if self.current_tool != "select":
            return

        painter.setBrush(QColor(0, 120, 255))
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        handle_size = 12

        for item in self.selectedItems():
            if item == self.bg_item or item == self.pending_text_item or isinstance(item, MarginHandleItem):
                continue

            if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                br = item.mapToScene(item.rect().bottomRight())
                painter.drawRect(QRectF(br.x() - handle_size/2, br.y() - handle_size/2, handle_size, handle_size))
            elif isinstance(item, CustomPixmapItem):
                local_rect = item.rect()
                handles = [
                    local_rect.topLeft(), local_rect.topRight(),
                    local_rect.bottomLeft(), local_rect.bottomRight(),
                    QPointF(local_rect.center().x(), local_rect.top()),
                    QPointF(local_rect.center().x(), local_rect.bottom()),
                    QPointF(local_rect.left(), local_rect.center().y()),
                    QPointF(local_rect.right(), local_rect.center().y())
                ]
                for local_pt in handles:
                    pt = item.mapToScene(local_pt)
                    painter.drawRect(QRectF(pt.x() - handle_size/2, pt.y() - handle_size/2, handle_size, handle_size))
            elif isinstance(item, QGraphicsPolygonItem):
                br = item.mapToScene(item.boundingRect().bottomRight())
                painter.drawRect(QRectF(br.x() - handle_size/2, br.y() - handle_size/2, handle_size, handle_size))
            elif isinstance(item, CustomPathItem):
                br = item.mapToScene(item.boundingRect().bottomRight())
                painter.drawRect(QRectF(br.x() - handle_size/2, br.y() - handle_size/2, handle_size, handle_size))
            elif isinstance(item, QGraphicsLineItem):
                p1 = item.mapToScene(item.line().p1())
                p2 = item.mapToScene(item.line().p2())
                painter.drawRect(QRectF(p1.x() - handle_size/2, p1.y() - handle_size/2, handle_size, handle_size))
                painter.drawRect(QRectF(p2.x() - handle_size/2, p2.y() - handle_size/2, handle_size, handle_size))
            elif isinstance(item, CustomTextItem):
                br = item.mapToScene(item.boundingRect().bottomRight())
                painter.drawRect(QRectF(br.x() - handle_size/2, br.y() - handle_size/2, handle_size, handle_size))

    def mousePressEvent(self, event):
        # プレビュー中のテキスト配置確定/キャンセル
        if self.current_tool == "text" and getattr(self, 'pending_text_item', None):
            if event.button() == Qt.MouseButton.LeftButton:
                self.pending_text_item.setPos(event.scenePos())
                self.pending_text_item = None
                self.has_unsaved_changes = True
                self.save_state()
                if hasattr(self.parent(), 'set_tool'):
                    self.parent().set_tool("select")
                event.accept()
                return
            elif event.button() == Qt.MouseButton.RightButton:
                self.removeItem(self.pending_text_item)
                self.pending_text_item = None
                if hasattr(self.parent(), 'set_tool'):
                    self.parent().set_tool("select")
                event.accept()
                return

        if self.current_tool == "margin":
            super().mousePressEvent(event)
            return

        if self.current_tool == "select":
            if event.button() == Qt.MouseButton.RightButton:
                super().mousePressEvent(event)
                return
            
            pos = event.scenePos()
            self.resizing_item = None
            self.resize_mode = None
            self.was_modified = False

            handle_area = 30
            for item in self.selectedItems():
                if item == self.bg_item:
                    continue
                
                if isinstance(item, CustomPixmapItem):
                    local_rect = item.rect()
                    handles = {
                        "top_left": local_rect.topLeft(),
                        "top_right": local_rect.topRight(),
                        "bottom_left": local_rect.bottomLeft(),
                        "bottom_right": local_rect.bottomRight(),
                        "top": QPointF(local_rect.center().x(), local_rect.top()),
                        "bottom": QPointF(local_rect.center().x(), local_rect.bottom()),
                        "left": QPointF(local_rect.left(), local_rect.center().y()),
                        "right": QPointF(local_rect.right(), local_rect.center().y())
                    }
                    for name, local_pt in handles.items():
                        pt = item.mapToScene(local_pt)
                        if (pos - pt).manhattanLength() < handle_area:
                            self.resizing_item = item
                            self.resize_mode = f"pixmap_{name}"
                            self.start_scene_rect = item.rect().translated(item.pos())
                            event.accept()
                            return
                elif isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                    br = item.mapToScene(item.rect().bottomRight())
                    if (pos - br).manhattanLength() < handle_area:
                        self.resizing_item = item
                        self.resize_mode = "shape_br"
                        self.shape_anchor = item.rect().topLeft()
                        event.accept()
                        return
                elif isinstance(item, QGraphicsPolygonItem):
                    br = item.mapToScene(item.boundingRect().bottomRight())
                    if (pos - br).manhattanLength() < handle_area:
                        self.resizing_item = item
                        self.resize_mode = "shape_br"
                        self.shape_anchor = item.polygon().boundingRect().topLeft()
                        event.accept()
                        return
                elif isinstance(item, CustomPathItem):
                    br = item.mapToScene(item.boundingRect().bottomRight())
                    if (pos - br).manhattanLength() < handle_area:
                        self.resizing_item = item
                        self.resize_mode = "path_br"
                        self.shape_anchor = item.boundingRect().topLeft()
                        self.initial_path = item.path()
                        self.initial_rect = item.boundingRect()
                        event.accept()
                        return
                elif isinstance(item, QGraphicsLineItem):
                    p1 = item.mapToScene(item.line().p1())
                    p2 = item.mapToScene(item.line().p2())
                    if (pos - p1).manhattanLength() < handle_area:
                        self.resizing_item = item
                        self.resize_mode = "line_p1"
                        event.accept()
                        return
                    if (pos - p2).manhattanLength() < handle_area:
                        self.resizing_item = item
                        self.resize_mode = "line_p2"
                        event.accept()
                        return
                elif isinstance(item, CustomTextItem):
                    br = item.mapToScene(item.boundingRect().bottomRight())
                    if (pos - br).manhattanLength() < handle_area:
                        self.resizing_item = item
                        self.resize_mode = "text_scale"
                        self.initial_scale = item.scale()
                        self.start_point = pos
                        self.initial_dist_x = max(1.0, pos.x() - item.scenePos().x())
                        self.initial_dist_y = max(1.0, pos.y() - item.scenePos().y())
                        event.accept()
                        return

            super().mousePressEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.start_point = event.scenePos()
            
            pen = QPen(self.current_pen_color)
            pen.setWidthF(self.pen_width)
            pen.setStyle(Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            
            brush = QBrush(self.current_brush_color) if self.use_fill else QBrush(Qt.BrushStyle.NoBrush)

            if self.current_tool == "line":
                if self.current_line_type == "line":
                    self.temp_item = CustomLineItem(QLineF(self.start_point, self.start_point), pen)
                elif self.current_line_type == "arrow":
                    self.temp_item = ArrowItem(QLineF(self.start_point, self.start_point), pen)
                elif self.current_line_type == "freehand":
                    self.current_path = QPainterPath(self.start_point)
                    self.temp_item = CustomPathItem(self.current_path, pen)
                    self.temp_item.setBrush(brush)
                self.temp_item.setZValue(self.get_next_z_value())
                self.addItem(self.temp_item)
            elif self.current_tool == "shape":
                if self.current_shape_type == "rect":
                    self.temp_item = CustomRectItem(QRectF(self.start_point, self.start_point), pen)
                    self.temp_item.setBrush(brush)
                elif self.current_shape_type == "ellipse":
                    self.temp_item = CustomEllipseItem(QRectF(self.start_point, self.start_point), pen)
                    self.temp_item.setBrush(brush)
                elif self.current_shape_type == "triangle":
                    self.temp_item = CustomPolygonItem(QPolygonF([self.start_point, self.start_point, self.start_point]), pen)
                    self.temp_item.setBrush(brush)
                self.temp_item.setZValue(self.get_next_z_value())
                self.addItem(self.temp_item)


    def mouseMoveEvent(self, event):
        if self.current_tool == "text" and getattr(self, 'pending_text_item', None):
            self.pending_text_item.setPos(event.scenePos())
            event.accept()
            return

        if self.current_tool == "margin":
            super().mouseMoveEvent(event)
            return

        if self.current_tool == "select":
            if event.buttons() == Qt.MouseButton.NoButton:
                pos = event.scenePos()
                handle_area = 30
                on_handle = False
                cursor_shape = Qt.CursorShape.ArrowCursor

                for item in self.selectedItems():
                    if item == self.bg_item or isinstance(item, MarginHandleItem):
                        continue
                    
                    if isinstance(item, CustomPixmapItem):
                        local_rect = item.rect()
                        handles = {
                            "top_left": (local_rect.topLeft(), Qt.CursorShape.SizeFDiagCursor),
                            "bottom_right": (local_rect.bottomRight(), Qt.CursorShape.SizeFDiagCursor),
                            "top_right": (local_rect.topRight(), Qt.CursorShape.SizeBDiagCursor),
                            "bottom_left": (local_rect.bottomLeft(), Qt.CursorShape.SizeBDiagCursor),
                            "top": (QPointF(local_rect.center().x(), local_rect.top()), Qt.CursorShape.SizeVerCursor),
                            "bottom": (QPointF(local_rect.center().x(), local_rect.bottom()), Qt.CursorShape.SizeVerCursor),
                            "left": (QPointF(local_rect.left(), local_rect.center().y()), Qt.CursorShape.SizeHorCursor),
                            "right": (QPointF(local_rect.right(), local_rect.center().y()), Qt.CursorShape.SizeHorCursor)
                        }
                        for name, (local_pt, cursor) in handles.items():
                            pt = item.mapToScene(local_pt)
                            if (pos - pt).manhattanLength() < handle_area:
                                on_handle = True
                                cursor_shape = cursor
                                break
                        if on_handle:
                            break
                    elif isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                        br = item.mapToScene(item.rect().bottomRight())
                        if (pos - br).manhattanLength() < handle_area:
                            on_handle = True
                            cursor_shape = Qt.CursorShape.SizeFDiagCursor
                            break
                    elif isinstance(item, (QGraphicsPolygonItem, CustomPathItem)):
                        br = item.mapToScene(item.boundingRect().bottomRight())
                        if (pos - br).manhattanLength() < handle_area:
                            on_handle = True
                            cursor_shape = Qt.CursorShape.SizeFDiagCursor
                            break
                    elif isinstance(item, QGraphicsLineItem):
                        p1 = item.mapToScene(item.line().p1())
                        p2 = item.mapToScene(item.line().p2())
                        if (pos - p1).manhattanLength() < handle_area or (pos - p2).manhattanLength() < handle_area:
                            on_handle = True
                            cursor_shape = Qt.CursorShape.CrossCursor
                            break
                    elif isinstance(item, CustomTextItem):
                        br = item.mapToScene(item.boundingRect().bottomRight())
                        if (pos - br).manhattanLength() < handle_area:
                            on_handle = True
                            cursor_shape = Qt.CursorShape.SizeFDiagCursor
                            break

                if not on_handle:
                    transform = self.views()[0].transform() if self.views() else QTransform()
                    item_under_mouse = self.itemAt(pos, transform)
                    if item_under_mouse and item_under_mouse != self.bg_item and not isinstance(item_under_mouse, MarginHandleItem):
                        if item_under_mouse.isSelected():
                            cursor_shape = Qt.CursorShape.SizeAllCursor
                        else:
                            cursor_shape = Qt.CursorShape.PointingHandCursor

                if self.views():
                    self.views()[0].viewport().setCursor(cursor_shape)
                
                super().mouseMoveEvent(event)
                return

            if self.resizing_item:
                pos = event.scenePos()
                item = self.resizing_item
                local_pos = item.mapFromScene(pos)

                if self.resize_mode.startswith("pixmap_"):
                    mode = self.resize_mode.replace("pixmap_", "")
                    start_rect = self.start_scene_rect
                    r = start_rect.width() / max(1.0, start_rect.height())

                    if mode == "bottom_right":
                        anchor = start_rect.topLeft()
                        dx = pos.x() - anchor.x()
                        dy = pos.y() - anchor.y()
                        sign_x = 1 if dx >= 0 else -1
                        sign_y = 1 if dy >= 0 else -1
                        val = max(abs(dx), abs(dy) * r)
                        new_w = sign_x * val
                        new_h = sign_y * val / r
                        new_scene_rect = QRectF(anchor.x(), anchor.y(), new_w, new_h).normalized()
                    elif mode == "top_left":
                        anchor = start_rect.bottomRight()
                        dx = anchor.x() - pos.x()
                        dy = anchor.y() - pos.y()
                        sign_x = 1 if dx >= 0 else -1
                        sign_y = 1 if dy >= 0 else -1
                        val = max(abs(dx), abs(dy) * r)
                        new_w = sign_x * val
                        new_h = sign_y * val / r
                        new_scene_rect = QRectF(anchor.x() - new_w, anchor.y() - new_h, new_w, new_h).normalized()
                    elif mode == "top_right":
                        anchor = start_rect.bottomLeft()
                        dx = pos.x() - anchor.x()
                        dy = pos.y() - anchor.y()
                        sign_x = 1 if dx >= 0 else -1
                        sign_y = 1 if dy >= 0 else -1
                        val = max(abs(dx), abs(dy) * r)
                        new_w = sign_x * val
                        new_h = sign_y * val / r
                        new_scene_rect = QRectF(anchor.x(), anchor.y() - new_h, new_w, new_h).normalized()
                    elif mode == "bottom_left":
                        anchor = start_rect.topRight()
                        dx = anchor.x() - pos.x()
                        dy = anchor.y() - pos.y()
                        sign_x = 1 if dx >= 0 else -1
                        sign_y = 1 if dy >= 0 else -1
                        val = max(abs(dx), abs(dy) * r)
                        new_w = sign_x * val
                        new_h = sign_y * val / r
                        new_scene_rect = QRectF(anchor.x() - new_w, anchor.y(), new_w, new_h).normalized()
                    
                    elif mode == "right":
                        new_w = pos.x() - start_rect.left()
                        new_scene_rect = QRectF(start_rect.left(), start_rect.top(), new_w, start_rect.height()).normalized()
                    elif mode == "left":
                        new_w = start_rect.right() - pos.x()
                        new_scene_rect = QRectF(pos.x(), start_rect.top(), new_w, start_rect.height()).normalized()
                    elif mode == "bottom":
                        new_h = pos.y() - start_rect.top()
                        new_scene_rect = QRectF(start_rect.left(), start_rect.top(), start_rect.width(), new_h).normalized()
                    elif mode == "top":
                        new_h = start_rect.bottom() - pos.y()
                        new_scene_rect = QRectF(start_rect.left(), pos.y(), start_rect.width(), new_h).normalized()

                    item.setPos(new_scene_rect.topLeft())
                    item.setRect(QRectF(0, 0, new_scene_rect.width(), new_scene_rect.height()))

                elif self.resize_mode == "shape_br":
                    rect = QRectF(self.shape_anchor, local_pos).normalized()
                    if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                        item.setRect(rect)
                    elif isinstance(item, QGraphicsPolygonItem):
                        p1 = QPointF(rect.center().x(), rect.top())
                        p2 = QPointF(rect.left(), rect.bottom())
                        p3 = QPointF(rect.right(), rect.bottom())
                        item.setPolygon(QPolygonF([p1, p2, p3]))
                elif self.resize_mode == "path_br":
                    rect = QRectF(self.shape_anchor, local_pos).normalized()
                    w = max(1.0, self.initial_rect.width())
                    h = max(1.0, self.initial_rect.height())
                    sx = rect.width() / w
                    sy = rect.height() / h
                    
                    t = QTransform()
                    t.translate(self.shape_anchor.x(), self.shape_anchor.y())
                    t.scale(sx, sy)
                    t.translate(-self.shape_anchor.x(), -self.shape_anchor.y())
                    
                    item.setPath(t.map(self.initial_path))
                elif self.resize_mode == "line_p1":
                    line = item.line()
                    line.setP1(local_pos)
                    item.setLine(line)
                elif self.resize_mode == "line_p2":
                    line = item.line()
                    line.setP2(local_pos)
                    item.setLine(line)
                elif self.resize_mode == "text_scale":
                    current_dist_x = pos.x() - item.scenePos().x()
                    current_dist_y = pos.y() - item.scenePos().y()
                    factor = max(current_dist_x / self.initial_dist_x, current_dist_y / self.initial_dist_y)
                    new_scale = max(0.1, self.initial_scale * factor)
                    item.setScale(new_scale)
                
                self.has_unsaved_changes = True
                self.was_modified = True
                self.update() 
                event.accept()
                return
            
            is_moving = False
            if event.buttons() == Qt.MouseButton.LeftButton:
                for item in self.selectedItems():
                    if item != self.bg_item and not isinstance(item, MarginHandleItem):
                        self.has_unsaved_changes = True
                        self.was_modified = True
                        is_moving = True
                        break
            super().mouseMoveEvent(event)
            if is_moving:
                self.update() 
            return

        if self.start_point and self.temp_item:
            end_point = event.scenePos()
            if self.current_tool == "line":
                if self.current_line_type in ["line", "arrow"]:
                    self.temp_item.setLine(QLineF(self.start_point, end_point))
                elif self.current_line_type == "freehand":
                    self.current_path.lineTo(end_point)
                    self.temp_item.setPath(self.current_path)
            elif self.current_tool == "shape":
                rect = QRectF(self.start_point, end_point).normalized()
                if self.current_shape_type in ["rect", "ellipse"]:
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

        if self.current_tool == "select":
            if getattr(self, 'was_modified', False):
                self.save_state()
                self.was_modified = False
            
            if self.resizing_item:
                self.resizing_item = None
                self.resize_mode = None
                self.shape_anchor = None
                self.initial_path = None
                self.initial_rect = None
                self.start_scene_rect = None
                event.accept()
                return
            super().mouseReleaseEvent(event)
            return

        if event.button() == Qt.MouseButton.LeftButton and self.temp_item:
            self.temp_item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
            self.start_point = None
            self.temp_item = None
            self.current_path = None
            self.has_unsaved_changes = True
            self.save_state()

    def delete_selected_items(self):
        """選択されているアイテムを削除する"""
        deleted = False
        for item in self.selectedItems():
            if item != self.bg_item and not isinstance(item, MarginHandleItem):
                self.removeItem(item)
                deleted = True
        if deleted:
            self.has_unsaved_changes = True
            self.save_state()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.delete_selected_items()
            super().keyPressEvent(event)
        else:
            super().keyPressEvent(event)


    def contextMenuEvent(self, event):
        if self.current_tool != "select":
            super().contextMenuEvent(event)
            return

        pos = event.scenePos()
        transform = self.views()[0].transform() if self.views() else QTransform()
        target_item = self.itemAt(pos, transform)
        
        if target_item == self.bg_item or isinstance(target_item, MarginHandleItem):
            target_item = None

        menu = QMenu()
        
        bring_front_action = menu.addAction("⏫ 前面に配置")
        bring_front_action.setEnabled(target_item is not None)
        
        menu.addSeparator()
        
        copy_action = menu.addAction("コピー")
        copy_action.setEnabled(target_item is not None)
        
        paste_action = menu.addAction("貼り付け")
        paste_action.setEnabled(self.copied_data is not None)

        edit_text_action = None
        if isinstance(target_item, CustomTextItem):
            menu.addSeparator()
            edit_text_action = menu.addAction("テキストを編集")

        reset_aspect_action = None
        if isinstance(target_item, CustomPixmapItem):
            menu.addSeparator()
            reset_aspect_action = menu.addAction("🔄 縦横比を元に戻す")

        action = menu.exec(event.screenPos())

        if action == bring_front_action:
            self.bring_to_front(target_item)
        elif action == copy_action:
            self.copy_item(target_item)
        elif action == paste_action:
            self.paste_item(pos)
        elif edit_text_action and action == edit_text_action:
            self.edit_text_item(target_item)
        elif reset_aspect_action and action == reset_aspect_action:
            self.reset_pixmap_aspect(target_item)

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
                self.update()

    def copy_item(self, item):
        if isinstance(item, ArrowItem):
            self.copied_data = {'type': 'arrow', 'line': item.line(), 'pen': QPen(item.pen())}
        elif isinstance(item, CustomLineItem):
            self.copied_data = {'type': 'line', 'line': item.line(), 'pen': QPen(item.pen())}
        elif isinstance(item, CustomRectItem):
            self.copied_data = {'type': 'rect', 'rect': item.rect(), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush())}
        elif isinstance(item, CustomEllipseItem):
            self.copied_data = {'type': 'ellipse', 'rect': item.rect(), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush())}
        elif isinstance(item, CustomPolygonItem):
            self.copied_data = {'type': 'polygon', 'polygon': item.polygon(), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush())}
        elif isinstance(item, CustomPathItem):
            self.copied_data = {'type': 'path', 'path': QPainterPath(item.path()), 'pen': QPen(item.pen()), 'brush': QBrush(item.brush())}
        elif isinstance(item, CustomTextItem):
            self.copied_data = {
                'type': 'text', 'text': item.toPlainText(),
                'font': QFont(item.font()), 'color': QColor(item.defaultTextColor()),
                'pen': QPen(item.pen()), 'brush': QBrush(item.brush()),
                'scale': item.scale()
            }
        elif isinstance(item, CustomPixmapItem):
            self.copied_data = {'type': 'pixmap', 'pixmap': item.original_pixmap, 'rect': item.rect()}
        else:
            self.copied_data = None

    def paste_item(self, pos):
        if not self.copied_data:
            return

        data = self.copied_data
        item_type = data['type']
        self.clearSelection()

        new_item = None
        if item_type in ['line', 'arrow']:
            old_line = data['line']
            dx = old_line.p2().x() - old_line.p1().x()
            dy = old_line.p2().y() - old_line.p1().y()
            new_line = QLineF(pos, QPointF(pos.x() + dx, pos.y() + dy))
            new_pen = QPen(data['pen'])
            new_item = CustomLineItem(new_line, new_pen) if item_type == 'line' else ArrowItem(new_line, new_pen)

        elif item_type in ['rect', 'ellipse']:
            old_rect = data['rect']
            new_rect = QRectF(pos.x(), pos.y(), old_rect.width(), old_rect.height())
            new_pen = QPen(data['pen'])
            new_item = CustomRectItem(new_rect, new_pen) if item_type == 'rect' else CustomEllipseItem(new_rect, new_pen)
            new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))

        elif item_type in ['polygon']:
            old_poly = data['polygon']
            br = old_poly.boundingRect()
            dx_poly = pos.x() - br.left()
            dy_poly = pos.y() - br.top()
            new_poly = old_poly.translated(dx_poly, dy_poly)
            new_pen = QPen(data['pen'])
            new_item = CustomPolygonItem(new_poly, new_pen)
            new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))
            
        elif item_type == 'path':
            old_path = data['path']
            br = old_path.boundingRect()
            dx_path = pos.x() - br.left()
            dy_path = pos.y() - br.top()
            new_path = old_path.translated(dx_path, dy_path)
            new_pen = QPen(data['pen'])
            new_item = CustomPathItem(new_path, new_pen)
            new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))

        elif item_type == 'text':
            new_item = CustomTextItem(data['text'])
            new_item.setFont(data['font'])
            new_item.setDefaultTextColor(data['color'])
            new_item.setPen(data.get('pen', QPen(Qt.PenStyle.NoPen)))
            new_item.setBrush(data.get('brush', QBrush(Qt.BrushStyle.NoBrush)))
            new_item.setPos(pos)
            new_item.setScale(data['scale'])

        elif item_type == 'pixmap':
            old_rect = data['rect']
            new_rect = QRectF(pos.x(), pos.y(), old_rect.width(), old_rect.height())
            new_item = CustomPixmapItem(data['pixmap'], new_rect)

        if new_item:
            new_item.setZValue(self.get_next_z_value())
            self.addItem(new_item)
            new_item.setSelected(True)
            self.has_unsaved_changes = True
            self.save_state()

    def edit_text_item(self, item):
        if isinstance(item, CustomTextItem):
            current_text = item.toPlainText()
            new_text, ok = QInputDialog.getMultiLineText(None, "テキストの編集", "文字を変更してください:", current_text)
            if ok and new_text and new_text != current_text:
                item.setPlainText(new_text)
                self.has_unsaved_changes = True
                self.save_state()


def color_to_hex(color):
    return color.name(QColor.NameFormat.HexArgb)

def hex_to_color(hex_str):
    return QColor(hex_str)

def serialize_pen(pen):
    return {
        'color': color_to_hex(pen.color()),
        'width': pen.widthF(),
        'style': pen.style().value if hasattr(pen.style(), 'value') else int(pen.style()),
        'cap': pen.capStyle().value if hasattr(pen.capStyle(), 'value') else int(pen.capStyle()),
        'join': pen.joinStyle().value if hasattr(pen.joinStyle(), 'value') else int(pen.joinStyle())
    }

def deserialize_pen(data):
    pen = QPen(hex_to_color(data['color']))
    pen.setWidthF(data['width'])
    pen.setStyle(Qt.PenStyle(data['style']))
    pen.setCapStyle(Qt.PenCapStyle(data['cap']))
    pen.setJoinStyle(Qt.PenJoinStyle(data['join']))
    return pen

def serialize_brush(brush):
    return {
        'color': color_to_hex(brush.color()),
        'style': brush.style().value if hasattr(brush.style(), 'value') else int(brush.style())
    }

def deserialize_brush(data):
    brush = QBrush(hex_to_color(data['color']))
    brush.setStyle(Qt.BrushStyle(data['style']))
    return brush

def pixmap_to_base64(pixmap):
    if pixmap.isNull():
        return ""
    byte_array = QByteArray()
    buffer = QBuffer(byte_array)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    return byte_array.toBase64().data().decode('utf-8')

def base64_to_pixmap(base64_str):
    if not base64_str:
        return QPixmap()
    byte_array = QByteArray.fromBase64(base64_str.encode('utf-8'))
    image = QImage.fromData(byte_array, "PNG")
    return QPixmap.fromImage(image)

def serialize_path(path):
    elements = []
    for i in range(path.elementCount()):
        el = path.elementAt(i)
        elements.append({
            'type': el.type.value if hasattr(el.type, 'value') else int(el.type),
            'x': el.x,
            'y': el.y
        })
    return elements

def deserialize_path(elements):
    path = QPainterPath()
    i = 0
    num_elements = len(elements)
    while i < num_elements:
        el = elements[i]
        t = el['type']
        if t == 0:
            path.moveTo(el['x'], el['y'])
            i += 1
        elif t == 1:
            path.lineTo(el['x'], el['y'])
            i += 1
        elif t == 2:
            if i + 2 < num_elements:
                ctrl1 = elements[i]
                ctrl2 = elements[i+1]
                end_pt = elements[i+2]
                path.cubicTo(ctrl1['x'], ctrl1['y'], ctrl2['x'], ctrl2['y'], end_pt['x'], end_pt['y'])
                i += 3
            else:
                path.lineTo(el['x'], el['y'])
                i += 1
        else:
            i += 1
    return path

def serialize_project(scene):
    state = scene.get_scene_state()
    items_data = state['items']
    
    serialized_items = []
    for item in items_data:
        item_type = item['type']
        s_item = {
            'type': item_type,
            'pos': [item['pos'].x(), item['pos'].y()]
        }
        
        if 'pen' in item:
            s_item['pen'] = serialize_pen(item['pen'])
            
        if 'brush' in item:
            s_item['brush'] = serialize_brush(item['brush'])
            
        if item_type in ['line', 'arrow']:
            line = item['line']
            s_item['line'] = [line.p1().x(), line.p1().y(), line.p2().x(), line.p2().y()]
        elif item_type in ['rect', 'ellipse']:
            rect = item['rect']
            s_item['rect'] = [rect.x(), rect.y(), rect.width(), rect.height()]
        elif item_type == 'polygon':
            poly = item['polygon']
            s_item['polygon'] = [[pt.x(), pt.y()] for pt in poly]
        elif item_type == 'path':
            s_item['path'] = serialize_path(item['path'])
        elif item_type == 'text':
            s_item['text'] = item['text']
            font = item['font']
            s_item['font'] = {
                'family': font.family(),
                'size': font.pointSizeF(),
                'bold': font.bold(),
                'italic': font.italic()
            }
            s_item['color'] = color_to_hex(item['color'])
            s_item['scale'] = item['scale']
        elif item_type == 'pixmap':
            s_item['pixmap'] = pixmap_to_base64(item['pixmap'])
            rect = item['rect']
            s_item['rect'] = [rect.x(), rect.y(), rect.width(), rect.height()]
            
        serialized_items.append(s_item)
        
    bg_pixmap_base64 = pixmap_to_base64(state['bg_pixmap'])
    bg_rect = state['bg_rect']
    original_image_rect = state['original_image_rect']
    
    project_data = {
        'version': '1.5.0',
        'bg_pixmap': bg_pixmap_base64,
        'bg_rect': [bg_rect.x(), bg_rect.y(), bg_rect.width(), bg_rect.height()],
        'original_image_rect': [original_image_rect.x(), original_image_rect.y(), original_image_rect.width(), original_image_rect.height()],
        'items': serialized_items
    }
    return project_data

def deserialize_project(project_data, scene):
    scene.clear()
    scene.margin_handles.clear()
    
    bg_pixmap = base64_to_pixmap(project_data['bg_pixmap'])
    scene.bg_item = scene.addPixmap(bg_pixmap)
    scene.bg_item.setZValue(-1.0)
    scene.bg_item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable ^ QGraphicsItem.GraphicsItemFlag.ItemIsFocusable)
    
    br = project_data['bg_rect']
    scene.setSceneRect(QRectF(br[0], br[1], br[2], br[3]))
    
    oir = project_data['original_image_rect']
    scene.original_image_rect = QRectF(oir[0], oir[1], oir[2], oir[3])
    
    for item_data in project_data['items']:
        item_type = item_data['type']
        pos = QPointF(item_data['pos'][0], item_data['pos'][1])
        
        pen = deserialize_pen(item_data['pen']) if 'pen' in item_data else None
        brush = deserialize_brush(item_data['brush']) if 'brush' in item_data else None
        
        new_item = None
        if item_type == 'line':
            line_coords = item_data['line']
            line = QLineF(line_coords[0], line_coords[1], line_coords[2], line_coords[3])
            new_item = CustomLineItem(line, pen)
        elif item_type == 'arrow':
            line_coords = item_data['line']
            line = QLineF(line_coords[0], line_coords[1], line_coords[2], line_coords[3])
            new_item = ArrowItem(line, pen)
        elif item_type == 'rect':
            r_coords = item_data['rect']
            rect = QRectF(r_coords[0], r_coords[1], r_coords[2], r_coords[3])
            new_item = CustomRectItem(rect, pen)
            if brush:
                new_item.setBrush(brush)
        elif item_type == 'ellipse':
            r_coords = item_data['rect']
            rect = QRectF(r_coords[0], r_coords[1], r_coords[2], r_coords[3])
            new_item = CustomEllipseItem(rect, pen)
            if brush:
                new_item.setBrush(brush)
        elif item_type == 'polygon':
            poly_pts = [QPointF(pt[0], pt[1]) for pt in item_data['polygon']]
            polygon = QPolygonF(poly_pts)
            new_item = CustomPolygonItem(polygon, pen)
            if brush:
                new_item.setBrush(brush)
        elif item_type == 'path':
            path = deserialize_path(item_data['path'])
            new_item = CustomPathItem(path, pen)
            if brush:
                new_item.setBrush(brush)
        elif item_type == 'text':
            new_item = CustomTextItem(item_data['text'])
            f_data = item_data['font']
            font = QFont(f_data['family'])
            font.setPointSizeF(f_data['size'])
            font.setBold(f_data['bold'])
            font.setItalic(f_data['italic'])
            new_item.setFont(font)
            new_item.setDefaultTextColor(hex_to_color(item_data['color']))
            if pen:
                new_item.setPen(pen)
            if brush:
                new_item.setBrush(brush)
            new_item.setScale(item_data['scale'])
        elif item_type == 'pixmap':
            pix = base64_to_pixmap(item_data['pixmap'])
            r_coords = item_data['rect']
            rect = QRectF(r_coords[0], r_coords[1], r_coords[2], r_coords[3])
            new_item = CustomPixmapItem(pix, rect)
            
        if new_item:
            new_item.setPos(pos)
            scene.addItem(new_item)
            
    scene.undo_stack.clear()
    scene.redo_stack.clear()
    scene.save_state()
    scene.has_unsaved_changes = False
    scene.update_margin_handles()


class AdvancedAnnotationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HandwrittenImageMiya")
        self.setGeometry(100, 100, 1200, 800)
        
        icon_path = resource_path("icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        self.apply_stylesheet()

        self.scene = AnnotationScene(self)
        self.scene.selectionChanged.connect(self.sync_properties_from_selection)

        self.view = CustomGraphicsView(self.scene, self)
        self.setCentralWidget(self.view)

        self.current_pdf_doc = None
        self.current_pdf_page = 0
        self.current_filename = "" 
        self.current_dir = "" 
        self.current_ext = "" 
        self.current_file_path = ""

        self.init_menubar()
        self.init_toolbar()


    def apply_stylesheet(self):
        """通常モード（ライト）のスタイル適用"""
        bg_main = "#F5F6F7"
        bg_toolbar = "#FFFFFF"
        bg_view = "#D0D7DE"
        text_main = "#333333"
        border_toolbar = "#D0D0D0"
        selection_bg = "#005FB8"
        selection_text = "#FFFFFF"
        hover_bg = "#E9E9E9"
        combo_bg = "#FFFFFF"
        dialog_bg = "#F5F6F7"

        style = f"""
        QMainWindow {{
            background-color: {bg_main};
        }}
        QMenuBar {{
            background-color: {bg_toolbar};
            border-bottom: 1px solid {border_toolbar};
            font-size: 13px;
            color: {text_main};
        }}
        QMenuBar::item {{
            background-color: transparent;
            padding: 6px 12px;
        }}
        QMenuBar::item:selected {{
            background-color: {selection_bg};
            color: {selection_text};
        }}
        QMenu {{
            background-color: {bg_toolbar};
            color: {text_main};
            border: 1px solid {border_toolbar};
            font-size: 13px;
        }}
        QMenu::item {{
            padding: 6px 25px 6px 20px;
        }}
        QMenu::item:selected {{
            background-color: {selection_bg};
            color: {selection_text};
        }}
        QToolBar {{
            background-color: {bg_toolbar};
            border-bottom: 1px solid {border_toolbar};
            spacing: 4px;
            padding: 4px;
        }}
        QToolButton {{
            color: {text_main};
            font-size: 12px;
            border: 1px solid transparent;
            border-radius: 4px;
            padding: 4px 8px;
            min-height: 20px;
            background-color: transparent;
        }}
        QToolButton:hover {{
            background-color: {hover_bg};
            border: 1px solid {border_toolbar};
        }}
        QToolButton:checked {{
            background-color: {selection_bg};
            border: 1px solid {selection_bg};
            color: {selection_text};
            font-weight: bold;
        }}
        QComboBox {{
            border: 1px solid {border_toolbar};
            border-radius: 4px;
            padding: 2px 8px;
            background-color: {combo_bg};
            color: {text_main};
            font-size: 12px;
            min-height: 20px;
            min-width: 65px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border: 1px solid {selection_bg};
        }}
        QToolBar QLabel {{
            color: {text_main};
            font-weight: bold;
            padding-left: 4px;
            font-size: 12px;
        }}
        QGraphicsView {{
            background-color: {bg_view};
            border: none;
        }}
        QDialog, QMessageBox {{
            background-color: {dialog_bg};
            color: {text_main};
        }}
        QMessageBox QLabel {{
            color: {text_main};
            font-size: 13px;
            font-weight: normal;
        }}
        QPushButton {{
            background-color: {combo_bg};
            color: {text_main};
            border: 1px solid {border_toolbar};
            border-radius: 4px;
            padding: 6px 20px;
            min-width: 60px;
            font-size: 13px;
        }}
        QPushButton:hover {{
            background-color: {selection_bg};
            color: {selection_text};
            border: 1px solid {selection_bg};
        }}
        QPushButton:pressed {{
            background-color: {hover_bg};
        }}
        QTextEdit {{
            background-color: {combo_bg};
            border: 1px solid {border_toolbar};
            border-radius: 4px;
            padding: 8px;
            color: {text_main};
        }}
        """
        self.setStyleSheet(style)


    def init_menubar(self):
        """メニューバーを構築し、ヘルプメニューを追加する"""
        menubar = self.menuBar()
        help_menu = menubar.addMenu("ヘルプ")

        readme_action = QAction("Readmeを表示", self)
        readme_action.triggered.connect(self.show_readme)
        help_menu.addAction(readme_action)

        help_menu.addSeparator()

        version_action = QAction("バージョン情報", self)
        version_action.triggered.connect(self.show_version_info)
        help_menu.addAction(version_action)

    def show_readme(self):
        """readme.mdを読み込み、専用のウィンドウで表示する"""
        readme_path = resource_path("readme.md")
        content = ""
        
        if os.path.exists(readme_path):
            try:
                with open(readme_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception as e:
                content = f"ファイルの読み込みに失敗しました:\n{e}"
        else:
            content = f"readme.md ファイルが見つかりませんでした。\n検索パス: {readme_path}"

        dialog = QDialog(self)
        dialog.setWindowTitle("Readme")
        dialog.resize(600, 450)
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit(dialog)
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        text_edit.setFont(font)
        
        layout.addWidget(text_edit)
        dialog.exec()

    def show_version_info(self):
        """バージョン情報をメッセージボックスで表示する"""
        title = "HandwrittenImageMiya"
        version = "v1.5.0"
        msg = f"{title}\nバージョン: {version}\n\nPyQt6ベースの高機能アノテーションツール"
        QMessageBox.about(self, "バージョン情報", msg)


    def init_toolbar(self):
        # ＝＝＝ 1段目のツールバー（ファイル操作、表示、ページ遷移） ＝＝＝
        toolbar1 = QToolBar("File and View Toolbar")
        toolbar1.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar1)

        # 1. ファイル操作
        save_action = QAction("💾 保存", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_file)
        toolbar1.addAction(save_action)

        save_as_action = QAction("💾 名前を付けて保存", self)
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self.save_file_as)
        toolbar1.addAction(save_as_action)

        # 2. プロジェクトの個別保存
        save_project_action = QAction("📦 プロジェクト保存", self)
        save_project_action.setShortcut("Ctrl+P")
        save_project_action.triggered.connect(self.save_project)
        toolbar1.addAction(save_project_action)

        open_action = QAction("📂 開く", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.open_file)
        toolbar1.addAction(open_action)

        toolbar1.addSeparator()

        # Undo/Redo
        undo_action = QAction("↩️ 戻る", self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self.scene.undo)
        toolbar1.addAction(undo_action)

        redo_action = QAction("↪️ 進む", self)
        redo_action.setShortcut("Ctrl+Y")
        redo_action.triggered.connect(self.scene.redo)
        toolbar1.addAction(redo_action)

        toolbar1.addSeparator()

        # ズーム操作
        zoom_out_action = QAction("🔍- 縮小", self)
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar1.addAction(zoom_out_action)

        zoom_in_action = QAction("🔍+ 拡大", self)
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar1.addAction(zoom_in_action)

        zoom_reset_action = QAction("🔍 100%", self)
        zoom_reset_action.triggered.connect(self.zoom_reset)
        toolbar1.addAction(zoom_reset_action)

        zoom_fit_action = QAction("🖥️ 画面に合わせる", self)
        zoom_fit_action.triggered.connect(self.fit_to_view)
        toolbar1.addAction(zoom_fit_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar1.addWidget(spacer)

        # ページ遷移
        self.prev_page_action = QAction("◀ 前ページ", self)
        self.prev_page_action.triggered.connect(lambda: self.change_page(-1))
        self.prev_page_action.setEnabled(False)
        toolbar1.addAction(self.prev_page_action)

        self.next_page_action = QAction("次ページ ▶", self)
        self.next_page_action.triggered.connect(lambda: self.change_page(1))
        self.next_page_action.setEnabled(False)
        toolbar1.addAction(self.next_page_action)

        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)

        # ＝＝＝ 2段目のツールバー（描画ツール、色、太さ・サイズ） ＝＝＝
        toolbar2 = QToolBar("Draw Toolbar")
        toolbar2.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar2)

        self.tool_actions = {}
        act_sel = QAction("↖️ 選択/移動", self)
        act_sel.setCheckable(True)
        act_sel.triggered.connect(lambda checked: self.set_tool("select"))
        toolbar2.addAction(act_sel)
        self.tool_actions["select"] = act_sel

        toolbar2.addSeparator()

        act_line = QAction("📏 線", self)
        act_line.setCheckable(True)
        act_line.triggered.connect(lambda checked: self.set_tool("line"))
        toolbar2.addAction(act_line)
        self.tool_actions["line"] = act_line

        self.line_combo = QComboBox(self)
        self.line_combo.addItems(["直線", "矢印", "曲線(フリーハンド)"])
        self.line_combo.currentIndexChanged.connect(self.change_line_type)
        toolbar2.addWidget(self.line_combo)

        act_shape = QAction("🔲 図形", self)
        act_shape.setCheckable(True)
        act_shape.triggered.connect(lambda checked: self.set_tool("shape"))
        toolbar2.addAction(act_shape)
        self.tool_actions["shape"] = act_shape

        self.shape_combo = QComboBox(self)
        self.shape_combo.addItems(["四角", "丸/楕円", "三角"])
        self.shape_combo.currentIndexChanged.connect(self.change_shape_type)
        toolbar2.addWidget(self.shape_combo)

        act_text = QAction("🔤 文字", self)
        act_text.setCheckable(True)
        act_text.triggered.connect(lambda checked: self.set_tool("text"))
        toolbar2.addAction(act_text)
        self.tool_actions["text"] = act_text

        act_insert_img = QAction("🖼️ 画像挿入", self)
        act_insert_img.triggered.connect(self.insert_image)
        toolbar2.addAction(act_insert_img)

        act_add_margin = QAction("⏹️ 余白調整(ドラッグ)", self)
        act_add_margin.setCheckable(True)
        act_add_margin.triggered.connect(lambda checked: self.set_tool("margin"))
        toolbar2.addAction(act_add_margin)
        self.tool_actions["margin"] = act_add_margin

        self.tool_actions["select"].setChecked(True)
        toolbar2.addSeparator()

        delete_action = QAction("🗑️ 削除", self)
        delete_action.setShortcut("Del")
        delete_action.triggered.connect(self.scene.delete_selected_items)
        toolbar2.addAction(delete_action)

        toolbar2.addSeparator()

        # 色設定（線・枠色 / 文字色 / 背景・塗色）
        pen_color_action = QAction("🖋️ 線/枠色", self)
        pen_color_action.triggered.connect(self.choose_pen_color)
        toolbar2.addAction(pen_color_action)

        text_color_action = QAction("🔤 文字色", self)
        text_color_action.triggered.connect(self.choose_text_color)
        toolbar2.addAction(text_color_action)

        brush_color_action = QAction("🪣 背景/塗色", self)
        brush_color_action.triggered.connect(self.choose_brush_color)
        toolbar2.addAction(brush_color_action)

        self.fill_combo = QComboBox(self)
        self.fill_combo.addItems(["透過 (枠のみ)", "塗りつぶし"])
        self.fill_combo.currentIndexChanged.connect(self.change_fill_mode)
        toolbar2.addWidget(self.fill_combo)

        toolbar2.addSeparator()

        # --- 図形・線の太さコントロール (分離) ---
        toolbar2.addWidget(QLabel("🖊️ 線太さ:"))
        self.width_combo = QComboBox(self)
        self.width_combo.setEditable(True) 
        width_options = ["0.5", "1.0", "1.5", "2.0", "3.0", "4.0", "5.0", "6.0", "8.0", "10.0", "12.0", "15.0", "20.0", "30.0", "50.0"]
        self.width_combo.addItems(width_options)
        self.width_combo.setCurrentText(str(float(self.scene.pen_width)))
        self.width_combo.currentTextChanged.connect(self.change_pen_width_text)
        toolbar2.addWidget(self.width_combo)

        # --- 文字のフォントサイズコントロール (分離) ---
        toolbar2.addWidget(QLabel("🔤 文字サイズ:"))
        self.font_size_combo = QComboBox(self)
        self.font_size_combo.setEditable(True)
        font_size_options = ["8", "10", "12", "14", "16", "18", "20", "24", "28", "32", "36", "48", "60", "72", "96", "120"]
        self.font_size_combo.addItems(font_size_options)
        self.font_size_combo.setCurrentText(str(int(self.scene.current_font_size)))
        self.font_size_combo.currentTextChanged.connect(self.change_font_size_text)
        toolbar2.addWidget(self.font_size_combo)


    def set_tool(self, tool_id):
        if tool_id != "text" and getattr(self.scene, 'pending_text_item', None):
            self.scene.removeItem(self.scene.pending_text_item)
            self.scene.pending_text_item = None

        if tool_id == "text":
            text, ok = QInputDialog.getMultiLineText(self, "テキスト入力", "キャンバスに配置する文字を入力してください:")
            if ok and text:
                font = QFont("Arial")
                font.setPointSizeF(max(4.0, self.scene.current_font_size))
                
                brush = QBrush(self.scene.current_brush_color) if self.scene.use_fill else QBrush(Qt.BrushStyle.NoBrush)
                pen = QPen(self.scene.current_pen_color)
                pen.setWidthF(self.scene.pen_width)
                if not self.scene.use_fill:
                    pen = QPen(Qt.PenStyle.NoPen)

                text_item = CustomTextItem(text)
                text_item.setFont(font)
                text_item.setDefaultTextColor(self.scene.current_text_color)
                text_item.setBrush(brush)
                text_item.setPen(pen)
                text_item.setZValue(self.scene.get_next_z_value())
                
                self.scene.addItem(text_item)
                self.scene.pending_text_item = text_item
            else:
                self.set_tool("select")
                return

        self.scene.current_tool = tool_id
        for tid, action in self.tool_actions.items():
            action.setChecked(tid == tool_id)
            
        self.scene.update_margin_handles()

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

    def change_line_type(self, index):
        line_types = ["line", "arrow", "freehand"]
        self.scene.current_line_type = line_types[index]
        self.set_tool("line")

    def change_shape_type(self, index):
        shape_types = ["rect", "ellipse", "triangle"]
        self.scene.current_shape_type = shape_types[index]
        self.set_tool("shape")

    def zoom_in(self):
        self.view.scale(1.25, 1.25)

    def zoom_out(self):
        self.view.scale(0.8, 0.8)

    def zoom_reset(self):
        self.view.resetTransform()

    def fit_to_view(self):
        if not self.scene.sceneRect().isEmpty():
            self.view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def sync_properties_from_selection(self):
        """選択アイテムからの各種プロパティ（色・線の太さ・文字サイズ）同期処理"""
        items = self.scene.selectedItems()
        if not items:
            return
        
        item = items[-1]
        if item == self.scene.bg_item:
            return

        self.width_combo.blockSignals(True)
        self.font_size_combo.blockSignals(True)
        self.fill_combo.blockSignals(True)

        if isinstance(item, (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem)):
            pen = item.pen()
            self.scene.current_pen_color = pen.color()
            self.scene.pen_width = max(0.5, pen.widthF())
            self.width_combo.setCurrentText(str(self.scene.pen_width))
            
            if hasattr(item, 'brush'):
                brush = item.brush()
                if brush.style() != Qt.BrushStyle.NoBrush:
                    self.scene.current_brush_color = brush.color()
                    self.scene.use_fill = True
                    self.fill_combo.setCurrentIndex(1)
                else:
                    self.scene.use_fill = False
                    self.fill_combo.setCurrentIndex(0)
            
        elif isinstance(item, CustomTextItem):
            self.scene.current_text_color = item.defaultTextColor()
            font = item.font()
            self.scene.current_font_size = font.pointSizeF()
            self.font_size_combo.setCurrentText(str(round(self.scene.current_font_size, 1)))

            pen = item.pen()
            if pen.style() != Qt.PenStyle.NoPen:
                self.scene.current_pen_color = pen.color()
                self.scene.pen_width = max(0.5, pen.widthF())
                self.width_combo.setCurrentText(str(self.scene.pen_width))
            
            brush = item.brush()
            if brush.style() != Qt.BrushStyle.NoBrush:
                self.scene.current_brush_color = brush.color()
                self.scene.use_fill = True
                self.fill_combo.setCurrentIndex(1)
            else:
                self.scene.use_fill = False
                self.fill_combo.setCurrentIndex(0)

        self.width_combo.blockSignals(False)
        self.font_size_combo.blockSignals(False)
        self.fill_combo.blockSignals(False)

    def choose_pen_color(self):
        """線や枠の色を変更"""
        color = QColorDialog.getColor(self.scene.current_pen_color, self)
        if color.isValid():
            self.scene.current_pen_color = color
            changed = False
            for item in self.scene.selectedItems():
                if isinstance(item, (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem)):
                    pen = item.pen()
                    pen.setColor(color)
                    item.setPen(pen)
                    changed = True
                elif isinstance(item, CustomTextItem):
                    if item.pen().style() != Qt.PenStyle.NoPen:
                        pen = item.pen()
                        pen.setColor(color)
                        item.setPen(pen)
                        changed = True
            if changed:
                self.scene.has_unsaved_changes = True
                self.scene.save_state()

    def choose_text_color(self):
        """文字の色を変更"""
        color = QColorDialog.getColor(self.scene.current_text_color, self)
        if color.isValid():
            self.scene.current_text_color = color
            changed = False
            for item in self.scene.selectedItems():
                if isinstance(item, CustomTextItem):
                    item.setDefaultTextColor(color)
                    changed = True
            if changed:
                self.scene.has_unsaved_changes = True
                self.scene.save_state()

    def choose_brush_color(self):
        """背景や塗りつぶしの色を変更"""
        color = QColorDialog.getColor(self.scene.current_brush_color, self)
        if color.isValid():
            self.scene.current_brush_color = color
            changed = False
            for item in self.scene.selectedItems():
                if isinstance(item, (CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem, CustomTextItem)):
                    if self.scene.use_fill:
                        brush = QBrush(color)
                        item.setBrush(brush)
                        changed = True
            if changed:
                self.scene.has_unsaved_changes = True
                self.scene.save_state()

    def change_fill_mode(self, index):
        """透過モードと塗りつぶしモードを切り替え"""
        self.scene.use_fill = (index == 1)
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem)):
                brush = QBrush(self.scene.current_brush_color) if self.scene.use_fill else QBrush(Qt.BrushStyle.NoBrush)
                item.setBrush(brush)
                changed = True
            elif isinstance(item, CustomTextItem):
                brush = QBrush(self.scene.current_brush_color) if self.scene.use_fill else QBrush(Qt.BrushStyle.NoBrush)
                item.setBrush(brush)
                if self.scene.use_fill:
                    pen = QPen(self.scene.current_pen_color)
                    pen.setWidthF(self.scene.pen_width)
                    item.setPen(pen)
                else:
                    item.setPen(QPen(Qt.PenStyle.NoPen))
                changed = True
                
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()


    def change_pen_width_text(self, text):
        """線の太さ（図形/線）用コンボボックスの変更ハンドラ"""
        try:
            value = float(text)
            if value < 0.1: value = 0.1 
            self.change_pen_width(value)
        except ValueError:
            pass 

    def change_pen_width(self, value):
        """図形や線の太さ（枠線）を更新"""
        self.scene.pen_width = value
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem)):
                pen = item.pen()
                pen.setWidthF(value)
                item.setPen(pen)
                changed = True
            elif isinstance(item, CustomTextItem):
                if item.pen().style() != Qt.PenStyle.NoPen:
                    pen = item.pen()
                    pen.setWidthF(value)
                    item.setPen(pen)
                    changed = True
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()

    def change_font_size_text(self, text):
        """文字サイズ（テキスト）用コンボボックスの変更ハンドラ"""
        try:
            value = float(text)
            if value < 1.0: value = 1.0
            self.change_font_size(value)
        except ValueError:
            pass

    def change_font_size(self, value):
        """テキストのフォントサイズを更新（図形の太さとは独立）"""
        self.scene.current_font_size = value
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, CustomTextItem):
                font = item.font()
                font.setPointSizeF(value)
                item.setFont(font)
                changed = True
        if changed:
            self.scene.has_unsaved_changes = True
            self.scene.save_state()


    def check_unsaved_changes(self):
        if self.scene.has_unsaved_changes:
            reply = QMessageBox.question(
                self, "確認", "保存されていない変更があります。\n現在の変更を破棄してもよろしいですか？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            return reply == QMessageBox.StandardButton.Yes
        return True

    def open_file(self):
        if not self.check_unsaved_changes():
            return

        default_dir = self.current_dir if self.current_dir else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "ファイルを開く", default_dir, "Supported Files (*.png *.jpg *.jpeg *.pdf *.hwi);;Images/PDF (*.png *.jpg *.jpeg *.pdf);;HandwrittenImage Projects (*.hwi)"
        )
        if not file_path:
            return

        self.current_file_path = file_path
        self.current_dir = os.path.dirname(file_path)
        self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
        self.current_ext = os.path.splitext(file_path)[1].lower()

        self.current_pdf_doc = None
        self.prev_page_action.setEnabled(False)
        self.next_page_action.setEnabled(False)
        self.zoom_reset()

        if self.current_ext == ".hwi":
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    project_data = json.load(f)
                deserialize_project(project_data, self.scene)
                self.setWindowTitle(f"HandwrittenImageMiya - {os.path.basename(file_path)}")
                self.fit_to_view()
            except Exception as e:
                QMessageBox.warning(self, "エラー", f"プロジェクトの読み込みに失敗しました。\n{e}")
        elif self.current_ext == ".pdf":
            self.current_pdf_doc = fitz.open(file_path)
            self.current_pdf_page = 0
            self.load_pdf_page()
            self.prev_page_action.setEnabled(True)
            self.next_page_action.setEnabled(True)
        else:
            reader = QImageReader(file_path)
            reader.setAutoTransform(True)
            image = reader.read()
            if not image.isNull():
                pixmap = QPixmap.fromImage(image)
                self.scene.set_background(pixmap)
                self.setWindowTitle(f"HandwrittenImageMiya - {os.path.basename(file_path)}")
                self.fit_to_view()
            else:
                QMessageBox.warning(self, "エラー", "画像の読み込みに失敗しました。")

    def load_pdf_page(self):
        if not self.current_pdf_doc: return
        page = self.current_pdf_doc.load_page(self.current_pdf_page)
        pix = page.get_pixmap(alpha=False)
        fmt = QImage.Format.Format_RGB888
        qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
        self.scene.set_background(QPixmap.fromImage(qimg))
        self.setWindowTitle(f"HandwrittenImageMiya - {os.path.basename(self.current_file_path)} (Page {self.current_pdf_page + 1}/{len(self.current_pdf_doc)})")
        self.fit_to_view()

    def change_page(self, delta):
        if self.current_pdf_doc:
            if not self.check_unsaved_changes():
                return
            new_page = self.current_pdf_page + delta
            if 0 <= new_page < len(self.current_pdf_doc):
                self.current_pdf_page = new_page
                self.load_pdf_page()


    def insert_image(self):
        """外部画像またはPDFページを注釈としてキャンバスの中に挿入する"""
        default_dir = self.current_dir if self.current_dir else os.path.expanduser("~")
        file_path, _ = QFileDialog.getOpenFileName(
            self, "挿入する画像またはPDFを選択", default_dir, "Images/PDF (*.png *.jpg *.jpeg *.pdf)"
        )
        if not file_path:
            return

        ext = os.path.splitext(file_path)[1].lower()
        pixmap = None

        try:
            if ext == ".pdf":
                doc = fitz.open(file_path)
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
                            doc.close()
                            return
                    page = doc.load_page(page_num)
                    pix = page.get_pixmap(alpha=False)
                    fmt = QImage.Format.Format_RGB888
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt)
                    pixmap = QPixmap.fromImage(qimg)
                doc.close()
            else:
                reader = QImageReader(file_path)
                reader.setAutoTransform(True)
                image = reader.read()
                if not image.isNull():
                    pixmap = QPixmap.fromImage(image)

            if pixmap and not pixmap.isNull():
                view_rect = self.view.viewport().rect()
                scene_center = self.view.mapToScene(view_rect.center())
                
                w = float(pixmap.width())
                h = float(pixmap.height())
                max_size = 300.0
                if w > max_size or h > max_size:
                    ratio = min(max_size / w, max_size / h)
                    w *= ratio
                    h *= ratio
                
                rect = QRectF(-w / 2, -h / 2, w, h)
                item = CustomPixmapItem(pixmap, rect)
                item.setPos(scene_center)
                item.setZValue(self.scene.get_next_z_value())
                self.scene.addItem(item)
                
                self.scene.clearSelection()
                item.setSelected(True)
                
                self.scene.has_unsaved_changes = True
                self.scene.save_state()
                self.set_tool("select")
            else:
                QMessageBox.warning(self, "エラー", "ファイルの読み込みに失敗しました。")
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"画像の挿入中にエラーが発生しました。\n{e}")

    def apply_margin(self, top, bottom, left, right, color):
        """余白を作成・削減して背景画像に適用し、既存の注釈をシフトして位置を補正する"""
        try:
            current_bg_pixmap = self.scene.bg_item.pixmap()
            orig_w = current_bg_pixmap.width()
            orig_h = current_bg_pixmap.height()
            
            new_w = orig_w + left + right
            new_h = orig_h + top + bottom
            
            if new_w < 10: new_w = 10
            if new_h < 10: new_h = 10
            
            new_pixmap = QPixmap(new_w, new_h)
            new_pixmap.fill(color)
            
            src_x = -left if left < 0 else 0
            src_y = -top if top < 0 else 0
            src_w = orig_w - (-left if left < 0 else 0) - (-right if right < 0 else 0)
            src_h = orig_h - (-top if top < 0 else 0) - (-bottom if bottom < 0 else 0)
            
            if src_w < 1: src_w = 1
            if src_h < 1: src_h = 1
            
            dest_x = left if left >= 0 else 0
            dest_y = top if top >= 0 else 0
            
            painter = QPainter(new_pixmap)
            painter.drawPixmap(dest_x, dest_y, current_bg_pixmap, src_x, src_y, src_w, src_h)
            painter.end()
            
            items_to_move = []
            for item in self.scene.items():
                if (item != self.scene.bg_item and 
                    item.parentItem() is None and 
                    item != getattr(self.scene, 'pending_text_item', None) and 
                    not isinstance(item, MarginHandleItem)):
                    items_to_move.append(item)
                    
            for item in items_to_move:
                item.moveBy(float(left), float(top))
                
            self.scene.bg_item.setPixmap(new_pixmap)
            self.scene.setSceneRect(QRectF(new_pixmap.rect()))
            
            if hasattr(self.scene, 'original_image_rect') and self.scene.original_image_rect:
                self.scene.original_image_rect.translate(float(left), float(top))
            
            self.scene.update_margin_handles()
            
            self.scene.has_unsaved_changes = True
            self.scene.save_state()
            self.scene.update()
            self.fit_to_view()
            
        except Exception as e:
            QMessageBox.critical(self, "エラー", f"余白追加・削減の実行中にエラーが発生しました。\n{e}")


    def save_file(self):
        """開いたファイル形式と同じ形式で上書き保存（パスがない場合は新規画像保存へ）"""
        if not self.current_file_path:
            return self.save_file_as()
        
        self.perform_actual_save(self.current_file_path)

    def save_file_as(self):
        """名前を付けて保存（エクスポート専用、デフォルトは.jpg）"""
        default_ext = ".jpg"
        
        initial_name = f"{self.current_filename}_After{default_ext}"
        if not self.current_filename:
            initial_name = f"untitled{default_ext}"

        initial_path = os.path.join(self.current_dir, initial_name) if self.current_dir else initial_name
        
        filter_str = "JPEG Image (*.jpg);;PNG Image (*.png);;PDF Document (*.pdf)"
        
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "名前を付けて保存", initial_path, filter_str
        )
        if not file_path:
            return

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

        self.perform_actual_save(file_path)

    def perform_actual_save(self, file_path):
        """指定されたパスに実際に保存処理を行う"""
        save_ext = os.path.splitext(file_path)[1].lower()
        rect = self.scene.sceneRect()
        if rect.isEmpty() or rect.width() <= 0 or rect.height() <= 0:
            QMessageBox.warning(self, "エラー", "保存する内容がありません（画面サイズが無効です）。")
            return

        try:
            if getattr(self.scene, 'pending_text_item', None):
                self.scene.removeItem(self.scene.pending_text_item)
                self.scene.pending_text_item = None
                self.set_tool("select")

            if save_ext == ".hwi":
                project_data = serialize_project(self.scene)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(project_data, f, ensure_ascii=False, indent=2)
                self.scene.has_unsaved_changes = False
                self.current_file_path = file_path
                self.current_dir = os.path.dirname(file_path)
                self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                self.current_ext = ".hwi"
                self.setWindowTitle(f"HandwrittenImageMiya - {os.path.basename(file_path)}")
                self.show_auto_close_message("完了", "プロジェクトファイル(.hwi)として保存しました。")
                return

            if save_ext == ".pdf":
                self.scene.clearSelection()
                image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
                image.fill(Qt.GlobalColor.white)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                self.scene.render(painter)
                painter.end()
                
                temp_img = os.path.join(tempfile.gettempdir(), "temp_save_anno.jpg")
                image.save(temp_img, "JPEG", 95)
                
                doc = fitz.open()
                imgdoc = fitz.open(temp_img)
                pdfbytes = imgdoc.convert_to_pdf()
                imgdoc.close()
                
                pdf_stream = fitz.open("pdf", pdfbytes)
                doc.insert_pdf(pdf_stream)
                doc.save(file_path)
                
                pdf_stream.close()
                doc.close()
                if os.path.exists(temp_img): os.remove(temp_img)
                
                self.scene.has_unsaved_changes = False
                self.current_file_path = file_path
                self.current_dir = os.path.dirname(file_path)
                self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                self.current_ext = ".pdf"
                self.setWindowTitle(f"HandwrittenImageMiya - {os.path.basename(file_path)}")
                self.show_auto_close_message("完了", "PDFとして保存しました。")
                return

            self.scene.clearSelection()
            image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.scene.render(painter)
            painter.end()

            if image.save(file_path):
                self.scene.has_unsaved_changes = False
                self.current_file_path = file_path
                self.current_dir = os.path.dirname(file_path)
                self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
                self.current_ext = save_ext
                self.setWindowTitle(f"HandwrittenImageMiya - {os.path.basename(file_path)}")
                self.show_auto_close_message("完了", f"{save_ext.upper()}として保存しました。")
            else:
                QMessageBox.warning(self, "エラー", "保存に失敗しました。")
                
        except Exception as e:
            QMessageBox.critical(self, "致命的なエラー", f"保存処理中にエラーが発生しました。\n{e}")

    def show_auto_close_message(self, title, text):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(QMessageBox.StandardButton.NoButton)
        QTimer.singleShot(3000, msg.accept)
        msg.exec()

    def closeEvent(self, event):
        if self.check_unsaved_changes():
            event.accept()
        else:
            event.ignore()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = AdvancedAnnotationApp()
    window.showMaximized()
    sys.exit(app.exec())
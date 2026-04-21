# app.pyw
import sys
import os
import math
import fitz # PyMuPDF
import tempfile # 一時ファイルを安全に処理するため
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QToolBar, QFileDialog, QInputDialog, QColorDialog,
    QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem,
    QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsPathItem,
    QGraphicsItem, QMessageBox, QLabel, QMenu, QComboBox,
    QWidget, QSizePolicy, QDialog, QVBoxLayout, QTextEdit, QPushButton
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QPolygonF, QFont, QAction, QTransform,
    QPainterPath, QPainterPathStroker, QImageReader, QBrush, QPalette
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF, QTimer

# ==============================
# リソースパス取得関数 (exe化対応)
# ==============================
def resource_path(relative_path):
    """実行時（exe）でも通常時（.pyw）でも正しいファイルパスを取得する"""
    try:
        # PyInstallerで展開された時の一時フォルダパス
        base_path = sys._MEIPASS
    except Exception:
        # 通常のPythonスクリプトとして実行した時のパス
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

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


class AnnotationScene(QGraphicsScene):
    """画像と注釈を管理するシーン"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tool = "select"
        self.current_line_type = "line"
        self.current_shape_type = "rect"
        
        # 枠線・文字色と、塗りつぶし・背景色を分離
        self.current_pen_color = QColor(Qt.GlobalColor.red)
        self.current_text_color = QColor(Qt.GlobalColor.red) # 文字色を追加
        self.current_brush_color = QColor(Qt.GlobalColor.white)
        self.use_fill = False
        self.pen_width = 5.0
        
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
        
        self.current_path = None
        self.copied_data = None
        
        self.has_unsaved_changes = False
        
        # Undo/Redo用のスタック
        self.undo_stack = []
        self.redo_stack = []
        self.was_modified = False

    def get_next_z_value(self):
        """シーン内で最も前面に配置するためのZ値を取得"""
        max_z = 0.0
        for item in self.items():
            if item != self.bg_item and item.zValue() > max_z:
                max_z = item.zValue()
        return max_z + 1.0

    def bring_to_front(self, item):
        """指定したアイテムを最前面に移動"""
        if not item or item == self.bg_item:
            return
        item.setZValue(self.get_next_z_value())
        self.has_unsaved_changes = True
        self.save_state()
        self.update()

    def get_scene_state(self):
        """現在のシーンのアイテム状態をシリアライズして取得"""
        state = []
        for item in self.items():
            if item == self.bg_item or item.zValue() < 0 or item == self.pending_text_item:
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
        return list(reversed(state))

    def restore_scene_state(self, state):
        """保存された状態からシーンを復元"""
        for item in self.items():
            if item != self.bg_item:
                self.removeItem(item)
        
        self.clearSelection()

        for i, data in enumerate(state):
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
            
            if new_item:
                new_item.setZValue(float(i + 1))
                new_item.setPos(data['pos'])
                self.addItem(new_item)

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
        self.bg_item = self.addPixmap(pixmap)
        self.bg_item.setZValue(-1.0) 
        self.bg_item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable ^ QGraphicsItem.GraphicsItemFlag.ItemIsFocusable) 
        self.setSceneRect(QRectF(pixmap.rect()))
        
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.save_state()
        self.has_unsaved_changes = False

    def drawForeground(self, painter, rect):
        """選択アイテムにサイズ変更用のハンドルを描画"""
        super().drawForeground(painter, rect)
        if self.current_tool != "select":
            return

        painter.setBrush(QColor(0, 120, 255))
        painter.setPen(QPen(Qt.GlobalColor.white, 1))
        handle_size = 12

        for item in self.selectedItems():
            if item == self.bg_item or item == self.pending_text_item:
                continue

            if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
                br = item.mapToScene(item.rect().bottomRight())
                painter.drawRect(QRectF(br.x() - handle_size/2, br.y() - handle_size/2, handle_size, handle_size))
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
                
                if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
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
        # プレビューテキストの追従
        if self.current_tool == "text" and getattr(self, 'pending_text_item', None):
            self.pending_text_item.setPos(event.scenePos())
            event.accept()
            return

        if self.current_tool == "select":
            if event.buttons() == Qt.MouseButton.NoButton:
                pos = event.scenePos()
                handle_area = 30
                on_handle = False
                cursor_shape = Qt.CursorShape.ArrowCursor

                for item in self.selectedItems():
                    if item == self.bg_item:
                        continue
                    
                    if isinstance(item, (QGraphicsRectItem, QGraphicsEllipseItem)):
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
                    if item_under_mouse and item_under_mouse != self.bg_item:
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

                if self.resize_mode == "shape_br":
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
                    if item != self.bg_item:
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
            if item != self.bg_item:
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
        
        if target_item == self.bg_item:
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

        action = menu.exec(event.screenPos())

        if action == bring_front_action:
            self.bring_to_front(target_item)
        elif action == copy_action:
            self.copy_item(target_item)
        elif action == paste_action:
            self.paste_item(pos)
        elif edit_text_action and action == edit_text_action:
            self.edit_text_item(target_item)

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


class AdvancedAnnotationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HandwrittenImageMiya")
        self.setGeometry(100, 100, 1200, 800)
        
        # 画面のスタイル（デザイン）を適用（初期状態はシステム設定に追従）
        self.is_dark = self.palette().color(QPalette.ColorRole.Window).lightness() < 128
        self.apply_stylesheet(self.is_dark)

        self.scene = AnnotationScene(self)
        self.scene.selectionChanged.connect(self.sync_properties_from_selection)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setMouseTracking(True) # マウス追従プレビューのために必要
        self.setCentralWidget(self.view)

        self.current_pdf_doc = None
        self.current_pdf_page = 0
        self.current_filename = "" 
        self.current_dir = "" 
        self.current_ext = "" 

        self.init_menubar()
        self.init_toolbar()

    def apply_stylesheet(self, is_dark=False):
        """テーマの適用（ライトモード・ダークモード対応、選択状態の視認性向上）"""
        if is_dark:
            # ダークモード用カラー
            bg_main = "#1E1E1E"
            bg_toolbar = "#2D2D2D"
            bg_view = "#121212"
            text_main = "#E0E0E0"
            border_toolbar = "#3F3F3F"
            selection_bg = "#0078D7"
            selection_text = "#FFFFFF"
            hover_bg = "#3D3D3D"
            combo_bg = "#333333"
            dialog_bg = "#252526"
        else:
            # 通常モード（ライト）用カラー
            bg_main = "#F5F6F7"
            bg_toolbar = "#FFFFFF"
            bg_view = "#D0D7DE"
            text_main = "#333333"
            border_toolbar = "#D0D0D0"
            selection_bg = "#005FB8" # 濃い目の青にして選択状態をはっきりさせる
            selection_text = "#FFFFFF"
            hover_bg = "#E9E9E9"
            combo_bg = "#FFFFFF"
            dialog_bg = "#F5F6F7"

        style = f"""
        QMainWindow {{
            background-color: {bg_main};
        }}
        /* メニューバー */
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
        /* ツールバー */
        QToolBar {{
            background-color: {bg_toolbar};
            border-bottom: 1px solid {border_toolbar};
            spacing: 4px;
            padding: 4px;
        }}
        /* ツールバーのボタン（選択状態を強調） */
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
        /* コンボボックス */
        QComboBox {{
            border: 1px solid {border_toolbar};
            border-radius: 4px;
            padding: 2px 8px;
            background-color: {combo_bg};
            color: {text_main};
            font-size: 12px;
            min-height: 20px;
            min-width: 80px;
        }}
        QComboBox:hover, QComboBox:focus {{
            border: 1px solid {selection_bg};
        }}
        /* ツールバー内のラベル */
        QToolBar QLabel {{
            color: {text_main};
            font-weight: bold;
            padding-left: 4px;
            font-size: 12px;
        }}
        /* 画像表示エリア（キャンバスの外側） */
        QGraphicsView {{
            background-color: {bg_view};
            border: none;
        }}
        /* ダイアログ全般 */
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

    def toggle_theme(self):
        """通常モード（ライト）とダークモードを切り替える"""
        self.is_dark = not self.is_dark
        self.apply_stylesheet(self.is_dark)
        # アイコンを更新
        self.theme_action.setText("🌙" if not self.is_dark else "☀️")


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

        # テキストを表示するためのダイアログを作成
        dialog = QDialog(self)
        dialog.setWindowTitle("Readme")
        dialog.resize(600, 450)
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit(dialog)
        text_edit.setPlainText(content)
        text_edit.setReadOnly(True) # 編集不可に設定
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        text_edit.setFont(font)
        
        layout.addWidget(text_edit)
        dialog.exec()

    def show_version_info(self):
        """バージョン情報をメッセージボックスで表示する"""
        title = "HandwrittenImageMiya"
        version = "v1.3.0"
        msg = f"{title}\nバージョン: {version}\n\nPyQt6ベースの高機能アノテーションツール"
        QMessageBox.about(self, "バージョン情報", msg)

    def init_toolbar(self):
        # ＝＝＝ 1段目のツールバー（ファイル操作、表示、ページ遷移） ＝＝＝
        toolbar1 = QToolBar("File and View Toolbar")
        toolbar1.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar1)

        # 1. ファイル操作
        open_action = QAction("📂 開く", self)
        open_action.triggered.connect(self.open_file)
        toolbar1.addAction(open_action)

        save_action = QAction("💾 保存", self)
        save_action.triggered.connect(self.save_file)
        toolbar1.addAction(save_action)

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

        # 右端に寄せるためのスペーサー
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

        toolbar1.addSeparator()

        # テーマ切り替えボタン
        self.theme_action = QAction("🌙" if not self.is_dark else "☀️", self)
        self.theme_action.triggered.connect(self.toggle_theme)
        toolbar1.addAction(self.theme_action)

        # 改行を入れてツールバーを2段にする
        self.addToolBarBreak(Qt.ToolBarArea.TopToolBarArea)

        # ＝＝＝ 2段目のツールバー（描画ツール、色、太さ） ＝＝＝
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

        self.tool_actions["select"].setChecked(True)
        toolbar2.addSeparator()

        # 削除ボタン
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

        toolbar2.addWidget(QLabel("🖊️ 太さ: "))
        self.width_combo = QComboBox(self)
        self.width_combo.setEditable(True) 
        width_options = ["0.5", "1.0", "1.5", "2.0", "3.0", "4.0", "5.0", "6.0", "8.0", "10.0", "12.0", "15.0", "20.0", "30.0", "50.0"]
        self.width_combo.addItems(width_options)
        self.width_combo.setCurrentText(str(float(self.scene.pen_width)))
        self.width_combo.currentTextChanged.connect(self.change_pen_width_text)
        toolbar2.addWidget(self.width_combo)

    def set_tool(self, tool_id):
        # 他のツールに切り替わるときに、未確定のプレビューテキストがあれば削除する
        if tool_id != "text" and getattr(self.scene, 'pending_text_item', None):
            self.scene.removeItem(self.scene.pending_text_item)
            self.scene.pending_text_item = None

        if tool_id == "text":
            # 先にテキスト入力を受け付ける
            text, ok = QInputDialog.getMultiLineText(self, "テキスト入力", "キャンバスに配置する文字を入力してください:")
            if ok and text:
                # プレビュー用のアイテムを仮生成してシーンに追加
                font = QFont("Arial")
                font.setPointSizeF(max(6.0, self.scene.pen_width * 3.0))
                
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
                # キャンセルされたら「選択ツール」に戻す
                self.set_tool("select")
                return

        self.scene.current_tool = tool_id
        for tid, action in self.tool_actions.items():
            action.setChecked(tid == tool_id)
            
        if tool_id == "select":
            self.view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
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
        items = self.scene.selectedItems()
        if not items:
            return
        
        item = items[-1]
        if item == self.scene.bg_item:
            return

        self.width_combo.blockSignals(True)
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
        try:
            value = float(text)
            if value < 0.1: value = 0.1 
            self.change_pen_width(value)
        except ValueError:
            pass 

    def change_pen_width(self, value):
        self.scene.pen_width = value
        changed = False
        for item in self.scene.selectedItems():
            if isinstance(item, (CustomLineItem, ArrowItem, CustomRectItem, CustomEllipseItem, CustomPolygonItem, CustomPathItem)):
                pen = item.pen()
                pen.setWidthF(value)
                item.setPen(pen)
                changed = True
            elif isinstance(item, CustomTextItem):
                font = item.font()
                font.setPointSizeF(max(6.0, value * 3.0))
                item.setFont(font)
                if item.pen().style() != Qt.PenStyle.NoPen:
                    pen = item.pen()
                    pen.setWidthF(value)
                    item.setPen(pen)
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
            self, "ファイルを開く", default_dir, "Images/PDF (*.png *.jpg *.jpeg *.pdf)"
        )
        if not file_path:
            return

        self.current_dir = os.path.dirname(file_path)
        self.current_filename = os.path.splitext(os.path.basename(file_path))[0]
        self.current_ext = os.path.splitext(file_path)[1].lower()

        self.current_pdf_doc = None
        self.prev_page_action.setEnabled(False)
        self.next_page_action.setEnabled(False)
        self.zoom_reset()

        if self.current_ext == ".pdf":
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
        self.setWindowTitle(f"HandwrittenImageMiya - Page {self.current_pdf_page + 1}/{len(self.current_pdf_doc)}")
        self.fit_to_view()

    def change_page(self, delta):
        if self.current_pdf_doc:
            if not self.check_unsaved_changes():
                return
            new_page = self.current_pdf_page + delta
            if 0 <= new_page < len(self.current_pdf_doc):
                self.current_pdf_page = new_page
                self.load_pdf_page()

    def save_file(self):
        # 元の拡張子をそのままデフォルト設定にする
        default_ext = self.current_ext
        if not default_ext: default_ext = ".jpg"
        
        initial_name = f"{self.current_filename}_After{default_ext}"
        initial_path = os.path.join(self.current_dir, initial_name) if self.current_dir else initial_name
        
        # フィルター文字列の作成
        if default_ext == ".png":
            filter_str = "PNG Image (*.png);;JPEG Image (*.jpg);;PDF Document (*.pdf)"
        elif default_ext == ".pdf":
            filter_str = "PDF Document (*.pdf);;JPEG Image (*.jpg);;PNG Image (*.png)"
        elif default_ext in [".jpg", ".jpeg"]:
            filter_str = "JPEG Image (*.jpg);;PNG Image (*.png);;PDF Document (*.pdf)"
        else:
            filter_str = "JPEG Image (*.jpg);;PNG Image (*.png);;PDF Document (*.pdf)"
        
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "保存", initial_path, filter_str
        )
        if not file_path:
            return

        save_ext = os.path.splitext(file_path)[1].lower()

        rect = self.scene.sceneRect()
        if rect.isEmpty() or rect.width() <= 0 or rect.height() <= 0:
            QMessageBox.warning(self, "エラー", "保存する内容がありません（画面サイズが無効です）。")
            return

        try:
            # プレビュー中の未確定テキストがあれば解除してから保存
            if getattr(self.scene, 'pending_text_item', None):
                self.scene.removeItem(self.scene.pending_text_item)
                self.scene.pending_text_item = None
                self.set_tool("select")

            # PDF保存ロジック（画像化してPDFに変換）
            if save_ext == ".pdf":
                self.scene.clearSelection()
                image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
                image.fill(Qt.GlobalColor.white)
                painter = QPainter(image)
                painter.setRenderHint(QPainter.RenderHint.Antialiasing)
                self.scene.render(painter)
                painter.end()
                
                # 一時ファイルを経由してPDF化 (権限エラー回避のためtempfileを使用)
                temp_img = os.path.join(tempfile.gettempdir(), "temp_save_anno.jpg")
                image.save(temp_img, "JPEG", 95)
                
                doc = fitz.open()
                imgdoc = fitz.open(temp_img)
                pdfbytes = imgdoc.convert_to_pdf()
                imgdoc.close()
                
                # ★ C++側のガベージコレクション問題を回避するため変数に保持して渡す
                pdf_stream = fitz.open("pdf", pdfbytes)
                doc.insert_pdf(pdf_stream)
                doc.save(file_path)
                
                pdf_stream.close()
                doc.close()
                if os.path.exists(temp_img): os.remove(temp_img)
                
                self.scene.has_unsaved_changes = False
                self.show_auto_close_message("完了", "PDFとして保存しました。")
                return

            # 画像保存ロジック
            self.scene.clearSelection()
            image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.scene.render(painter)
            painter.end()

            if image.save(file_path):
                self.scene.has_unsaved_changes = False
                self.current_dir = os.path.dirname(file_path)
                self.show_auto_close_message("完了", f"{save_ext.upper()}として保存しました。")
            else:
                QMessageBox.warning(self, "エラー", "保存に失敗しました。")
                
        except Exception as e:
            # 予期せぬエラーでもアプリが落ちないようにする
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
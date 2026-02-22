# app.py
import sys
import os
import math
import fitz  # PyMuPDF
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QGraphicsView, QGraphicsScene,
    QToolBar, QFileDialog, QInputDialog, QColorDialog,
    QGraphicsRectItem, QGraphicsLineItem, QGraphicsTextItem,
    QGraphicsEllipseItem, QGraphicsPolygonItem, QGraphicsPathItem,
    QGraphicsItem, QMessageBox, QLabel, QMenu, QComboBox,
    QWidget, QSizePolicy
)
from PyQt6.QtGui import (
    QPixmap, QImage, QPainter, QPen, QColor, QPolygonF, QFont, QAction, QTransform,
    QPainterPath, QPainterPathStroker, QImageReader
)
from PyQt6.QtCore import Qt, QPointF, QRectF, QLineF, QTimer

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


class AnnotationScene(QGraphicsScene):
    """画像と注釈を管理するシーン"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_tool = "select"
        self.current_line_type = "line"
        self.current_shape_type = "rect"
        self.current_color = QColor(Qt.GlobalColor.red)
        self.pen_width = 5.0
        
        self.start_point = None
        self.temp_item = None
        self.bg_item = None

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

    def set_background(self, pixmap):
        self.clear()
        self.bg_item = self.addPixmap(pixmap)
        self.bg_item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable ^ QGraphicsItem.GraphicsItemFlag.ItemIsFocusable) 
        self.setSceneRect(QRectF(pixmap.rect()))
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
            if item == self.bg_item:
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
            elif isinstance(item, QGraphicsTextItem):
                br = item.mapToScene(item.boundingRect().bottomRight())
                painter.drawRect(QRectF(br.x() - handle_size/2, br.y() - handle_size/2, handle_size, handle_size))

    def mousePressEvent(self, event):
        if self.current_tool == "select":
            if event.button() == Qt.MouseButton.RightButton:
                super().mousePressEvent(event)
                return
                
            pos = event.scenePos()
            self.resizing_item = None
            self.resize_mode = None

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
                elif isinstance(item, QGraphicsTextItem):
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
            pen = QPen(self.current_color)
            pen.setWidthF(self.pen_width)
            pen.setStyle(Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)

            if self.current_tool == "line":
                if self.current_line_type == "line":
                    self.temp_item = CustomLineItem(QLineF(self.start_point, self.start_point), pen)
                elif self.current_line_type == "arrow":
                    self.temp_item = ArrowItem(QLineF(self.start_point, self.start_point), pen)
                elif self.current_line_type == "freehand":
                    self.current_path = QPainterPath(self.start_point)
                    self.temp_item = CustomPathItem(self.current_path, pen)
                self.addItem(self.temp_item)
            elif self.current_tool == "shape":
                if self.current_shape_type == "rect":
                    self.temp_item = CustomRectItem(QRectF(self.start_point, self.start_point), pen)
                elif self.current_shape_type == "ellipse":
                    self.temp_item = CustomEllipseItem(QRectF(self.start_point, self.start_point), pen)
                elif self.current_shape_type == "triangle":
                    self.temp_item = CustomPolygonItem(QPolygonF([self.start_point, self.start_point, self.start_point]), pen)
                self.addItem(self.temp_item)
            elif self.current_tool == "text":
                text, ok = QInputDialog.getMultiLineText(None, "テキスト入力", "文字を入力してください:")
                if ok and text:
                    font = QFont("Arial")
                    font.setPointSizeF(max(6.0, self.pen_width * 3.0))
                    text_item = self.addText(text, font)
                    text_item.setDefaultTextColor(self.current_color)
                    text_item.setPos(self.start_point)
                    text_item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
                    self.has_unsaved_changes = True
                self.start_point = None
                self.temp_item = None

    def mouseMoveEvent(self, event):
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
                    elif isinstance(item, QGraphicsTextItem):
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
                self.update() 
                event.accept()
                return
            
            is_moving = False
            if event.buttons() == Qt.MouseButton.LeftButton:
                for item in self.selectedItems():
                    if item != self.bg_item:
                        self.has_unsaved_changes = True
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            deleted = False
            for item in self.selectedItems():
                if item != self.bg_item:
                    self.removeItem(item)
                    deleted = True
            if deleted:
                self.has_unsaved_changes = True
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
        copy_action = menu.addAction("コピー")
        copy_action.setEnabled(target_item is not None)
        
        paste_action = menu.addAction("貼り付け")
        paste_action.setEnabled(self.copied_data is not None)

        edit_text_action = None
        if isinstance(target_item, QGraphicsTextItem):
            menu.addSeparator()
            edit_text_action = menu.addAction("テキストを編集")

        action = menu.exec(event.screenPos())

        if action == copy_action:
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
            self.copied_data = {'type': 'rect', 'rect': item.rect(), 'pen': QPen(item.pen())}
        elif isinstance(item, CustomEllipseItem):
            self.copied_data = {'type': 'ellipse', 'rect': item.rect(), 'pen': QPen(item.pen())}
        elif isinstance(item, CustomPolygonItem):
            self.copied_data = {'type': 'polygon', 'polygon': item.polygon(), 'pen': QPen(item.pen())}
        elif isinstance(item, CustomPathItem):
            self.copied_data = {'type': 'path', 'path': QPainterPath(item.path()), 'pen': QPen(item.pen())}
        elif isinstance(item, QGraphicsTextItem):
            self.copied_data = {
                'type': 'text', 'text': item.toPlainText(),
                'font': QFont(item.font()), 'color': QColor(item.defaultTextColor()),
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

        elif item_type in ['polygon']:
            old_poly = data['polygon']
            br = old_poly.boundingRect()
            dx_poly = pos.x() - br.left()
            dy_poly = pos.y() - br.top()
            new_poly = old_poly.translated(dx_poly, dy_poly)
            new_pen = QPen(data['pen'])
            new_item = CustomPolygonItem(new_poly, new_pen)
            
        elif item_type == 'path':
            old_path = data['path']
            br = old_path.boundingRect()
            dx_path = pos.x() - br.left()
            dy_path = pos.y() - br.top()
            new_path = old_path.translated(dx_path, dy_path)
            new_pen = QPen(data['pen'])
            new_item = CustomPathItem(new_path, new_pen)

        elif item_type == 'text':
            new_item = self.addText(data['text'], QFont(data['font']))
            new_item.setDefaultTextColor(QColor(data['color']))
            new_item.setPos(pos)
            new_item.setScale(data['scale'])
            new_item.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable | QGraphicsItem.GraphicsItemFlag.ItemIsMovable)

        if new_item:
            if item_type != 'text':
                self.addItem(new_item)
            new_item.setSelected(True)
            self.has_unsaved_changes = True

    def edit_text_item(self, item):
        if isinstance(item, QGraphicsTextItem):
            current_text = item.toPlainText()
            new_text, ok = QInputDialog.getMultiLineText(None, "テキストの編集", "文字を変更してください:", current_text)
            if ok and new_text and new_text != current_text:
                item.setPlainText(new_text)
                self.has_unsaved_changes = True


class AdvancedAnnotationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Annotation Tool")
        self.setGeometry(100, 100, 1200, 800)

        self.scene = AnnotationScene(self)
        self.scene.selectionChanged.connect(self.sync_properties_from_selection)

        self.view = QGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.view.setMouseTracking(True)
        self.setCentralWidget(self.view)

        self.current_pdf_doc = None
        self.current_pdf_page = 0
        self.current_filename = "" 
        self.current_dir = "" 
        self.current_ext = "" 

        self.init_toolbar()

    def init_toolbar(self):
        toolbar = QToolBar("Main Toolbar")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        # 1. ファイル操作
        open_action = QAction("📂 開く", self)
        open_action.triggered.connect(self.open_file)
        toolbar.addAction(open_action)

        save_action = QAction("💾 保存", self)
        save_action.triggered.connect(self.save_file)
        toolbar.addAction(save_action)

        toolbar.addSeparator()

        self.tool_actions = {}
        act_sel = QAction("↖️ 選択/移動", self)
        act_sel.setCheckable(True)
        act_sel.triggered.connect(lambda checked: self.set_tool("select"))
        toolbar.addAction(act_sel)
        self.tool_actions["select"] = act_sel

        toolbar.addSeparator()

        act_line = QAction("📏 線", self)
        act_line.setCheckable(True)
        act_line.triggered.connect(lambda checked: self.set_tool("line"))
        toolbar.addAction(act_line)
        self.tool_actions["line"] = act_line

        self.line_combo = QComboBox(self)
        self.line_combo.addItems(["直線", "矢印", "曲線(フリーハンド)"])
        self.line_combo.currentIndexChanged.connect(self.change_line_type)
        toolbar.addWidget(self.line_combo)

        act_shape = QAction("🔲 図形", self)
        act_shape.setCheckable(True)
        act_shape.triggered.connect(lambda checked: self.set_tool("shape"))
        toolbar.addAction(act_shape)
        self.tool_actions["shape"] = act_shape

        self.shape_combo = QComboBox(self)
        self.shape_combo.addItems(["四角", "丸/楕円", "三角"])
        self.shape_combo.currentIndexChanged.connect(self.change_shape_type)
        toolbar.addWidget(self.shape_combo)

        act_text = QAction("🔤 文字", self)
        act_text.setCheckable(True)
        act_text.triggered.connect(lambda checked: self.set_tool("text"))
        toolbar.addAction(act_text)
        self.tool_actions["text"] = act_text

        self.tool_actions["select"].setChecked(True)
        toolbar.addSeparator()

        color_action = QAction("🎨 色変更", self)
        color_action.triggered.connect(self.choose_color)
        toolbar.addAction(color_action)

        toolbar.addWidget(QLabel("  🖊️ 太さ: "))
        self.width_combo = QComboBox(self)
        self.width_combo.setEditable(True) 
        width_options = ["0.5", "1.0", "1.5", "2.0", "3.0", "4.0", "5.0", "6.0", "8.0", "10.0", "12.0", "15.0", "20.0", "30.0", "50.0"]
        self.width_combo.addItems(width_options)
        self.width_combo.setCurrentText(str(float(self.scene.pen_width)))
        self.width_combo.currentTextChanged.connect(self.change_pen_width_text)
        toolbar.addWidget(self.width_combo)

        toolbar.addSeparator()

        zoom_out_action = QAction("🔍- 縮小", self)
        zoom_out_action.triggered.connect(self.zoom_out)
        toolbar.addAction(zoom_out_action)

        zoom_in_action = QAction("🔍+ 拡大", self)
        zoom_in_action.triggered.connect(self.zoom_in)
        toolbar.addAction(zoom_in_action)

        zoom_reset_action = QAction("🔍 100%", self)
        zoom_reset_action.triggered.connect(self.zoom_reset)
        toolbar.addAction(zoom_reset_action)

        zoom_fit_action = QAction("🖥️ 画面に合わせる", self)
        zoom_fit_action.triggered.connect(self.fit_to_view)
        toolbar.addAction(zoom_fit_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.prev_page_action = QAction("◀ 前ページ", self)
        self.prev_page_action.triggered.connect(lambda: self.change_page(-1))
        self.prev_page_action.setEnabled(False)
        toolbar.addAction(self.prev_page_action)

        self.next_page_action = QAction("次ページ ▶", self)
        self.next_page_action.triggered.connect(lambda: self.change_page(1))
        self.next_page_action.setEnabled(False)
        toolbar.addAction(self.next_page_action)

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

        if isinstance(item, (QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem, CustomPathItem)):
            pen = item.pen()
            self.scene.current_color = pen.color()
            self.scene.pen_width = max(0.5, pen.widthF())
            self.width_combo.setCurrentText(str(self.scene.pen_width))
            
        elif isinstance(item, QGraphicsTextItem):
            self.scene.current_color = item.defaultTextColor()
            font = item.font()
            w = max(0.5, font.pointSizeF() / 3.0)
            self.scene.pen_width = w
            self.width_combo.setCurrentText(str(w))

        self.width_combo.blockSignals(False)

    def set_tool(self, tool_id):
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

    def choose_color(self):
        color = QColorDialog.getColor(self.scene.current_color, self)
        if color.isValid():
            self.scene.current_color = color
            changed = False
            for item in self.scene.selectedItems():
                if isinstance(item, (QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem, CustomPathItem)):
                    pen = item.pen()
                    pen.setColor(color)
                    item.setPen(pen)
                    changed = True
                elif isinstance(item, QGraphicsTextItem):
                    item.setDefaultTextColor(color)
                    changed = True
            if changed:
                self.scene.has_unsaved_changes = True

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
            if isinstance(item, (QGraphicsLineItem, QGraphicsRectItem, QGraphicsEllipseItem, QGraphicsPolygonItem, CustomPathItem)):
                pen = item.pen()
                pen.setWidthF(value)
                item.setPen(pen)
                changed = True
            elif isinstance(item, QGraphicsTextItem):
                font = item.font()
                font.setPointSizeF(max(6.0, value * 3.0))
                item.setFont(font)
                changed = True
        if changed:
            self.scene.has_unsaved_changes = True

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
        self.setWindowTitle(f"Advanced Annotation Tool - Page {self.current_pdf_page + 1}/{len(self.current_pdf_doc)}")
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
        # 元の拡張子に基づいたデフォルト設定（PDFの場合はJPEG）
        is_pdf = self.current_ext == ".pdf"
        default_ext = ".jpg" if is_pdf else self.current_ext
        if not default_ext: default_ext = ".jpg"
        
        initial_name = f"{self.current_filename}_After{default_ext}"
        initial_path = os.path.join(self.current_dir, initial_name) if self.current_dir else initial_name
        
        # フィルター文字列の作成（元の形式をデフォルト選択に）
        if default_ext == ".png":
            filter_str = "PNG Image (*.png);;JPEG Image (*.jpg)"
        elif default_ext in [".pdf"]:
             filter_str = "PDF Document (*.pdf);;JPEG Image (*.jpg);;PNG Image (*.png)"
        else:
            filter_str = "JPEG Image (*.jpg);;PNG Image (*.png)"
        
        file_path, selected_filter = QFileDialog.getSaveFileName(
            self, "保存", initial_path, filter_str
        )
        if not file_path:
            return

        save_ext = os.path.splitext(file_path)[1].lower()

        # PDF保存ロジック（画像化してPDFに変換）
        if save_ext == ".pdf":
            self.scene.clearSelection()
            rect = self.scene.sceneRect()
            image = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            self.scene.render(painter)
            painter.end()
            
            # 一時ファイルを経由してPDF化
            temp_img = "temp_save.jpg"
            image.save(temp_img, "JPEG", 95)
            doc = fitz.open()
            imgdoc = fitz.open(temp_img)
            pdfbytes = imgdoc.convert_to_pdf()
            imgdoc.close()
            doc.insert_pdf(fitz.open("pdf", pdfbytes))
            doc.save(file_path)
            doc.close()
            if os.path.exists(temp_img): os.remove(temp_img)
            
            self.scene.has_unsaved_changes = False
            self.show_auto_close_message("完了", "PDFとして保存しました。")
            return

        # 画像保存ロジック
        self.scene.clearSelection()
        rect = self.scene.sceneRect()
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
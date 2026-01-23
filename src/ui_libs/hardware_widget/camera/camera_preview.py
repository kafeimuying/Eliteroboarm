"""
相机预览组件
"""

import time
import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QPoint, QEvent
from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QPixmap, QImage
from core.managers.log_manager import warning, error
from .camera_info import CameraInfo
from core.middleware.event_bus import get_hardware_event_bus
from core.middleware.types_dto import CameraFrameInfo


class CameraPreviewThread(QThread):
    """相机预览线程"""
    frame_captured = pyqtSignal(object)  # CameraInfo

    def __init__(self, camera_info: CameraInfo):
        super().__init__()
        self.camera_info = camera_info
        self.running = False
        self.fps = camera_info.config.get('fps', 30)

    def run(self):
        self.running = True

        # 如果相机已连接且有驱动，使用实际相机
        if self.camera_info.connected and self.camera_info.camera_driver:
            while self.running:
                try:
                    # 从实际相机捕获帧
                    frame = self.camera_info.camera_driver.capture_image()
                    if frame is not None:
                        # 更新相机的帧信息
                        self.camera_info.current_frame = frame
                        self.camera_info.last_frame_time = time.time()
                        self.camera_info.frame_count = self.camera_info.frame_count + 1 if hasattr(self.camera_info, 'frame_count') else 1

                        # 发送帧信号
                        self.frame_captured.emit(self.camera_info)

                        # 发布帧捕获事件到事件总线
                        frame_info = CameraFrameInfo(
                            camera_id=self.camera_info.camera_id,
                            name=self.camera_info.name,
                            frame_count=self.camera_info.frame_count,
                            width=frame.shape[1] if len(frame.shape) > 1 else 0,
                            height=frame.shape[0] if len(frame.shape) > 0 else 0,
                            channels=frame.shape[2] if len(frame.shape) > 2 else 1,
                            timestamp=time.time(),
                            is_simulation=False
                        )
                        get_hardware_event_bus().publish_camera_frame("camera_preview", frame_info)
                    else:
                        warning(f"Failed to capture frame from {self.camera_info.name}", "CAMERA_UI")

                    # 控制帧率
                    self.msleep(int(1000 / self.fps))

                except Exception as e:
                    error(f"Camera preview error: {e}", "CAMERA_UI")
                    break
        else:
            # 如果相机未连接，显示占位图像
            while self.running:
                try:
                    # 创建占位图像
                    height, width = 480, 640
                    frame = np.zeros((height, width, 3), dtype=np.uint8)

                    # 添加提示文字
                    cv2.putText(
                        frame, f"Camera: {self.camera_info.name}",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2
                    )
                    cv2.putText(
                        frame, "Not Connected",
                        (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1
                    )
                    cv2.putText(
                        frame, time.strftime("%H:%M:%S"),
                        (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1
                    )

                    # 添加相机类型标识
                    if self.camera_info.camera_id == "主相机":
                        cv2.rectangle(frame, (50, 100), (200, 300), (0, 255, 0), 2)
                        cv2.putText(frame, "Main Camera", (60, 130), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
                    elif self.camera_info.camera_id == "辅助相机":
                        cv2.circle(frame, (320, 240), 50, (255, 0, 0), 2)
                        cv2.putText(frame, "Aux Camera", (270, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)
                    elif "侧视" in self.camera_info.camera_id:
                        cv2.line(frame, (50, 100), (590, 380), (255, 255, 0), 2)
                        cv2.putText(frame, "Side View", (250, 240), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 1)

                    self.camera_info.current_frame = frame
                    self.frame_captured.emit(self.camera_info)

                    # 发布模拟帧捕获事件到事件总线
                    frame_info = CameraFrameInfo(
                        camera_id=self.camera_info.camera_id,
                        name=self.camera_info.name,
                        frame_count=self.camera_info.frame_count if hasattr(self.camera_info, 'frame_count') else 1,
                        width=frame.shape[1] if len(frame.shape) > 1 else 0,
                        height=frame.shape[0] if len(frame.shape) > 0 else 0,
                        channels=frame.shape[2] if len(frame.shape) > 2 else 1,
                        timestamp=time.time(),
                        is_simulation=True
                    )
                    get_hardware_event_bus().publish_camera_frame("camera_preview_simulation", frame_info)

                    # 控制帧率
                    self.msleep(int(1000 / self.fps))

                except Exception as e:
                    error(f"Preview placeholder error: {e}", "CAMERA_UI")
                    break

    def stop(self):
        self.running = False
        self.wait(1000)

    def msleep(self, ms):
        time.sleep(ms / 1000.0)


class PreviewLabel(QLabel):
    """相机预览标签"""

    # 自定义信号
    mouse_moved = pyqtSignal(int, int)  # x, y坐标
    mouse_hover = pyqtSignal(int, int, str)  # hover时的坐标和RGB信息（用于状态栏更新）

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(640, 480)
        self.setStyleSheet("border: 2px solid #ccc; background-color: #f0f0f0;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)  # 居中对齐
        self.setText("等待相机连接...")
        self.movie = None
        self.camera_info = None  # 存储相机信息

        # 十字线和坐标显示
        self.show_crosshair = True
        self.mouse_position = QPoint()
        self.current_frame = None

        # 启用鼠标跟踪以支持hover功能
        self.setMouseTracking(True)

        # 添加销毁标志以防止在对象删除后继续更新
        self._is_destroyed = False

        # 安装事件过滤器来捕获对象删除事件
        self.installEventFilter(self)

    def closeEvent(self, event):
        """窗口关闭事件"""
        self._is_destroyed = True
        super().closeEvent(event)

    def cleanup(self):
        """清理资源"""
        self._is_destroyed = True
        self.camera_info = None
        self.current_frame = None

    def deleteLater(self):
        """重写deleteLater以确保正确的清理"""
        self.cleanup()
        super().deleteLater()

    def eventFilter(self, obj, event):
        """事件过滤器 - 捕获对象销毁事件"""
        if event.type() == QEvent.Type.DeferredDelete and obj == self:
            self.cleanup()
        return super().eventFilter(obj, event)

    def update_frame(self, camera_info):
        """更新预览帧"""
        # 检查对象是否已被销毁
        if self._is_destroyed:
            return

        # 额外检查：确保Qt对象仍然有效
        try:
            # 尝试访问一个基本属性来检查对象是否仍然有效
            _ = self.isEnabled()
        except RuntimeError:
            # C++对象已被删除
            self._is_destroyed = True
            return

        try:
            if camera_info.current_frame is not None:
                # 将numpy数组转换为QPixmap
                import numpy as np

                frame = camera_info.current_frame
                if isinstance(frame, np.ndarray):
                    height, width, channel = frame.shape
                    bytes_per_line = 3 * width
                    q_image = QImage(frame.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
                    pixmap = QPixmap.fromImage(q_image)

                    # 缩放图像以适应标签大小
                    scaled_pixmap = pixmap.scaled(self.size(), 1)  # 1 = Qt.KeepAspectRatio

                    self.setPixmap(scaled_pixmap)
                else:
                    self.setText("无法显示帧数据")
        except Exception as e:
            error(f"Failed to update preview frame: {e}", "CAMERA_UI")
            self.setText(f"预览错误: {str(e)}")

    def set_camera_info(self, camera_info):
        """设置相机信息"""
        self.camera_info = camera_info

    def get_camera_info(self):
        """获取相机信息"""
        return self.camera_info

    def mouseMoveEvent(self, event):
        """鼠标移动事件 - hover即可显示坐标和十字线"""
        # 检查对象是否已被销毁
        if self._is_destroyed:
            super().mouseMoveEvent(event)
            return

        if self.camera_info and self.camera_info.current_frame is not None and self.pixmap():
            self.mouse_position = event.pos()

            # 使用与paintEvent相同的坐标计算逻辑
            x = int(event.position().x())
            y = int(event.position().y())

            # 获取图像在标签中的实际显示区域（考虑居中对齐）
            pixmap_rect = self.pixmap().rect()
            label_rect = self.rect()

            # 防止除零错误
            if pixmap_rect.width() == 0 or pixmap_rect.height() == 0:
                self.mouse_hover.emit(-1, -1, "")
                super().mouseMoveEvent(event)
                return

            # 计算缩放后的图像大小（保持宽高比）
            scaled_width = label_rect.width()
            scaled_height = int(pixmap_rect.height() * scaled_width / pixmap_rect.width())

            if scaled_height > label_rect.height():
                # 如果高度超出，按高度缩放
                scaled_height = label_rect.height()
                scaled_width = int(pixmap_rect.width() * scaled_height / pixmap_rect.height())

            # 计算图像在标签中的偏移（居中对齐）
            offset_x = (label_rect.width() - scaled_width) // 2
            offset_y = (label_rect.height() - scaled_height) // 2

            # 计算在原始图像中的坐标
            frame_height, frame_width = self.camera_info.current_frame.shape[:2]

            # 检查鼠标是否在图像区域内
            if offset_x <= x < offset_x + scaled_width and offset_y <= y < offset_y + scaled_height:
                # 计算相对于缩放图像的坐标
                rel_x = x - offset_x
                rel_y = y - offset_y

                # 等比例缩放回原始图像坐标
                img_x = int(rel_x * frame_width / scaled_width)
                img_y = int(rel_y * frame_height / scaled_height)

                # 确保坐标在图像范围内
                img_x = max(0, min(img_x, frame_width - 1))
                img_y = max(0, min(img_y, frame_height - 1))

                # 获取RGB值
                frame = self.camera_info.current_frame
                if 0 <= img_y < frame.shape[0] and 0 <= img_x < frame.shape[1]:
                    b, g, r = frame[img_y, img_x]  # OpenCV是BGR格式
                    rgb_info = f"RGB({r}, {g}, {b})"
                else:
                    rgb_info = "RGB(-, -, -)"

                # 发送信号
                self.mouse_moved.emit(img_x, img_y)
                self.mouse_hover.emit(img_x, img_y, rgb_info)
            else:
                # 鼠标不在图像区域内，发送无效坐标
                self.mouse_hover.emit(-1, -1, "")

            # 更新显示（绘制十字线）
            self.update()
        else:
            # 没有图像时，发送无效坐标
            self.mouse_hover.emit(-1, -1, "")

        super().mouseMoveEvent(event)

    def mousePressEvent(self, event):
        """鼠标点击事件"""
        # 检查对象是否已被销毁
        if self._is_destroyed:
            super().mousePressEvent(event)
            return

        if self.camera_info and self.camera_info.current_frame is not None:
            self.mouse_position = event.pos()
            self.update()

        super().mousePressEvent(event)

    def paintEvent(self, event):
        """重绘事件 - 绘制十字线"""
        # 检查对象是否已被销毁，防止在对象删除后继续绘制
        if self._is_destroyed:
            return

        try:
            # 额外检查：确保Qt对象仍然有效
            _ = self.isEnabled()

            super().paintEvent(event)

            if self.show_crosshair and self.camera_info and self.camera_info.current_frame is not None:
                from PyQt6.QtGui import QPainter, QPen, QColor
                from PyQt6.QtCore import Qt

                painter = QPainter(self)

                # 设置淡灰色虚线十字线
                pen = QPen(QColor(200, 200, 200), 1)  # 淡灰色
                pen.setStyle(Qt.PenStyle.DashLine)  # 虚线
                painter.setPen(pen)

            # 获取当前鼠标位置
                if self.mouse_position:
                    # 绘制十字线
                    x = int(self.mouse_position.x())
                    y = int(self.mouse_position.y())

                    # 水平线
                    painter.drawLine(0, y, self.width(), y)
                    # 垂直线
                    painter.drawLine(x, 0, x, self.height())

                    # 显示坐标信息
                    if self.pixmap():
                        # 获取图像在标签中的实际显示区域（考虑居中对齐）
                        pixmap_rect = self.pixmap().rect()
                        label_rect = self.rect()

                        # 防止除零错误
                        if pixmap_rect.width() == 0 or pixmap_rect.height() == 0:
                            return

                        # 计算缩放后的图像大小（保持宽高比）
                        scaled_width = label_rect.width()
                        scaled_height = int(pixmap_rect.height() * scaled_width / pixmap_rect.width())

                        if scaled_height > label_rect.height():
                            # 如果高度超出，按高度缩放
                            scaled_height = label_rect.height()
                            scaled_width = int(pixmap_rect.width() * scaled_height / pixmap_rect.height())

                        # 计算图像在标签中的偏移（居中对齐）
                        offset_x = (label_rect.width() - scaled_width) // 2
                        offset_y = (label_rect.height() - scaled_height) // 2

                        # 计算在原始图像中的坐标
                        frame_height, frame_width = self.camera_info.current_frame.shape[:2]

                        # 检查鼠标是否在图像区域内
                        if offset_x <= x < offset_x + scaled_width and offset_y <= y < offset_y + scaled_height:
                            # 计算相对于缩放图像的坐标
                            rel_x = x - offset_x
                            rel_y = y - offset_y

                            # 等比例缩放回原始图像坐标
                            img_x = int(rel_x * frame_width / scaled_width)
                            img_y = int(rel_y * frame_height / scaled_height)

                            # 确保坐标在图像范围内
                            img_x = max(0, min(img_x, frame_width - 1))
                            img_y = max(0, min(img_y, frame_height - 1))

                            # 获取RGB值
                            frame = self.camera_info.current_frame
                            if 0 <= img_y < frame.shape[0] and 0 <= img_x < frame.shape[1]:
                                b, g, r = frame[img_y, img_x]  # OpenCV是BGR格式
                                rgb_text = f"RGB({r}, {g}, {b})"
                            else:
                                rgb_text = "RGB(-, -, -)"

                            # 绘制坐标和RGB文本背景（使用小字体）
                            coord_text = f"({img_x}, {img_y})"
                            painter.setPen(QPen(QColor(0, 0, 0), 1))

                            # 计算文本背景大小（考虑两行文本）
                            coord_width = len(coord_text) * 6 + 10
                            rgb_width = len(rgb_text) * 6 + 10
                            max_width = max(coord_width, rgb_width)
                            painter.fillRect(x + 5, y - 45, max_width, 35, QColor(0, 0, 0, 180))

                            # 设置小字体
                            try:
                                from PyQt6.QtGui import QFont
                                font = QFont("Arial", 8)
                                painter.setFont(font)
                            except:
                                pass

                            # 绘制坐标文本（小字体）
                            painter.setPen(QPen(QColor(255, 255, 255), 1))
                            painter.drawText(x + 10, y - 30, coord_text)

                            # 绘制RGB文本（小字体）
                            painter.setPen(QPen(QColor(200, 200, 200), 1))
                            painter.drawText(x + 10, y - 18, rgb_text)

        except Exception as e:
            # 捕获绘制过程中的任何异常，防止C++对象已被删除时的崩溃
            from core.managers.log_manager import error
            error(f"PaintEvent error: {e}", "CAMERA_UI")

    def clear_preview(self):
        """清除预览"""
        self.cleanup()  # 调用cleanup方法设置销毁标志
        self.clear()
        self.setText("等待相机连接...")
        self.mouse_position = QPoint()
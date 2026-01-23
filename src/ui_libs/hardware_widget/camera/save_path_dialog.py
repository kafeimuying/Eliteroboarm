from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QDialogButtonBox, QMessageBox, QFormLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import time

class SavePathDialog(QDialog):
    """保存路径对话框"""

    def __init__(self, default_name: str = "", parent=None):
        super().__init__(parent)
        self.default_name = default_name
        self.name_edit = None
        self.desc_edit = None

        # 简化初始化，直接设置UI
        self.setWindowTitle("保存路径")
        self.setMinimumWidth(400)
        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout()

        # 路径名称输入
        name_layout = QFormLayout()
        self.name_edit = QLineEdit(self.default_name)
        name_layout.addRow("路径名称:", self.name_edit)
        layout.addLayout(name_layout)

        # 路径描述
        desc_layout = QFormLayout()
        self.desc_edit = QLineEdit()
        desc_layout.addRow("描述:", self.desc_edit)
        layout.addLayout(desc_layout)

        # 按钮
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def is_valid(self):
        """检查对话框是否有效"""
        return self.name_edit is not None and self.desc_edit is not None

    def get_path_info(self):
        """获取路径信息"""
        if not self.is_valid():
            return {
                'name': self.default_name or f"路径_{int(time.time())}",
                'description': ""
            }
        return {
            'name': self.name_edit.text() or f"路径_{int(time.time())}",
            'description': self.desc_edit.text()
        }



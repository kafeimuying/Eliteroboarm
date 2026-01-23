#!/usr/bin/env python3
"""
保存组合算法对话框 - 支持完整的metadata编辑
"""

from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
                            QLineEdit, QTextEdit, QLabel, QPushButton, QMessageBox,
                            QGroupBox, QSpinBox, QComboBox)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from typing import Dict, Any, Optional, List
from core.managers.log_manager import info, debug, warning, error


class SaveCombinedAlgorithmDialog(QDialog):
    """保存组合算法对话框"""
    
    # 信号：当需要保存组合算法时发出
    save_requested = pyqtSignal(str, dict)  # algorithm_id, metadata
    
    def __init__(self, parent=None, execution_order: List = None, existing_ids: List[str] = None):
        super().__init__(parent)
        self.execution_order = execution_order or []
        self.existing_ids = existing_ids or []
        self.setWindowTitle("保存组合算法")
        self.setModal(True)
        self.resize(500, 600)
        
        self.setup_ui()
        self.populate_suggestions()
    
    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)
        
        # 标题
        title_label = QLabel("保存组合算法")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # 基本信息
        basic_group = QGroupBox("基本信息")
        basic_layout = QFormLayout(basic_group)
        
        # 算法ID
        self.algorithm_id_edit = QLineEdit()
        self.algorithm_id_edit.setPlaceholderText("例如: my_combined_algorithm")
        basic_layout.addRow("算法ID *:", self.algorithm_id_edit)
        
        # 显示名称
        self.display_name_edit = QLineEdit()
        self.display_name_edit.setPlaceholderText("例如: 我的组合算法")
        basic_layout.addRow("显示名称 *:", self.display_name_edit)
        
        # 二级分类（secondary_category）
        self.custom_category_combo = QComboBox()
        self.custom_category_combo.addItems([
            "预处理组合",
            "检测组合",
            "分析组合",
            "分割组合",
            "自定义组合",
            "未分类"
        ])
        self.custom_category_combo.setEditable(True)
        basic_layout.addRow("二级分类 *:", self.custom_category_combo)
        
        # 版本
        self.version_edit = QLineEdit("1.0.0")
        basic_layout.addRow("版本:", self.version_edit)
        
        # 作者
        self.author_edit = QLineEdit("User")
        basic_layout.addRow("作者:", self.author_edit)
        
        layout.addWidget(basic_group)
        
        # 描述信息
        desc_group = QGroupBox("描述信息")
        desc_layout = QVBoxLayout(desc_group)
        
        self.description_edit = QTextEdit()
        self.description_edit.setPlaceholderText("请输入组合算法的详细描述...")
        self.description_edit.setMaximumHeight(100)
        desc_layout.addWidget(QLabel("描述:"))
        desc_layout.addWidget(self.description_edit)
        
        layout.addWidget(desc_group)
        
        # 标签
        tags_group = QGroupBox("标签")
        tags_layout = QVBoxLayout(tags_group)
        
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText("例如: 组合, 预处理, 边缘检测 (用逗号分隔)")
        tags_layout.addWidget(QLabel("标签:"))
        tags_layout.addWidget(self.tags_edit)
        
        layout.addWidget(tags_group)
        
        # 算法链信息预览
        if self.execution_order:
            preview_group = QGroupBox("算法链预览")
            preview_layout = QVBoxLayout(preview_group)
            
            algo_count = len(self.execution_order)
            preview_label = QLabel(f"包含 {algo_count} 个算法:")
            preview_layout.addWidget(preview_label)
            
            algo_list = []
            for i, node in enumerate(self.execution_order):
                algo_name = node.algorithm.get_algorithm_info().display_name
                algo_list.append(f"{i+1}. {algo_name}")
            
            algo_text = "\n".join(algo_list)
            algo_preview = QLabel(algo_text)
            algo_preview.setStyleSheet("QLabel { background-color: #f5f5f5; padding: 10px; border: 1px solid #ccc; }")
            preview_layout.addWidget(algo_preview)
            
            layout.addWidget(preview_group)
        
        # 按钮
        button_layout = QHBoxLayout()
        
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_btn)
        
        button_layout.addStretch()
        
        self.save_btn = QPushButton("保存组合算法")
        self.save_btn.clicked.connect(self.save_combined_algorithm)
        self.save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        """)
        button_layout.addWidget(self.save_btn)
        
        layout.addLayout(button_layout)
        
        # 连接信号
        self.display_name_edit.textChanged.connect(self.on_display_name_changed)
        self.algorithm_id_edit.textChanged.connect(self.on_algorithm_id_changed)
    
    def populate_suggestions(self):
        """根据执行顺序自动填充建议信息"""
        if not self.execution_order:
            return
        
        algo_count = len(self.execution_order)
        
        # 生成默认的显示名称
        if algo_count == 1:
            default_name = self.execution_order[0].algorithm.get_algorithm_info().display_name + "组合"
        elif algo_count == 2:
            names = [node.algorithm.get_algorithm_info().display_name for node in self.execution_order[:2]]
            default_name = f"{names[0]}+{names[1]}组合"
        else:
            first_names = [node.algorithm.get_algorithm_info().display_name for node in self.execution_order[:2]]
            default_name = f"{first_names[0]}+{first_names[1]}等{algo_count}个算法组合"
        
        if not self.display_name_edit.text():
            self.display_name_edit.setText(default_name)
        
        # 生成默认的算法ID
        if not self.algorithm_id_edit.text():
            # 基于显示名称生成ID
            suggested_id = default_name.replace(" ", "_").replace("+", "_and_").replace("等", "_and_").lower()
            # 移除特殊字符
            import re
            suggested_id = re.sub(r'[^\w_]', '', suggested_id)
            self.algorithm_id_edit.setText(suggested_id)
        
        # 生成默认描述
        if not self.description_edit.toPlainText():
            if algo_count == 1:
                desc = f"基于 {self.execution_order[0].algorithm.get_algorithm_info().display_name} 的组合算法"
            else:
                names = [node.algorithm.get_algorithm_info().display_name for node in self.execution_order[:3]]
                if algo_count > 3:
                    desc = f"包含 {', '.join(names)} 等 {algo_count} 个算法的组合链"
                else:
                    desc = f"包含 {', '.join(names)} 的组合算法"
            self.description_edit.setText(desc)
        
        # 生成默认标签
        if not self.tags_edit.text():
            default_tags = ["组合", "链式"]
            if algo_count <= 3:
                # 根据算法类型添加标签
                for node in self.execution_order:
                    info = node.algorithm.get_algorithm_info()
                    if "预处理" in info.category:
                        default_tags.append("预处理")
                    elif "检测" in info.category:
                        default_tags.append("检测")
                    elif "分析" in info.category:
                        default_tags.append("分析")
            
            # 去重并限制数量
            unique_tags = list(dict.fromkeys(default_tags))[:5]  # 最多5个标签
            self.tags_edit.setText(", ".join(unique_tags))
    
    def on_display_name_changed(self, text: str):
        """当显示名称改变时，仅在算法ID为空或未手动修改时自动更新"""
        current_id = self.algorithm_id_edit.text().strip()
        # 只有在算法ID为空时才自动更新，避免覆盖用户手动输入的ID
        if text and not current_id:
            suggested_id = self.generate_algorithm_id_from_name(text)
            self.algorithm_id_edit.setText(suggested_id)
            self.algorithm_id_edit.setModified(False)  # 标记为自动生成的
    
    def generate_algorithm_id_from_name(self, display_name: str) -> str:
        """根据显示名称生成符合规范的算法ID"""
        # 基于显示名称生成ID
        suggested_id = display_name.replace(" ", "_").replace("+", "_and_").replace("等", "_and_").lower()
        # 移除特殊字符
        import re
        suggested_id = re.sub(r'[^\w_]', '', suggested_id)
        
        # 确保以字母或下划线开头
        if suggested_id and suggested_id[0].isdigit():
            suggested_id = f"algo_{suggested_id}"
        
        # 确保不为空
        if not suggested_id:
            suggested_id = "combined_algorithm"
        
        # 检查去重
        return self.ensure_unique_id(suggested_id)
    
    def ensure_unique_id(self, base_id: str) -> str:
        """确保算法ID唯一，避免与现有算法冲突"""
        if base_id not in self.existing_ids:
            return base_id
        
        # 添加数字后缀去重
        counter = 1
        while f"{base_id}_{counter}" in self.existing_ids:
            counter += 1
        
        return f"{base_id}_{counter}"
    
    def on_algorithm_id_changed(self, text: str):
        """当算法ID改变时，验证其有效性"""
        import re
        if text and not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', text):
            self.algorithm_id_edit.setStyleSheet("QLineEdit { background-color: #ffebee; }")
        else:
            self.algorithm_id_edit.setStyleSheet("")
        
        # 标记为用户手动修改
        if text:
            self.algorithm_id_edit.setModified(True)
    
    def validate_input(self) -> bool:
        """验证输入信息"""
        # 检查必填字段
        if not self.algorithm_id_edit.text().strip():
            QMessageBox.warning(self, "输入错误", "请输入算法ID")
            self.algorithm_id_edit.setFocus()
            return False
        
        if not self.display_name_edit.text().strip():
            QMessageBox.warning(self, "输入错误", "请输入显示名称")
            self.display_name_edit.setFocus()
            return False
        
        # 验证算法ID格式
        import re
        algorithm_id = self.algorithm_id_edit.text().strip()
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', algorithm_id):
            QMessageBox.warning(self, "输入错误", 
                               "算法ID只能包含字母、数字和下划线，且必须以字母或下划线开头")
            self.algorithm_id_edit.setFocus()
            return False
        
        # 验证版本格式
        version = self.version_edit.text().strip()
        if not re.match(r'^\d+\.\d+\.\d+$', version):
            QMessageBox.warning(self, "输入错误", 
                               "版本号格式不正确，应为 x.y.z 格式，例如 1.0.0")
            self.version_edit.setFocus()
            return False
        
        return True
    
    def get_metadata(self) -> Dict[str, Any]:
        """获取metadata信息"""
        # 解析标签
        tags_text = self.tags_edit.text().strip()
        tags = [tag.strip() for tag in tags_text.split(",") if tag.strip()] if tags_text else []
        
        return {
            "algorithm_id": self.algorithm_id_edit.text().strip(),
            "display_name": self.display_name_edit.text().strip(),
            "category": "组合算法",  # 一级分类固定为"组合算法"
            "secondary_category": self.custom_category_combo.currentText().strip(),  # 二级分类由用户选择
            "description": self.description_edit.toPlainText().strip(),
            "version": self.version_edit.text().strip(),
            "author": self.author_edit.text().strip(),
            "tags": tags
        }
    
    def save_combined_algorithm(self):
        """保存组合算法"""
        if not self.validate_input():
            return
        
        metadata = self.get_metadata()
        algorithm_id = metadata["algorithm_id"]
        
        # 发出保存信号
        self.save_requested.emit(algorithm_id, metadata)
        
        # 关闭对话框并设置结果为Accepted
        self.accept()


# 使用示例
if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    dialog = SaveCombinedAlgorithmDialog()
    
    def on_save_requested(algorithm_id, metadata):
        info(f"保存请求: {algorithm_id}", "SAVE_DIALOG")
        info(f"Metadata: {metadata}", "SAVE_DIALOG")
        QMessageBox.information(None, "成功", f"组合算法 {algorithm_id} 的保存请求已发出")
    
    dialog.save_requested.connect(on_save_requested)
    dialog.show()
    
    sys.exit(app.exec())
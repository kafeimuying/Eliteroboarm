#!/usr/bin/env python3
"""
算法面板组件 - 支持拖拽功能
"""

from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from typing import Dict, List, Optional

from core.managers.algorithm_registry import AlgorithmRegistry


class AlgorithmItem(QTreeWidgetItem):
    """算法项"""
    
    def __init__(self, algorithm_id: str, algorithm_info, parent=None):
        super().__init__(parent)
        self.algorithm_id = algorithm_id
        self.algorithm_info = algorithm_info
        
        # 设置显示文本
        self.setText(0, algorithm_info.display_name)
        self.setToolTip(0, f"{algorithm_info.description}\n版本: {algorithm_info.version}")
        
        # 设置图标（可以后续添加）
        if hasattr(algorithm_info, 'icon') and algorithm_info.icon:
            self.setIcon(0, QIcon(algorithm_info.icon))
        else:
            # 使用简单的默认图标，避免使用style()方法
            # 创建一个简单的颜色方块作为图标
            pixmap = QPixmap(16, 16)
            if "组合算法" in algorithm_info.category:
                pixmap.fill(QColor("#e74c3c"))  # 红色 - 组合算法特殊颜色
            elif "预处理" in algorithm_info.category:
                pixmap.fill(QColor("#3498db"))  # 蓝色
            elif "边缘检测" in algorithm_info.category:
                pixmap.fill(QColor("#f39c12"))  # 橙色
            elif "分割" in algorithm_info.category:
                pixmap.fill(QColor("#f39c12"))  # 橙色
            elif "几何检测" in algorithm_info.category:
                pixmap.fill(QColor("#2ecc71"))  # 绿色
            elif "形状检测" in algorithm_info.category:
                pixmap.fill(QColor("#9b59b6"))  # 紫色
            elif "模式匹配" in algorithm_info.category:
                pixmap.fill(QColor("#e67e22"))  # 橙红色
            elif "颜色分析" in algorithm_info.category:
                pixmap.fill(QColor("#1abc9c"))  # 青色
            else:
                pixmap.fill(QColor("#95a5a6"))  # 灰色
            self.setIcon(0, QIcon(pixmap))


class AlgorithmCategoryWidget(QWidget):
    """算法分类显示组件"""
    
    algorithm_dropped = pyqtSignal(str, QPoint)  # 转发拖拽信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry: Optional[AlgorithmRegistry] = None
        self.setup_ui()
        
    def setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # 搜索框
        search_layout = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索算法...")
        self.search_edit.textChanged.connect(self.filter_algorithms)
        search_layout.addWidget(QLabel("🔍"))
        search_layout.addWidget(self.search_edit)
        layout.addLayout(search_layout)
        
        # 分类标签页
        self.category_tabs = QTabWidget()
        self.category_tabs.setTabPosition(QTabWidget.TabPosition.West)
        layout.addWidget(self.category_tabs)
        
        # 按钮布局
        button_layout = QHBoxLayout()
        
        # 刷新按钮
        refresh_btn = QPushButton("🔄 刷新")
        refresh_btn.clicked.connect(self.refresh_algorithms)
        button_layout.addWidget(refresh_btn)
        
        # 组合算法管理按钮
        manage_btn = QPushButton("🔧 组合算法")
        manage_btn.clicked.connect(self._manage_combined_algorithms)
        button_layout.addWidget(manage_btn)
        
        layout.addLayout(button_layout)
    
    def set_registry(self, registry: AlgorithmRegistry):
        """设置算法注册表"""
        self.registry = registry
        # 连接信号
        registry.algorithm_registered.connect(self.refresh_algorithms)
        registry.algorithm_unregistered.connect(self.refresh_algorithms)
        self.refresh_algorithms()
    
    def refresh_algorithms(self):
        """刷新算法列表"""
        try:
            if not self.registry:
                from core.managers.log_manager import debug
                debug("No registry found", "ALGO_PANEL")
                return
            
            # 清空现有标签页
            self.category_tabs.clear()
            
            # 获取所有算法
            all_algorithms = self.registry.get_all_algorithms()
            
            from core.managers.log_manager import debug
            debug(f"Found {len(all_algorithms)} algorithms: {list(all_algorithms.keys())}", "ALGO_PANEL")
            
            if not all_algorithms:
                # 没有算法时显示提示
                empty_widget = QWidget()
                empty_layout = QVBoxLayout(empty_widget)
                empty_layout.addWidget(QLabel("暂无可用算法\n\n请点击工具栏上的'刷新算法'按钮加载算法"))
                self.category_tabs.addTab(empty_widget, "空")
                return
            
            # 按 category (一级目录) 和 secondary_category (二级目录) 分类
            categorized_algorithms = {}

            for algorithm_id, algorithm_info in all_algorithms.items():
                # 获取一级目录 (category)
                primary_category = getattr(algorithm_info, 'category', '未分类')
                if not primary_category:
                    primary_category = '未分类'

                # 获取二级目录 (secondary_category)
                secondary_category = getattr(algorithm_info, 'secondary_category', '未分类')
                if not secondary_category:
                    secondary_category = '未分类'
                    
                # 构建分类结构
                if primary_category not in categorized_algorithms:
                    categorized_algorithms[primary_category] = {}
                
                if secondary_category not in categorized_algorithms[primary_category]:
                    categorized_algorithms[primary_category][secondary_category] = []
                
                categorized_algorithms[primary_category][secondary_category].append((algorithm_id, algorithm_info))
            
            # 创建标签页 - 每个一级目录一个标签页
            for primary_category in sorted(categorized_algorithms.keys()):
                self._create_primary_category_tab(primary_category, categorized_algorithms[primary_category])
                    
        except Exception as e:
            from core.managers.log_manager import debug
            debug(f"Error in refresh_algorithms: {str(e)}", "ALGO_PANEL")
            import traceback
            traceback.print_exc()
            
    def _create_primary_category_tab(self, primary_category_name: str, secondary_categories: dict):
        """创建一级分类标签页，包含二级分类树"""
        primary_category_widget = QWidget()
        primary_category_layout = QVBoxLayout(primary_category_widget)
        
        # 创建树形控件用于显示二级分类
        tree = QTreeWidget()
        tree.setHeaderLabel("算法分类")
        tree.setDragEnabled(True)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        
        # 为每个二级分类创建树节点
        for secondary_category_name in sorted(secondary_categories.keys()):
            algorithms = secondary_categories[secondary_category_name]
            
            # 创建二级分类节点
            secondary_category_item = QTreeWidgetItem([secondary_category_name])
            secondary_category_item.setExpanded(True)  # 默认展开二级分类
            
            # 为该二级分类下的每个算法创建叶子节点
            for algorithm_id, algorithm_info in algorithms:
                algorithm_item = AlgorithmItem(algorithm_id, algorithm_info)
                # 将 AlgorithmItem 作为数据存储在项中
                secondary_category_item.addChild(algorithm_item)
            
            tree.addTopLevelItem(secondary_category_item)
        
        # 连接拖拽事件和右键菜单事件
        tree.startDrag = lambda supportedActions: self._start_tree_drag(tree, supportedActions)
        tree.customContextMenuRequested.connect(lambda pos: self._show_context_menu(tree, pos))
        
        primary_category_layout.addWidget(tree)
        
        # 添加分类统计信息
        total_algorithms = sum(len(algs) for algs in secondary_categories.values())
        info_label = QLabel(f"共 {total_algorithms} 个算法")
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        primary_category_layout.addWidget(info_label)
        
        self.category_tabs.addTab(primary_category_widget, primary_category_name)
        
    def _show_context_menu(self, tree: QTreeWidget, position):
        """显示右键菜单"""
        item = tree.itemAt(position)
        
        if isinstance(item, AlgorithmItem):
            # 创建右键菜单
            menu = QMenu(tree)
            
            # 添加基本信息
            info_action = menu.addAction(f"📋 算法信息")
            info_action.triggered.connect(lambda: self._show_algorithm_info(item))
            
            menu.addSeparator()
            
            # 如果是组合算法，添加删除选项
            if "组合算法" in item.algorithm_info.category:
                delete_action = menu.addAction("🗑️ 删除组合算法")
                delete_action.triggered.connect(lambda: self._delete_combined_algorithm(item))
                
                menu.addSeparator()
                
                # 添加编辑选项
                edit_action = menu.addAction("✏️ 编辑组合算法")
                edit_action.triggered.connect(lambda: self._edit_combined_algorithm(item))
            
            # 添加刷新选项
            refresh_action = menu.addAction("🔄 刷新算法库")
            refresh_action.triggered.connect(self.refresh_algorithms)
            
            # 显示菜单
            menu.exec(tree.mapToGlobal(position))
    
    def _show_algorithm_info(self, item: AlgorithmItem):
        """显示算法详细信息"""
        info = item.algorithm_info
        msg = QMessageBox()
        msg.setWindowTitle(f"算法信息: {info.display_name}")
        msg.setText(f"""
        <b>算法名称:</b> {info.display_name}<br>
        <b>算法ID:</b> {item.algorithm_id}<br>
        <b>分类:</b> {info.category}<br>
        <b>版本:</b> {info.version}<br>
        <b>作者:</b> {info.author}<br>
        <b>描述:</b> {info.description}
        """)
        msg.exec()
    
    def _delete_combined_algorithm(self, item: AlgorithmItem):
        """删除组合算法"""
        algorithm_id = item.algorithm_id
        algorithm_name = item.algorithm_info.display_name
        
        # 确认删除
        reply = QMessageBox.question(
            None, '确认删除',
            f'确定要删除组合算法 "{algorithm_name}" 吗？\n\n'
            f'算法ID: {algorithm_id}\n\n'
            '此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 获取组合算法管理器并删除算法
                from core.managers.combined_algorithm_manager import CombinedAlgorithmManager
                from core.managers.log_manager import debug
                
                # 创建组合算法管理器实例
                combined_manager = CombinedAlgorithmManager()
                
                # 删除组合算法
                success = combined_manager.delete_combined_algorithm(algorithm_id)
                
                if success:
                    # 从注册表中移除
                    if self.registry:
                        self.registry.unregister_algorithm(algorithm_id)
                    
                    # 刷新显示
                    self.refresh_algorithms()
                    
                    QMessageBox.information(None, '删除成功', 
                        f'组合算法 "{algorithm_name}" 已删除')
                    
                    debug(f"组合算法已删除: {algorithm_id}", "ALGO_PANEL")
                else:
                    QMessageBox.warning(None, '删除失败', 
                        f'无法删除组合算法 "{algorithm_name}"')
                    
            except Exception as e:
                QMessageBox.critical(None, '删除错误', 
                    f'删除组合算法时发生错误:\n{str(e)}')
    
    def _edit_combined_algorithm(self, item: AlgorithmItem):
        """编辑组合算法"""
        algorithm_id = item.algorithm_id
        algorithm_name = item.algorithm_info.display_name
        
        QMessageBox.information(None, '编辑功能', 
            f'编辑组合算法功能正在开发中\n\n'
            f'算法: {algorithm_name}\n'
            f'ID: {algorithm_id}')
    
    def _manage_combined_algorithms(self):
        """打开组合算法管理对话框"""
        try:
            from core.managers.combined_algorithm_manager import CombinedAlgorithmManager
            from PyQt6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel, QPushButton, QMessageBox
            
            # 创建管理对话框
            dialog = QDialog()
            dialog.setWindowTitle("组合算法管理")
            dialog.resize(500, 400)
            
            layout = QVBoxLayout(dialog)
            
            # 标题
            title = QLabel("🔧 组合算法管理")
            title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
            layout.addWidget(title)
            
            # 组合算法列表
            combined_list = QListWidget()
            layout.addWidget(QLabel("已保存的组合算法:"))
            layout.addWidget(combined_list)
            
            # 加载组合算法
            combined_manager = CombinedAlgorithmManager()
            all_combined = combined_manager.get_all_combined_algorithms()
            
            if not all_combined:
                combined_list.addItem("暂无组合算法")
            else:
                for algorithm_id, chain_config in all_combined.items():
                    algorithm_info = combined_manager.get_algorithm_info(algorithm_id)
                    if algorithm_info:
                        item_text = f"{algorithm_info.display_name} ({algorithm_id})"
                        item = QListWidgetItem(item_text)
                        item.setData(1, algorithm_id)  # 存储算法ID
                        combined_list.addItem(item)
            
            # 按钮布局
            button_layout = QHBoxLayout()
            
            # 删除按钮
            delete_btn = QPushButton("🗑️ 删除选中")
            delete_btn.clicked.connect(lambda: self._delete_selected_combined(dialog, combined_list))
            button_layout.addWidget(delete_btn)
            
            button_layout.addStretch()
            
            # 关闭按钮
            close_btn = QPushButton("关闭")
            close_btn.clicked.connect(dialog.close)
            button_layout.addWidget(close_btn)
            
            layout.addLayout(button_layout)
            
            # 显示对话框
            dialog.exec()
            
        except Exception as e:
            QMessageBox.critical(None, '错误', f'打开组合算法管理对话框失败:\n{str(e)}')
    
    def _delete_selected_combined(self, dialog, combined_list):
        """删除选中的组合算法"""
        current_item = combined_list.currentItem()
        if not current_item:
            return
        
        algorithm_id = current_item.data(1)  # 获取存储的算法ID
        algorithm_name = current_item.text()
        
        if not algorithm_id:
            return
        
        # 确认删除
        reply = QMessageBox.question(
            dialog, '确认删除',
            f'确定要删除组合算法 "{algorithm_name}" 吗？\n\n'
            f'算法ID: {algorithm_id}\n\n'
            '此操作不可撤销。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 获取组合算法管理器并删除算法
                from core.managers.combined_algorithm_manager import CombinedAlgorithmManager
                
                # 创建组合算法管理器实例
                combined_manager = CombinedAlgorithmManager()
                
                # 删除组合算法
                success = combined_manager.delete_combined_algorithm(algorithm_id)
                
                if success:
                    # 从注册表中移除
                    if self.registry:
                        self.registry.unregister_algorithm(algorithm_id)
                    
                    # 刷新显示
                    self.refresh_algorithms()
                    
                    # 关闭并重新打开对话框以更新列表
                    dialog.close()
                    self._manage_combined_algorithms()
                    
                    QMessageBox.information(dialog, '删除成功', 
                        f'组合算法 "{algorithm_name}" 已删除')
                else:
                    QMessageBox.warning(dialog, '删除失败', 
                        f'无法删除组合算法 "{algorithm_name}"')
                    
            except Exception as e:
                QMessageBox.critical(dialog, '删除错误', 
                    f'删除组合算法时发生错误:\n{str(e)}')
    
    def _start_tree_drag(self, tree: QTreeWidget, supportedActions):
        """开始从树形控件拖拽"""
        item = tree.currentItem()
        if isinstance(item, AlgorithmItem):
            drag = QDrag(tree)
            mimeData = QMimeData()
            
            # 设置拖拽数据
            mimeData.setText(item.algorithm_id)
            mimeData.setData("application/x-algorithm-id", item.algorithm_id.encode())
            
            # 创建拖拽图像
            pixmap = QPixmap(100, 30)
            pixmap.fill(Qt.GlobalColor.lightGray)
            painter = QPainter(pixmap)
            painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, item.text(0))  # 修复：添加列参数
            painter.end()
            
            drag.setMimeData(mimeData)
            drag.setPixmap(pixmap)
            drag.setHotSpot(QPoint(50, 15))
            
            # 执行拖拽
            drag.exec(Qt.DropAction.CopyAction)
    
    def filter_algorithms(self, text: str):
        """过滤算法"""
        if not self.registry or not text.strip():
            self.refresh_algorithms()
            return
        
        # 搜索算法
        matching_algorithms = self.registry.search_algorithms(text)
        
        if not matching_algorithms:
            # 没有匹配结果
            self.category_tabs.clear()
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.addWidget(QLabel(f"未找到匹配 '{text}' 的算法"))
            self.category_tabs.addTab(empty_widget, "搜索结果")
            return
        
        # 显示搜索结果
        self.category_tabs.clear()
        
        result_widget = QWidget()
        result_layout = QVBoxLayout(result_widget)
        
        # 创建搜索结果树形控件
        tree = QTreeWidget()
        tree.setHeaderLabel(f"搜索结果: '{text}'")
        tree.setDragEnabled(True)
        tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        
        # 添加搜索结果到树形控件
        for algorithm_id in matching_algorithms:
            algorithm_info = self.registry.get_algorithm_info(algorithm_id)
            if algorithm_info:
                algorithm_item = AlgorithmItem(algorithm_id, algorithm_info)
                tree.addTopLevelItem(algorithm_item)
        
        # 连接拖拽事件
        tree.startDrag = lambda supportedActions: self._start_tree_drag(tree, supportedActions)
        
        result_layout.addWidget(tree)
        
        # 添加搜索结果统计
        info_label = QLabel(f"找到 {len(matching_algorithms)} 个匹配算法")
        info_label.setStyleSheet("color: gray; font-size: 10px;")
        result_layout.addWidget(info_label)
        
        self.category_tabs.addTab(result_widget, f"搜索: {text}")


def create_algorithm_panel(parent):
    """创建算法面板"""
    panel = QWidget()
    panel.setMinimumWidth(300)
    panel.setMaximumWidth(500)
    layout = QVBoxLayout(panel)
    
    # 面板标题
    title_layout = QHBoxLayout()
    title_label = QLabel("🧮 算法库")
    title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #2c3e50;")
    title_layout.addWidget(title_label)
    title_layout.addStretch()
    
    # 添加算法按钮
    add_algorithm_btn = QPushButton("➕")
    add_algorithm_btn.setToolTip("添加外部算法")
    add_algorithm_btn.setFixedSize(25, 25)
    add_algorithm_btn.clicked.connect(parent.add_external_algorithm)
    title_layout.addWidget(add_algorithm_btn)
    
    layout.addLayout(title_layout)
    
    # 算法分类组件
    parent.algorithm_category_widget = AlgorithmCategoryWidget()
    parent.algorithm_category_widget.algorithm_dropped.connect(parent.on_algorithm_dropped)
    layout.addWidget(parent.algorithm_category_widget)
    
    # 算法信息显示区域
    info_group = QGroupBox("算法信息")
    info_layout = QVBoxLayout()
    
    parent.algorithm_info_label = QLabel("选择一个算法查看详细信息")
    parent.algorithm_info_label.setWordWrap(True)
    parent.algorithm_info_label.setStyleSheet("padding: 10px; background-color: #f8f9fa;")
    info_layout.addWidget(parent.algorithm_info_label)
    
    info_group.setLayout(info_layout)
    layout.addWidget(info_group)
    
    return panel
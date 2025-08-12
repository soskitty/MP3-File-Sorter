# -*- coding: utf-8 -*-
import sys
import os
import shutil
from mutagen.mp3 import MP3
from pathlib import Path

# 从PySide6库中导入所有需要的模块
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QPushButton, QCheckBox, QProgressBar, QLabel, QFileDialog, QMessageBox
)
from PySide6.QtCore import QThread, QObject, Signal, Slot

# --- 核心工作逻辑，放在一个独立的线程中运行 ---
class Worker(QObject):
    progress_updated = Signal(int, int, str)
    finished = Signal()

    def __init__(self, file_list, dest_path, remove_tags):
        super().__init__()
        self.file_list = file_list
        self.dest_path_str = dest_path # 路径现在是纯净的字符串
        self.remove_tags = remove_tags
        self.is_running = True

    @Slot()
    def run(self):
        total_files = len(self.file_list)
        # 使用 pathlib 来处理路径
        dest_folder = Path(self.dest_path_str)

        for i, source_path in enumerate(self.file_list):
            if not self.is_running:
                break
            
            filename = os.path.basename(source_path)
            # 使用 / 操作符来拼接路径，pathlib 会自动处理好分隔符
            dest_path_full = dest_folder / filename
            
            self.progress_updated.emit(i + 1, total_files, f"正在处理: {filename}")

            try:
                if self.remove_tags:
                    audio = MP3(source_path)
                    audio.delete()
                    audio.save(dest_path_full)
                else:
                    shutil.copy2(source_path, dest_path_full)
            except Exception as e:
                print(f"处理文件 '{source_path}' -> '{dest_path_full}' 时出错: {e}")
        
        self.finished.emit()

# --- 主窗口代码 ---
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MP3 顺序写入工具 v0.1")
        self.setGeometry(300, 300, 600, 450)
        self.worker = None
        self.thread = None
        self.destination_path = ""
        
        self.setAcceptDrops(True)

        # --- 界面布局 ---
        self.layout = QVBoxLayout(self)
        self.list_widget = QListWidget()
        self.layout.addWidget(self.list_widget)

        controls_layout = QHBoxLayout()
        btn_up = QPushButton("▲ 上移")
        btn_down = QPushButton("▼ 下移")
        btn_clear = QPushButton("清空列表")
        controls_layout.addWidget(btn_up)
        controls_layout.addWidget(btn_down)
        controls_layout.addWidget(btn_clear)
        controls_layout.addStretch()
        self.layout.addLayout(controls_layout)

        dest_layout = QHBoxLayout()
        self.dest_label = QLabel("目标文件夹: (未选择)")
        btn_dest = QPushButton("选择...")
        dest_layout.addWidget(self.dest_label)
        dest_layout.addWidget(btn_dest)
        self.layout.addLayout(dest_layout)
        
        action_layout = QHBoxLayout()
        self.cb_remove_tags = QCheckBox("复制时移除ID3标签")
        self.btn_write = QPushButton("开始写入")
        self.btn_write.setStyleSheet("background-color: green; color: white;")
        action_layout.addWidget(self.cb_remove_tags)
        action_layout.addStretch()
        action_layout.addWidget(self.btn_write)
        self.layout.addLayout(action_layout)

        self.progress_bar = QProgressBar()
        self.status_label = QLabel("准备就绪 (可拖拽文件或文件夹到此窗口)")
        self.layout.addWidget(self.progress_bar)
        self.layout.addWidget(self.status_label)

        # --- 连接信号和槽 ---
        btn_up.clicked.connect(self.move_up)
        btn_down.clicked.connect(self.move_down)
        btn_clear.clicked.connect(self.list_widget.clear)
        btn_dest.clicked.connect(self.select_destination)
        self.btn_write.clicked.connect(self.start_writing)

    # 拖拽事件处理
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            path = url.toLocalFile()
            if os.path.isdir(path):
                for root, dirs, files in os.walk(path):
                    for file in files:
                        if file.lower().endswith('.mp3'):
                            self.list_widget.addItem(os.path.join(root, file))
            elif path.lower().endswith('.mp3'):
                self.list_widget.addItem(path)
    
    # 上下移动等函数
    def move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)
    def move_down(self):
        row = self.list_widget.currentRow()
        if row >= 0 and row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)
            
    def select_destination(self):
        folder = QFileDialog.getExistingDirectory(self, "选择目标文件夹")
        if folder:
            self.destination_path = folder 
            self.dest_label.setText(f"目标文件夹: {folder}")

    def start_writing(self):
        if not self.destination_path or not os.path.isdir(self.destination_path):
            QMessageBox.critical(self, "错误", "请先选择一个有效的目标文件夹！")
            return
        if self.list_widget.count() == 0:
            QMessageBox.critical(self, "错误", "文件列表为空！")
            return

        file_list = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        remove_tags = self.cb_remove_tags.isChecked()

        self.thread = QThread()
        self.worker = Worker(file_list, self.destination_path, remove_tags)
        self.worker.moveToThread(self.thread)
        self.worker.progress_updated.connect(self.update_status)
        self.worker.finished.connect(self.on_finished)
        self.thread.started.connect(self.worker.run)
        self.btn_write.setEnabled(False)
        self.thread.start()

    def update_status(self, current, total, text):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)
        self.status_label.setText(text)

    def on_finished(self):
        self.status_label.setText("任务完成！")
        self.btn_write.setEnabled(True)
        self.thread.quit()
        self.thread.wait()
        QMessageBox.information(self, "完成", "所有文件已按指定顺序成功写入目标文件夹！")

# --- 程序入口 ---
if __name__ == "__main__":
    app = QApplication(sys.argv) # <-- 之前被截断的行，现在是完整的
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
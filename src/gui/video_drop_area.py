from PyQt6.QtWidgets import QLabel, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
import os

class VideoDropArea(QLabel):
    filesDropped = pyqtSignal(list)
    VIDEO_EXTENSIONS = ('.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm')

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("\nDrag and drop video files here\nor click to select files\n\nSupported formats: MP4, MKV, AVI, MOV, WMV, FLV, WEBM")
        self.dark_mode = False
        self._update_style()
        self.setAcceptDrops(True)

    def _update_style(self):
        if self.dark_mode:
            self.setStyleSheet("""
                QLabel {
                    border: 2px dashed #666;
                    border-radius: 5px;
                    padding: 20px;
                    background: #2a2a2a;
                    color: #ffffff;
                }
            """)
        else:
            self.setStyleSheet("""
                QLabel {
                    border: 2px dashed #aaa;
                    border-radius: 5px;
                    padding: 20px;
                    background: #f8f9fa;
                    color: #000000;
                }
            """)

    def set_dark_mode(self, enabled: bool):
        self.dark_mode = enabled
        self._update_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Select Video Files",
                "",
                f"Video Files (*{' *'.join(self.VIDEO_EXTENSIONS)})"
            )
            if files:
                self.filesDropped.emit(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            # Check if at least one file is a video file or a directory
            for url in urls:
                file_path = url.toLocalFile()
                if (os.path.isdir(file_path) or 
                    any(file_path.lower().endswith(ext) for ext in self.VIDEO_EXTENSIONS)):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            files.append(file_path)
        
        self.filesDropped.emit(files)
        event.acceptProposedAction()
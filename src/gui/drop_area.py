from PyQt6.QtWidgets import QLabel, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
import os
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
import os

class DropArea(QLabel):
    filesDropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("\nDrag and drop SRT files here\nor click to select files")
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
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select SRT Files",
            "",
            "SRT Files (*.srt)"
        )
        if files:
            self.filesDropped.emit(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            local_file = url.toLocalFile()
            if local_file.lower().endswith('.srt'):
                files.append(local_file)  # Add individual .srt files
            elif os.path.isdir(local_file):  # Check if it's a directory
                # List all .srt files in the directory
                srt_files = [os.path.join(local_file, f) for f in os.listdir(local_file) if f.endswith('.srt')]
                files.extend(srt_files)  # Add found .srt files to the list
                
                # Check if no .srt files were found
                if not srt_files:
                    QMessageBox.warning(self, "Warning", "No .srt files found in the dropped folder.")

        if files:
            self.filesDropped.emit(files)
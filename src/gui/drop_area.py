from PyQt6.QtWidgets import QLabel, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
import os
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
import os

class DropArea(QLabel):
    filesDropped = pyqtSignal(list)
    invalidFilesDropped = pyqtSignal(str)  # New signal for invalid files

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("\nDrag and drop subtitle files here\nor click to select files")
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
            "Select Subtitle Files",
            "",
            "Subtitle Files (*.srt *.ass *.ssa *.css *.txt *.vtt)"
        )
        if files:
            self.filesDropped.emit(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            # Check if at least one file has a valid extension
            valid = False
            subtitle_extensions = ('.srt', '.ass', '.ssa', '.txt', '.vtt')
            for url in event.mimeData().urls():
                local_file = url.toLocalFile()
                if local_file.lower().endswith(subtitle_extensions) or os.path.isdir(local_file):
                    valid = True
                    break
            if valid:
                event.accept()
            else:
                event.ignore()
                # Remove warning message here - it will be handled after drop
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = []
        invalid_files = []
        subtitle_extensions = ('.srt', '.ass', '.ssa', '.txt', '.vtt')
        
        for url in event.mimeData().urls():
            local_file = url.toLocalFile()
            if local_file.lower().endswith(subtitle_extensions) or os.path.isdir(local_file):
                files.append(local_file)  # Add both subtitle files and directories directly
            elif local_file:
                invalid_files.append(os.path.basename(local_file))
        
        # Emit signal for invalid files instead of showing dialog directly
        if invalid_files:
            self.invalidFilesDropped.emit("Please drop only supported subtitle files (srt, ass, ssa, txt, vtt) or folders.")
        
        if files:
            self.filesDropped.emit(files)
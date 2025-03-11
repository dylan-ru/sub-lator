from PyQt6.QtWidgets import QLabel, QFileDialog, QMessageBox
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon
import os
from PyQt6.QtGui import QDragEnterEvent, QDropEvent

class DropArea(QLabel):
    filesDropped = pyqtSignal(list)
    
    SUPPORTED_SUBTITLE_FORMATS = {
        '.srt': 'SubRip',
        '.vtt': 'WebVTT',
        '.ass': 'Advanced SubStation Alpha',
        '.ssa': 'SubStation Alpha',
        '.txt': 'Plain Text',
        '.sub': 'MicroDVD'
    }

    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("\nDrag and drop subtitle files here\nor click to select files\n\n" + 
                    f"Supported formats: {', '.join(self.SUPPORTED_SUBTITLE_FORMATS.keys())}")
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
            f"Subtitle Files (*{' *'.join(self.SUPPORTED_SUBTITLE_FORMATS.keys())})"
        )
        if files:
            self.filesDropped.emit(files)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            # Check if at least one file is a subtitle file or a directory
            for url in urls:
                file_path = url.toLocalFile()
                if (os.path.isdir(file_path) or 
                    any(file_path.lower().endswith(ext) for ext in self.SUPPORTED_SUBTITLE_FORMATS)):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            local_file = url.toLocalFile()
            if any(local_file.lower().endswith(ext) for ext in self.SUPPORTED_SUBTITLE_FORMATS):
                files.append(local_file)  # Add individual subtitle files
            elif os.path.isdir(local_file):  # Check if it's a directory
                # List all subtitle files in the directory
                subtitle_files = []
                for root, _, filenames in os.walk(local_file):
                    for filename in filenames:
                        if any(filename.lower().endswith(ext) for ext in self.SUPPORTED_SUBTITLE_FORMATS):
                            subtitle_files.append(os.path.join(root, filename))
                files.extend(subtitle_files)  # Add found subtitle files to the list
                
                # Check if no subtitle files were found
                if not subtitle_files:
                    QMessageBox.warning(self, "Warning", "No subtitle files found in the dropped folder.")

        if files:
            self.filesDropped.emit(files)
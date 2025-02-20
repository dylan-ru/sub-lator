from PyQt6.QtWidgets import QMainWindow
from .translation_view import TranslationView

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SRT File Translator")
        self.setMinimumSize(800, 600)
        
        # Create translation view as the main view
        self.translation_view = TranslationView()
        self.setCentralWidget(self.translation_view)
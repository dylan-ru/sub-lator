from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtGui import QIcon
import os
from .translation_view import TranslationView

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SRT File Translator")
        self.setMinimumSize(800, 600)
        self.setWindowIcon(QIcon(os.path.join('src/icons', 'icon.png')))
        
        # Create translation view as the main view
        self.translation_view = TranslationView()
        self.setCentralWidget(self.translation_view)
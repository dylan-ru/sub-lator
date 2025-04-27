from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtGui import QIcon
import os
from .translation_view import TranslationView
from ..utils.resource_path import resource_path

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SRT File Translator")
        self.setMinimumSize(800, 600)
        # Set window icon
        self.setWindowIcon(QIcon(resource_path('icons/icon.png')))
        # Create translation view as the main view
        self.translation_view = TranslationView()
        self.setCentralWidget(self.translation_view)
from PyQt6.QtWidgets import QMainWindow
from PyQt6.QtGui import QIcon
import os
from .translation_view import TranslationView
from .srt_generation_view import SrtGenerationView

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SRT File Translator")
        self.setMinimumSize(800, 600)
        self.setWindowIcon(QIcon(os.path.join('src/icons', 'icon.png')))
        
        # Initialize views
        self.translation_view = TranslationView()
        self.srt_generation_view = SrtGenerationView()
        
        # Set up view connections
        self.translation_view.switch_to_srt_generation.connect(self.show_srt_generation_view)
        self.srt_generation_view.switch_to_translation.connect(self.show_translation_view)
        
        # Set translation view as the initial view
        self.setCentralWidget(self.translation_view)
        self.current_view = self.translation_view

    def show_srt_generation_view(self):
        # Take ownership of the current widget to prevent deletion
        current = self.takeCentralWidget()
        if current:
            current.setParent(self)  # Keep the widget alive
        
        self.setCentralWidget(self.srt_generation_view)
        self.current_view = self.srt_generation_view

    def show_translation_view(self):
        # Take ownership of the current widget to prevent deletion
        current = self.takeCentralWidget()
        if current:
            current.setParent(self)  # Keep the widget alive
            
        self.setCentralWidget(self.translation_view)
        self.current_view = self.translation_view
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QProgressBar, QFrame
from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint, QRect, QSize
from PyQt6.QtGui import QColor, QPalette
from dataclasses import dataclass, field
from typing import Optional

def default_background_color() -> QColor:
    """Create default background color with 70% opacity"""
    return QColor(60, 60, 60, 178)  # 70% opacity

def default_text_color() -> QColor:
    """Create default text color"""
    return QColor(255, 255, 255)

def default_progress_color() -> QColor:
    """Create default progress bar color"""
    return QColor(200, 200, 200)

@dataclass
class ToastStyle:
    """Style configuration for toast notifications"""
    background_color: QColor = field(default_factory=default_background_color)
    text_color: QColor = field(default_factory=default_text_color)
    progress_bar_color: QColor = field(default_factory=default_progress_color)
    duration_ms: int = 5000  # 5 seconds by default
    margin: int = 10
    padding: int = 10
    min_width: int = 200
    max_width: int = 400

class ToastNotification(QFrame):
    """A toast notification widget that appears within the parent widget"""
    
    def __init__(self, parent: QWidget, message: str, style: Optional[ToastStyle] = None):
        super().__init__(parent)
        
        # Store parent reference for positioning
        self.parent = parent
        
        # Initialize style
        self.style = style or ToastStyle()
        
        # Set up the widget
        self._setup_ui()
        
        # Set the message
        self.message_label.setText(message)
        
        # Position within parent
        self._position_toast()
        
        # Start the timer
        self._setup_timer()
        
        # Show the notification
        self.show()
        self.fade_in()

    def _setup_ui(self):
        """Set up the UI components"""
        # Configure frame appearance
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)
        
        # Set background color with opacity
        self.setStyleSheet(f"""
            QFrame {{
                background-color: rgba({self.style.background_color.red()}, 
                                     {self.style.background_color.green()}, 
                                     {self.style.background_color.blue()}, 
                                     {self.style.background_color.alpha()});
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 30);
            }}
        """)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            self.style.padding, 
            self.style.padding, 
            self.style.padding, 
            self.style.padding
        )
        
        # Add message label
        self.message_label = QLabel()
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(f"color: {self.style.text_color.name()}")
        layout.addWidget(self.message_label)
        
        # Add progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100)
        self.progress_bar.setTextVisible(False)
        
        # Style the progress bar
        progress_style = f"""
            QProgressBar {{
                background: transparent;
                border: none;
                height: 2px;
            }}
            QProgressBar::chunk {{
                background-color: {self.style.progress_bar_color.name()};
            }}
        """
        self.progress_bar.setStyleSheet(progress_style)
        layout.addWidget(self.progress_bar)
        
        # Set size constraints
        self.setMinimumWidth(self.style.min_width)
        self.setMaximumWidth(self.style.max_width)
        
        # Start with opacity 0
        self.setWindowOpacity(0.0)

    def _position_toast(self):
        """Position the toast in the top-right corner of the parent"""
        parent_rect = self.parent.rect()
        
        # First display the widget to get its proper size
        self.adjustSize()
        
        # Ensure the toast fits within the parent
        toast_width = min(self.sizeHint().width(), parent_rect.width() - 2 * self.style.margin)
        self.setFixedWidth(toast_width)
        
        # Calculate position (top-right corner with margin)
        x = parent_rect.width() - self.width() - self.style.margin
        y = self.style.margin
        
        # Set the position
        self.move(x, y)
        
        # Ensure it stays on top
        self.raise_()

    def _setup_timer(self):
        """Set up timers for the toast"""
        # Progress bar timer
        self.progress_timer = QTimer(self)
        self.progress_timer.timeout.connect(self._update_progress)
        self.progress_timer.setInterval(50)
        self.time_remaining = self.style.duration_ms
        
        # Auto-close timer
        QTimer.singleShot(self.style.duration_ms, self.fade_out)

    def _update_progress(self):
        """Update the progress bar"""
        self.time_remaining = max(0, self.time_remaining - 50)
        progress = (self.time_remaining / self.style.duration_ms) * 100
        self.progress_bar.setValue(int(progress))
        
        if self.time_remaining <= 0:
            self.progress_timer.stop()

    def fade_in(self):
        """Fade in animation"""
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.animation.finished.connect(self._on_fade_in_complete)
        self.animation.start()

    def _on_fade_in_complete(self):
        """Start the progress timer after fade in"""
        self.progress_timer.start()

    def fade_out(self):
        """Fade out animation"""
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setStartValue(1.0)
        self.animation.setEndValue(0.0)
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.InCubic)
        self.animation.finished.connect(self.deleteLater)
        self.animation.start()

    @classmethod
    def show_toast(cls, parent: QWidget, message: str, style: Optional[ToastStyle] = None) -> 'ToastNotification':
        """Convenience method to create and show a toast notification"""
        return cls(parent, message, style) 
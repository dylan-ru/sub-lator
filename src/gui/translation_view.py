from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QTextEdit, QComboBox, QLabel, QLineEdit, QListWidget,
                            QMessageBox, QProgressBar, QCheckBox, QFileDialog, QApplication,
                            QDialog)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMetaObject, Q_ARG, QSize
import os
from typing import List, Dict, Optional, Tuple
from ..core.translation_service import OpenRouterTranslationService
from .drop_area import DropArea
from ..core.async_utils import run_async, AsyncWorker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QStyle

state = False

LANGUAGE_CODES = {
    "English": "EN",
    "Spanish": "ES",
    "French": "FR",
    "German": "DE",
    "Italian": "IT",
    "Portuguese": "PT",
    "Russian": "RU",
    "Japanese": "JP",
    "Korean": "KR",
    "Chinese": "CN"
}

class TranslationResultDialog(QDialog):
    """Dialog to show translation results with a scrollable list of translated files."""
    def __init__(self, parent=None, translated_files=None, dark_mode=False):
        super().__init__(parent)
        self.setWindowTitle("Success")
        self.setMinimumSize(600, 400)  # Wider and taller dialog
        
        # Create layout
        layout = QVBoxLayout(self)
        
        # Header label with icon
        header_layout = QHBoxLayout()
        icon_label = QLabel()
        icon_label.setPixmap(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton).pixmap(32, 32))
        header_layout.addWidget(icon_label)
        
        header_label = QLabel("Translation completed successfully!")
        header_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        header_layout.addWidget(header_label)
        header_layout.addStretch()
        layout.addLayout(header_layout)
        
        # Files label
        files_label = QLabel("Translated files:")
        layout.addWidget(files_label)
        
        # Text edit for file list (scrollable)
        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        
        # Format and add the list of files
        file_list_text = ""
        if translated_files:
            for file in translated_files:
                file_list_text += f"- {file}\n"
        self.text_edit.setText(file_list_text)
        
        layout.addWidget(self.text_edit)
        
        # OK button
        button_box = QHBoxLayout()
        ok_button = QPushButton("OK")
        ok_button.setFixedWidth(100)
        ok_button.clicked.connect(self.accept)
        button_box.addStretch()
        button_box.addWidget(ok_button)
        layout.addLayout(button_box)
        
        # Apply dark mode if needed
        if dark_mode:
            self.setStyleSheet("""
                QDialog { background-color: #121212; color: #e0e0e0; }
                QLabel { color: #e0e0e0; }
                QTextEdit { 
                    background-color: #1e1e1e; 
                    color: #e0e0e0;
                    border: 1px solid #3d3d3d;
                }
                QPushButton { 
                    background-color: #2d2d2d; 
                    color: #f0f0f0;
                    border: 1px solid #3d3d3d;
                    padding: 5px;
                    border-radius: 5px;
                }
                QPushButton:hover {
                    background-color: darkgray;
                }
            """)

class TranslationView(QWidget):
    # Add signals for thread-safe UI updates
    update_progress = pyqtSignal(int)
    update_status = pyqtSignal(str)
    back_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.translation_service = OpenRouterTranslationService()
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_key_statuses)
        self.update_timer.start(1000)
        self.files = []
        self.store_at_original = False
        self.output_dir = None
        self.current_worker: Optional[AsyncWorker] = None

        # Connect signals to slots
        self.update_progress.connect(self._update_progress_bar)
        self.update_status.connect(self._update_status_label)
        
        # Set default button style
        self.setStyleSheet("""
            QPushButton { 
                border-radius: 5px;
                padding: 5px;
                border: 1px solid #ccc;
            }
            QPushButton:hover {
                background-color: rgb(140, 140, 140);
            }
            QComboBox {
                border-radius: 5px;
                padding: 8px 25px 8px 8px;
                border: 1px solid #ccc;
                min-width: 6em;
            }
            QComboBox:hover {
                background-color: rgb(102, 102, 102);
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
                border-radius: 5px;
            }
            QComboBox::down-arrow {
                image: url(src/icons/down_arrow_dark.svg);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #ccc;
                border-radius: 5px;
                selection-background-color: #e0e0e0;
            }
        """)
        
        self._init_ui()
        self.dark_mode_active = False

    def closeEvent(self, event):
        """Handle cleanup when the widget is closed."""
        self.update_timer.stop()
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.quit()
            self.current_worker.wait()
            self.current_worker.deleteLater()
        super().closeEvent(event)

    def hideEvent(self, event):
        """Handle cleanup when the widget is hidden."""
        if self.current_worker and self.current_worker.isRunning():
            self.current_worker.quit()
            self.current_worker.wait()
            self.current_worker.deleteLater()
            self.current_worker = None
        super().hideEvent(event)

    def _cleanup_worker(self):
        """Clean up the current worker if it exists."""
        if self.current_worker:
            if self.current_worker.isRunning():
                self.current_worker.quit()
                self.current_worker.wait()
            self.current_worker.deleteLater()
            self.current_worker = None

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # Open source button
        self.open_source_btn = QPushButton("Open Source")
        folder_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)  # Get folder icon
        self.open_source_btn.setIcon(folder_icon)  # Set the folder icon
        self.open_source_btn.setIconSize(QSize(16, 16))  # Set icon size
        self.open_source_btn.setStyleSheet("text-align: left;")  # Align text to the left
        self.open_source_btn.clicked.connect(self._open_source_folder)
        self.open_source_btn.setFixedSize(self.open_source_btn.sizeHint() + QSize(7, 0))  # Set size to match text
        self.default_open_source_btn_size = self.open_source_btn.size()  # Store default size
        layout.addWidget(self.open_source_btn)  # Add above the drop area

        # Dark mode button
        self.dark_mode_btn = QPushButton("Dark Mode: OFF")  # Store as instance variable
        self.moon_icon = QIcon(os.path.join('src/icons', 'moon_icon.png'))
        self.white_moon_icon = QIcon(os.path.join('src/icons', 'white_moon.png'))
        self.dark_mode_btn.setIcon(self.moon_icon)
        self.dark_mode_btn.setIconSize(QSize(16, 16))
        self.dark_mode_btn.setStyleSheet("text-align: left;")
        self.dark_mode_btn.clicked.connect(self.toggle_dark_mode)
        self.dark_mode_btn.setFixedSize(self.dark_mode_btn.sizeHint() + QSize(7, 0))  
        layout.addWidget(self.dark_mode_btn)

        # File management buttons
        file_buttons_layout = QHBoxLayout()
        file_buttons_layout.addWidget(self.open_source_btn, alignment=Qt.AlignmentFlag.AlignLeft)  # Add open source button to the left
        file_buttons_layout.addWidget(self.dark_mode_btn, alignment=Qt.AlignmentFlag.AlignRight)  # Add dark mode button to the right
        layout.addLayout(file_buttons_layout)  # Add the button layout to the main layout

        # Drop area
        self.drop_area = DropArea()
        self.drop_area.filesDropped.connect(self._handle_dropped_files)
        self.drop_area.invalidFilesDropped.connect(self._handle_invalid_files)
        layout.addWidget(self.drop_area)

        # File list section
        file_section = QVBoxLayout()
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(100)
        file_section.addWidget(self.file_list)
        
        # File management buttons
        file_buttons_layout = QHBoxLayout()
        
        # Remove selected file button
        remove_file_btn = QPushButton("Remove Selected")
        remove_file_btn.setFixedWidth(remove_file_btn.sizeHint().width() + 6)  # Add 6 pixels (3 on each side)
        remove_file_btn.clicked.connect(self._remove_selected_file)
        file_buttons_layout.addWidget(remove_file_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Clear all files button
        clear_files_btn = QPushButton("Clear All")
        clear_files_btn.setFixedWidth(clear_files_btn.sizeHint().width() + 6)  # Add 6 pixels (3 on each side)
        clear_files_btn.clicked.connect(self._clear_files)
        file_buttons_layout.addWidget(clear_files_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        file_section.addLayout(file_buttons_layout)
        layout.addLayout(file_section)

        # API Key section
        api_key_section = QVBoxLayout()
        
        # API Key input
        api_key_input_layout = QHBoxLayout()
        api_key_label = QLabel("API Key:")
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        add_key_btn = QPushButton("Add Key")
        add_key_btn.clicked.connect(self._add_api_key)
        api_key_input_layout.addWidget(api_key_label)
        api_key_input_layout.addWidget(self.api_key_input)
        api_key_input_layout.addWidget(add_key_btn)
        api_key_section.addLayout(api_key_input_layout)

        # API Keys list
        api_keys_label = QLabel("Active API Keys:")
        api_key_section.addWidget(api_keys_label)
        self.api_keys_list = QListWidget()
        self.api_keys_list.setMaximumHeight(40)  # Reduced height since we only show one key
        api_key_section.addWidget(self.api_keys_list)

        # Remove key button
        remove_key_btn = QPushButton("Remove Selected Key")
        remove_key_btn.setFixedWidth(remove_key_btn.sizeHint().width() + 6)  # Add 6 pixels (3 on each side)
        remove_key_btn.clicked.connect(self._remove_selected_key)
        api_key_section.addWidget(remove_key_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addLayout(api_key_section)

        # Translation settings
        settings_layout = QHBoxLayout()
        
        # Model selection
        model_label = QLabel("Model:")
        self.model_combo = QComboBox()
        self.model_combo.addItems(self.translation_service.get_available_models())
        settings_layout.addWidget(model_label)
        settings_layout.addWidget(self.model_combo)
        
        # Target language
        language_label = QLabel("Target Language:")
        self.language_combo = QComboBox()
        self.language_combo.addItems(["English", "Spanish", "French", "German", "Italian", "Portuguese", "Russian", "Japanese", "Korean", "Chinese"])
        settings_layout.addWidget(language_label)
        settings_layout.addWidget(self.language_combo)
        
        layout.addLayout(settings_layout)

        # Store at original location checkbox
        self.store_original_cb = QCheckBox("Store files at the original location")
        self.store_original_cb.stateChanged.connect(self._toggle_output_directory)
        layout.addWidget(self.store_original_cb)

        # Output directory button
        self.select_dir_btn = QPushButton("Select Output Directory")
        self.select_dir_btn.setFixedWidth(self.select_dir_btn.sizeHint().width() + 6)  # Add 6 pixels (3 on each side)
        self.select_dir_btn.clicked.connect(self._select_output_directory)
        layout.addWidget(self.select_dir_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Progress section
        progress_layout = QVBoxLayout()
        self.progress_label = QLabel("Translation Progress:")
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        # Translate button
        self.translate_btn = QPushButton("Translate Files")
        self.translate_btn.setFixedWidth(self.translate_btn.sizeHint().width() + 6)  # Add 6 pixels (3 on each side)
        self.translate_btn.clicked.connect(self._translate_files)
        layout.addWidget(self.translate_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

    def set_store_at_original(self, store: bool):
        """Set whether to store files at original location."""
        self.store_at_original = store
        self.store_original_cb.setChecked(store)

    def set_output_directory(self, directory: str):
        """Set the output directory."""
        self.output_dir = directory
        self._update_output_label()

    def _find_subtitle_files_recursive(self, directory):
        """Find all subtitle files in a directory and its subdirectories."""
        subtitle_extensions = ('.srt', '.ass', '.ssa', '.txt', '.vtt')
        subtitle_files = []
        
        print(f"Searching directory recursively: {directory}")  # Enhanced debug output
        for root, dirs, files in os.walk(directory):
            for file in files:
                if file.lower().endswith(subtitle_extensions):
                    full_path = os.path.join(root, file)
                    subtitle_files.append(full_path)
                    print(f"Found subtitle file: {full_path}")  # Debug each file found
        
        print(f"Total subtitle files found: {len(subtitle_files)}")  # Summary debug output
        return subtitle_files

    def _handle_dropped_files(self, files: List[str]):
        """Handle dropped files or folders recursively."""
        print("Dropped files/folders:", files)  # Debugging output
        subtitle_extensions = ('.srt', '.ass', '.ssa', '.txt', '.vtt')
        added_files = False  # Flag to track if any files were added
        folders_processed = 0  # Counter for processed folders
        
        for file in files:
            if os.path.isdir(file):  # Check if the dropped item is a directory
                folders_processed += 1
                # Find all subtitle files recursively
                subtitle_files = self._find_subtitle_files_recursive(file)
                if subtitle_files:
                    print(f"Found {len(subtitle_files)} subtitle files in directory tree of {file}")
                    self.files.extend(subtitle_files)
                    added_files = True
                    self.status_label.setText(f"Found {len(subtitle_files)} subtitle files in {os.path.basename(file)}")
                else:
                    print(f"No subtitle files found in directory: {file}")
                    # Only show warning if this is the only folder dropped and no files were added
                    if folders_processed == len(files) and not added_files:
                        QMessageBox.warning(self, "Warning", f"No subtitle files found in the dropped folder.")
            elif file.lower().endswith(subtitle_extensions):
                print(f"Adding individual subtitle file: {file}")
                self.files.append(file)  # Add individual subtitle files
                added_files = True
        
        # Update the UI with found files
        if added_files:
            self._update_file_list()
        else:
            print("No files were added")
            if not folders_processed:  # If no folders were processed, show a different message
                QMessageBox.warning(self, "Warning", "No valid subtitle files were dropped.")

    def _update_file_list(self):
        """Update the list of files to be translated."""
        self.file_list.clear()
        for file in self.files:
            self.file_list.addItem(os.path.basename(file))

    def _toggle_output_directory(self, state):
        """Toggle output directory selection based on checkbox."""
        is_checked = bool(state)
        self.store_at_original = is_checked
        self.select_dir_btn.setEnabled(not is_checked)
        self._update_output_label()

    def _select_output_directory(self):
        """Select output directory for translated files."""
        dir_path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if dir_path:
            self.output_dir = dir_path
            self._update_output_label()

    def _update_output_label(self):
        """Update the output directory label."""
        if self.store_at_original:
            self.select_dir_btn.setText("Output: Using original file locations")
        else:
            self.select_dir_btn.setText(f"Output: {self.output_dir or 'Current Directory'}")
        self.select_dir_btn.setFixedWidth(self.select_dir_btn.sizeHint().width() + 6)  # Add 6 pixels (3 on each side)

    def _translate_files(self):
        """Start the translation process."""
        if not self.files:
            QMessageBox.warning(self, "Warning", "No files to translate!")
            return

        if not self.translation_service.get_api_keys():
            QMessageBox.warning(self, "Warning", "Please add at least one API key")
            return

        # Clean up any existing worker
        self._cleanup_worker()

        # Disable UI elements
        self.translate_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        
        # Start async translation
        self.current_worker = run_async(self._translate_files_async)
        self.current_worker.finished.connect(self._on_translation_finished)
        self.current_worker.error.connect(self._on_translation_error)

    async def _translate_files_async(self):
        """Translate all files asynchronously."""
        try:
            total_files = len(self.files)
            translated_files = []

            for file_index, input_file in enumerate(self.files):
                self.update_status.emit(f"Processing file {file_index + 1} of {total_files}: {os.path.basename(input_file)}")
                
                try:
                    # Read the input file
                    with open(input_file, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Create translation prompt
                    translation_prompt = (
                        f"Translate the following SRT subtitles to {self.language_combo.currentText()}. "
                        "Important rules:\n"
                        "1. Preserve all numbers exactly as they are\n"
                        "2. Preserve all timecodes exactly as they are\n"
                        "3. Only translate the text content\n"
                        "4. Maintain the exact same line breaks and format\n\n"
                        f"{content}"
                    )
                    
                    # Translate content
                    self.update_status.emit(f"Translating file: {os.path.basename(input_file)}")
                    translated = self.translation_service.translate(
                        translation_prompt,
                        self.model_combo.currentText()
                    )
                    
                    # Save translated file
                    base_name = os.path.splitext(os.path.basename(input_file))[0]
                    file_ext = os.path.splitext(input_file)[1]  # Get original file extension
                    output_dir = os.path.dirname(input_file) if self.store_at_original else (self.output_dir or ".")
                    lang_suffix = LANGUAGE_CODES.get(self.language_combo.currentText(), "XX")
                    output_file = os.path.join(output_dir, f"{base_name}-{lang_suffix}{file_ext}")
                    
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(translated)
                    
                    translated_files.append(output_file)
                    
                    # Update progress
                    progress = ((file_index + 1) * 100) / total_files
                    self.update_progress.emit(int(progress))
                    
                except Exception as e:
                    raise ValueError(f"Error processing file {input_file}: {str(e)}")
            
            return translated_files
            
        except Exception as e:
            self.update_status.emit(f"Error: {str(e)}")
            raise e

    def _on_translation_finished(self, translated_files):
        """Handle successful translation completion."""
        if not translated_files:
            self.update_status.emit("No files were translated")
            return
            
        # Use the custom dialog instead of QMessageBox
        dialog = TranslationResultDialog(
            self, 
            translated_files=translated_files, 
            dark_mode=self.dark_mode_active
        )
        dialog.exec()
        
        self.update_status.emit("Translation completed successfully")
        self.translate_btn.setEnabled(True)
        self._update_key_list()
        self._cleanup_worker()
        
        # Clear the file list
        self._clear_files()

    def _on_translation_error(self, error):
        """Handle translation error."""
        self.update_status.emit(f"Error: {str(error)}")
        QMessageBox.critical(self, "Error", str(error))
        self.translate_btn.setEnabled(True)
        self._update_key_list()
        self._cleanup_worker()

    def _add_api_key(self):
        key = self.api_key_input.text().strip()
        if not key:
            QMessageBox.warning(self, "Warning", "Please enter an API key")
            return

        self.translation_service.add_api_key(key)
        self.api_key_input.clear()
        self._update_key_list()

    def _remove_selected_key(self):
        current_item = self.api_keys_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select an API key to remove")
            return

        key = current_item.text().split(" [")[0]  # Extract key without status
        self.translation_service.remove_api_key(key)
        self._update_key_list()

    def _update_key_list(self):
        """Update the list of API keys and their statuses, showing only the first key with masking."""
        self.api_keys_list.clear()
        
        keys = self.translation_service.get_api_keys()
        if not keys:
            return
            
        # Only show the first key
        key = keys[0]
        status = self.translation_service.get_key_status(key)
        masked_key = self._mask_api_key(key)
        
        if status:
            cooldown = status["cooldown_remaining"]
            status_text = "Ready" if status["is_available"] else f"Cooldown: {cooldown:.1f}s"
            self.api_keys_list.addItem(f"{masked_key} [{status_text}]")

    def _mask_api_key(self, key):
        """Mask an API key to show only first 5 and last 3 characters."""
        if len(key) <= 8:  # If key is too short, just mask most of it
            return key[:2] + "..." + key[-2:]
        return key[:5] + "..." + key[-3:]

    def _update_key_statuses(self):
        self._update_key_list()

    def _update_progress_bar(self, value: int):
        """Update progress bar from any thread."""
        self.progress_bar.setValue(value)

    def _update_status_label(self, text: str):
        """Update status label from any thread."""
        self.status_label.setText(text)

    def _remove_selected_file(self):
        """Remove the selected file from the list."""
        current_item = self.file_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a file to remove")
            return
            
        file_name = current_item.text()
        # Find and remove the full file path from self.files
        for file_path in self.files[:]:  # Create a copy to iterate while modifying
            if os.path.basename(file_path) == file_name:
                self.files.remove(file_path)
                break
        
        # Remove from list widget
        self.file_list.takeItem(self.file_list.row(current_item))

    def _clear_files(self):
        """Clear all files from the list."""
        if not self.files:
            return
            
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Do you want to clear all added files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.files.clear()
            self._update_file_list()

    def _open_source_folder(self):
        """Open the source folder and find srt files recursively."""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder_path:
            # Analyze the folder for subtitle files recursively
            subtitle_files = self._find_subtitle_files_recursive(folder_path)
            if subtitle_files:
                self.files.extend(subtitle_files)
                self._update_file_list()
                self.status_label.setText(f"Found {len(subtitle_files)} subtitle files in directory tree")
            else:
                QMessageBox.warning(self, "Warning", "No subtitle files found in the selected folder or its subfolders.")

    def toggle_dark_mode(self):
        if not self.dark_mode_active:
            dark_style = """
            QWidget { background-color: #121212; color: #e0e0e0; }
            QPushButton { 
                background-color: #2d2d2d; 
                color: #f0f0f0;
                border: 1px solid #3d3d3d;
                padding: 5px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: darkgray;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QListWidget, QLabel { 
                background-color: #1e1e1e; 
                color: #e0e0e0; 
            }
            QComboBox {
                background-color: rgb(115, 115, 115);
                color: #f0f0f0;
                border: 1px solid #3d3d3d;
                border-radius: 5px;
                padding: 8px 25px 8px 8px;
                min-width: 6em;
            }
            QComboBox:hover {
                background-color: rgb(128, 159, 255);
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
                border-radius: 5px;
                background-color: transparent;
            }
            QComboBox::down-arrow {
                image: url(src/icons/down_arrow.svg);
                width: 12px;
                height: 12px;
            }
            QComboBox QAbstractItemView {
                background-color: #2d2d2d;
                color: #f0f0f0;
                selection-background-color: #3d3d3d;
                selection-color: #ffffff;
                border: 1px solid #3d3d3d;
                border-radius: 5px;
            }
            QMessageBox { background-color: #121212; color: #e0e0e0; }
            """
            QApplication.instance().setStyleSheet(dark_style)
            self.dark_mode_active = True
            
            self.drop_area.set_dark_mode(True)
            self.dark_mode_btn.setText("Dark Mode: ON")
            self.dark_mode_btn.setIcon(self.white_moon_icon)
            self.open_source_btn.setFixedSize(QSize(self.default_open_source_btn_size.width() + 5, self.default_open_source_btn_size.height() + 2))
        else:
            QApplication.instance().setStyleSheet("")
            self.dark_mode_active = False
            self.drop_area.set_dark_mode(False)
            self.dark_mode_btn.setText("Dark Mode: OFF")
            self.dark_mode_btn.setIcon(self.moon_icon)
            self.open_source_btn.setFixedSize(QSize(self.default_open_source_btn_size.width() + 5, self.default_open_source_btn_size.height()))

    def _handle_invalid_files(self, message):
        """Handle invalid files dropped on the drop area."""
        QTimer.singleShot(100, lambda: QMessageBox.warning(self, "Warning", message))

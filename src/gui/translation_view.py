from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QTextEdit, QComboBox, QLabel, QLineEdit, QListWidget,
                            QMessageBox, QProgressBar, QCheckBox, QFileDialog, QApplication)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMetaObject, Q_ARG, QSize
import os
from typing import List, Dict, Optional, Tuple
from ..core.translation_service import OpenRouterTranslationService
from ..core.groq_translation_service import GroqTranslationService
from ..core.key_importer import KeyImporter
from .drop_area import DropArea
from ..core.async_utils import run_async, AsyncWorker
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QStyle
from ..core.api_provider import ApiProviderFactory

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

class TranslationView(QWidget):
    # Add signals for thread-safe UI updates
    update_progress = pyqtSignal(int)
    update_status = pyqtSignal(str)
    back_clicked = pyqtSignal()
    switch_to_srt_generation = pyqtSignal()  # New signal for navigation

    def __init__(self):
        super().__init__()
        self.current_provider = "OpenRouter"  # Default provider
        self.translation_services = {
            "OpenRouter": OpenRouterTranslationService(),
            "Groq": GroqTranslationService()
        }
        self.translation_service = self.translation_services[self.current_provider]
        
        # Initialize each provider with keys from storage
        self._initialize_provider_keys()
        
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
        
        # Update the API key list immediately after UI initialization
        self._update_key_list()
        
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

        # Navigation button for SRT Generation
        self.srt_generation_btn = QPushButton("Subtitles generation")
        self.srt_generation_btn.clicked.connect(self.switch_to_srt_generation.emit)
        layout.addWidget(self.srt_generation_btn)

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

        # API Provider selection
        provider_layout = QHBoxLayout()
        provider_label = QLabel("API Provider:")
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(["OpenRouter", "Groq"])
        self.provider_combo.setCurrentText(self.current_provider)
        self.provider_combo.currentTextChanged.connect(self._change_provider)
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_combo)
        layout.addLayout(provider_layout)

        # API Key section
        api_key_section = QVBoxLayout()
        
        # API Key input layout with import button
        api_key_input_layout = QHBoxLayout()
        
        # Import key button
        self.import_key_btn = QPushButton()
        upload_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowUp)
        self.import_key_btn.setIcon(upload_icon)
        self.import_key_btn.setToolTip("Import API Keys")
        self.import_key_btn.clicked.connect(self._import_api_keys)
        self.import_key_btn.setFixedSize(QSize(30, 30))
        api_key_input_layout.addWidget(self.import_key_btn)
        
        # API Key input
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
        self.api_keys_list.setMaximumHeight(100)
        api_key_section.addWidget(self.api_keys_list)

        # Remove key button
        remove_key_btn = QPushButton("Remove key")
        remove_key_btn.setFixedWidth(remove_key_btn.sizeHint().width() + 6)  # Add 6 pixels (3 on each side)
        remove_key_btn.clicked.connect(self._remove_all_keys)
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

    def _change_provider(self, provider_name: str):
        """Handle changing the API provider."""
        if provider_name in self.translation_services:
            self.current_provider = provider_name
            self.translation_service = self.translation_services[provider_name]
            
            # Reload the keys from storage to ensure we have the latest
            if provider_name == "Groq":
                from ..core.groq_key_storage import GroqKeyStorage
                groq_storage = GroqKeyStorage()
                # Get all keys from storage
                stored_keys = groq_storage.get_keys()
                
                # Clear existing keys in the service
                current_keys = self.translation_service.get_api_keys()
                for key in current_keys:
                    self.translation_service.remove_api_key(key)
                
                # Add all keys from storage to the service
                for key in stored_keys:
                    self.translation_service.add_api_key(key)
            elif provider_name == "OpenRouter":
                from ..core.key_storage import KeyStorage
                openrouter_storage = KeyStorage()
                # Get all keys from storage
                stored_keys = openrouter_storage.load_keys()
                
                # Clear existing keys in the service
                current_keys = self.translation_service.get_api_keys()
                for key in current_keys:
                    self.translation_service.remove_api_key(key)
                
                # Add all keys from storage to the service
                for key in stored_keys:
                    self.translation_service.add_api_key(key)
            
            # Update model list based on provider
            self.model_combo.clear()
            self.model_combo.addItems(self.translation_service.get_available_models())
            
            # Update key list
            self._update_key_list()
        else:
            QMessageBox.warning(self, "Warning", f"Unknown provider: {provider_name}")

    def set_store_at_original(self, store: bool):
        """Set whether to store files at original location."""
        self.store_at_original = store
        self.store_original_cb.setChecked(store)

    def set_output_directory(self, directory: str):
        """Set the output directory."""
        self.output_dir = directory
        self._update_output_label()

    def _handle_dropped_files(self, files: List[str]):
        """Handle dropped files or folders."""
        print("Dropped files/folders:", files)  # Debugging output
        for file in files:
            if os.path.isdir(file):  # Check if the dropped item is a directory
                # List all .srt files in the directory
                srt_files = [os.path.join(file, f) for f in os.listdir(file) if f.endswith('.srt')]
                print("Found .srt files:", srt_files)  # Debugging output
                self.files.extend(srt_files)  # Add found .srt files to the list
            elif file.endswith('.srt'):
                self.files.append(file)  # Add individual .srt files
        self._update_file_list()  # Update the displayed file list

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
                        content = f.read().strip()

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
                    output_dir = os.path.dirname(input_file) if self.store_at_original else (self.output_dir or ".")
                    lang_suffix = LANGUAGE_CODES.get(self.language_combo.currentText(), "XX")
                    output_file = os.path.join(output_dir, f"{base_name}-{lang_suffix}.srt")
                    
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
            
        # Show success message with list of translated files
        message = "Translation completed successfully!\n\nTranslated files:"
        for file in translated_files:
            message += f"\n- {file}"
            
        QMessageBox.information(self, "Success", message)
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

        # Check if there are any existing keys
        existing_keys = self.translation_service.get_api_keys()
        if existing_keys:
            QMessageBox.warning(
                self, 
                "Warning", 
                "Only one API key is allowed.\n Please remove the existing key first."
            )
            return

        # Add the key to the appropriate storage based on the current provider
        if self.current_provider == "Groq":
            from ..core.groq_key_storage import GroqKeyStorage
            groq_storage = GroqKeyStorage()
            groq_storage.add_key(key)
        elif self.current_provider == "OpenRouter":
            from ..core.key_storage import KeyStorage
            openrouter_storage = KeyStorage()
            # Need to get existing keys, add the new one, then save
            keys = openrouter_storage.load_keys()
            if key not in keys:
                keys.append(key)
                openrouter_storage.save_keys(keys)
            
        # Also add key to the service
        self.translation_service.add_api_key(key)
        self.api_key_input.clear()
        self._update_key_list()

    def _remove_all_keys(self):
        """Remove all API keys."""
        all_keys = self.translation_service.get_api_keys()
        if not all_keys:
            QMessageBox.warning(self, "Warning", "No API keys to remove")
            return

        reply = QMessageBox.question(
            self,
            "Confirm Remove",
            "Are you sure you want to remove API key?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Remove keys from the underlying storage directly
            if self.current_provider == "Groq":
                from ..core.groq_key_storage import GroqKeyStorage
                groq_storage = GroqKeyStorage()
                groq_storage.remove_all_keys()
            elif self.current_provider == "OpenRouter":
                from ..core.key_storage import KeyStorage
                openrouter_storage = KeyStorage()
                openrouter_storage.save_keys([])  # Save empty list to clear keys
            
            # Also remove from the service
            for key in all_keys:
                self.translation_service.remove_api_key(key)
                
            self._update_key_list()
            QMessageBox.information(self, "Success", "API key have been removed")

    def _update_key_list(self):
        """Update the list of API keys, showing only one key."""
        self.api_keys_list.clear()
        
        # Get all keys
        all_keys = self.translation_service.get_api_keys()
        if not all_keys:
            return
            
        # Only show the first key
        key = all_keys[0]
        if not key or len(key) == 0:
            return
            
        # Mask the key to show only first 5 and last 3 characters with exactly 6 asterisks
        if len(key) > 8:
            masked_key = f"{key[:5]}{'*' * 6}{key[-3:]}"
        else:
            masked_key = "*" * len(key)
            
        status = self.translation_service.get_key_status(key)
        if status:
            cooldown = status["cooldown_remaining"]
            status_text = "Ready" if status["is_available"] else f"Cooldown: {cooldown:.1f}s"
            self.api_keys_list.addItem(f"{self.current_provider}: {masked_key} [{status_text}]")
        else:
            # If no status, just show the key without status
            self.api_keys_list.addItem(f"{self.current_provider}: {masked_key}")
            
        # Set the first key as selected
        if self.api_keys_list.count() > 0:
            self.api_keys_list.setCurrentRow(0)

    def _update_key_statuses(self):
        # Check if we need to reload keys from storage
        self._refresh_api_keys_from_storage()
        self._update_key_list()
        
    def _refresh_api_keys_from_storage(self):
        """Refresh API keys from storage to ensure we have the latest."""
        # Reload keys from storage for the current provider
        if self.current_provider == "Groq":
            from ..core.groq_key_storage import GroqKeyStorage
            groq_storage = GroqKeyStorage()
            stored_keys = groq_storage.get_keys()
            
            # Get the current keys in the service
            current_keys = self.translation_service.get_api_keys()
            
            # Check if keys are different
            if set(stored_keys) != set(current_keys):
                # Clear existing keys
                for key in current_keys:
                    self.translation_service.remove_api_key(key)
                
                # Add keys from storage
                for key in stored_keys:
                    self.translation_service.add_api_key(key)
                    
        elif self.current_provider == "OpenRouter":
            from ..core.key_storage import KeyStorage
            openrouter_storage = KeyStorage()
            stored_keys = openrouter_storage.load_keys()
            
            # Get the current keys in the service
            current_keys = self.translation_service.get_api_keys()
            
            # Check if keys are different
            if set(stored_keys) != set(current_keys):
                # Clear existing keys
                for key in current_keys:
                    self.translation_service.remove_api_key(key)
                
                # Add keys from storage
                for key in stored_keys:
                    self.translation_service.add_api_key(key)

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
        """Open the source folder and find srt files."""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder_path:
            # Analyze the folder for srt files
            srt_files = [os.path.join(folder_path, f) for f in os.listdir(folder_path) if f.endswith('.srt')]
            if srt_files:
                self.files.extend(srt_files)
                self._update_file_list()
            else:
                QMessageBox.warning(self, "Warning", "No .srt files found in the selected folder.")

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

    def _import_api_keys(self):
        """Handle the import of API keys from a zip file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select API Keys File",
            "",
            "ZIP files (*.zip)"
        )
        
        if not file_path:
            return
            
        try:
            # Create key importer with the predefined password
            importer = KeyImporter("ZjcGbbwDjzDDkdL")
            
            # Import keys from the zip file
            imported_keys = importer.import_keys_from_zip(file_path)
            
            # Add each imported key
            for key in imported_keys:
                self.translation_service.add_api_key(key)
            
            # Update the key list
            self._update_key_list()
            
            # Show success message
            QMessageBox.information(
                self,
                "Success",
                f"Successfully imported API key"
            )
            
        except ValueError as e:
            QMessageBox.critical(
                self,
                "Import Error",
                str(e)
            )

    def _initialize_provider_keys(self):
        """Initialize each provider with the correct keys from storage."""
        # Load OpenRouter keys
        from ..core.key_storage import KeyStorage
        openrouter_storage = KeyStorage()
        openrouter_keys = openrouter_storage.load_keys()
        
        # Clear existing keys
        current_keys = self.translation_services["OpenRouter"].get_api_keys()
        for key in current_keys:
            self.translation_services["OpenRouter"].remove_api_key(key)
            
        # Add keys from storage
        for key in openrouter_keys:
            self.translation_services["OpenRouter"].add_api_key(key)
            
        # Load Groq keys
        from ..core.groq_key_storage import GroqKeyStorage
        groq_storage = GroqKeyStorage()
        groq_keys = groq_storage.get_keys()
        
        # Clear existing keys
        current_keys = self.translation_services["Groq"].get_api_keys()
        for key in current_keys:
            self.translation_services["Groq"].remove_api_key(key)
            
        # Add keys from storage
        for key in groq_keys:
            self.translation_services["Groq"].add_api_key(key)

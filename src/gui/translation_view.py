from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                            QTextEdit, QComboBox, QLabel, QLineEdit, QListWidget,
                            QMessageBox, QProgressBar, QCheckBox, QFileDialog)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QMetaObject, Q_ARG
import os
from typing import List, Dict, Optional, Tuple
from ..core.translation_service import OpenRouterTranslationService
from .drop_area import DropArea
from ..core.async_utils import run_async, AsyncWorker

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
        
        self._init_ui()

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
        remove_file_btn.clicked.connect(self._remove_selected_file)
        file_buttons_layout.addWidget(remove_file_btn)
        
        # Clear all files button
        clear_files_btn = QPushButton("Clear All")
        clear_files_btn.clicked.connect(self._clear_files)
        file_buttons_layout.addWidget(clear_files_btn)
        
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
        self.api_keys_list.setMaximumHeight(100)
        api_key_section.addWidget(self.api_keys_list)

        # Remove key button
        remove_key_btn = QPushButton("Remove Selected Key")
        remove_key_btn.clicked.connect(self._remove_selected_key)
        api_key_section.addWidget(remove_key_btn)

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
        self.select_dir_btn.clicked.connect(self._select_output_directory)
        layout.addWidget(self.select_dir_btn)

        # Progress section
        progress_layout = QVBoxLayout()
        self.progress_label = QLabel("Translation Progress:")
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        # Translate button
        self.translate_btn = QPushButton("Translate Files")
        self.translate_btn.clicked.connect(self._translate_files)
        layout.addWidget(self.translate_btn)

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

    def _handle_dropped_files(self, files: List[str]):
        """Handle dropped files."""
        self.files.extend([f for f in files if f.endswith('.srt')])
        self._update_file_list()

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
        # Store the currently selected key
        current_item = self.api_keys_list.currentItem()
        selected_key = current_item.text().split(" [")[0] if current_item else None
        
        self.api_keys_list.clear()
        selected_index = -1
        
        # Rebuild the list and find the index of the previously selected key
        for i, key in enumerate(self.translation_service.get_api_keys()):
            status = self.translation_service.get_key_status(key)
            if status:
                cooldown = status["cooldown_remaining"]
                status_text = "Ready" if status["is_available"] else f"Cooldown: {cooldown:.1f}s"
                self.api_keys_list.addItem(f"{key} [{status_text}]")
                if key == selected_key:
                    selected_index = i

        # Restore the selection if the key still exists
        if selected_index >= 0:
            self.api_keys_list.setCurrentRow(selected_index)

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
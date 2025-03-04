from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                         QListWidget, QMessageBox, QFileDialog, QLineEdit, QStyle, QComboBox,
                         QProgressBar)
from PyQt6.QtCore import pyqtSignal, Qt
import os
from typing import List
from .video_drop_area import VideoDropArea
from PyQt6.QtGui import QIcon
import assemblyai as aai
from ..core.async_utils import run_async
from ..core.api_provider import ApiProviderFactory

class ApiKeyManager:
    def __init__(self):
        self.current_provider = "AssemblyAI"  # Default provider
        self.providers = {
            "AssemblyAI": None,
            "Groq": None
        }
        self._initialize_providers()
        
    def _initialize_providers(self):
        """Initialize API provider instances."""
        from ..core.assembly_key_storage import AssemblyKeyStorage
        from ..core.groq_key_storage import GroqKeyStorage
        
        # Initialize provider storage
        self.providers["AssemblyAI"] = AssemblyKeyStorage()
        self.providers["Groq"] = GroqKeyStorage()
    
    def set_provider(self, provider_name: str):
        """Change the current API provider."""
        if provider_name in self.providers:
            self.current_provider = provider_name
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
    
    def get_current_provider(self) -> str:
        """Get the name of the current provider."""
        return self.current_provider
    
    def get_available_providers(self) -> List[str]:
        """Get list of available providers."""
        return list(self.providers.keys())

    def set_api_key(self, key: str):
        """Set API key for the current provider."""
        if not key:
            self.providers[self.current_provider].remove_all_keys()
        else:
            # For now, we only support one key per provider
            # First remove any existing keys
            current_keys = self.get_keys()
            if current_keys:
                for existing_key in current_keys:
                    self.providers[self.current_provider].remove_key(existing_key)
            
            # Add the new key
            self.providers[self.current_provider].add_key(key)

    def get_keys(self) -> List[str]:
        """Get API keys for the current provider."""
        return self.providers[self.current_provider].get_keys()

    def is_api_key_set(self) -> bool:
        """Check if API key is set for the current provider."""
        return bool(self.get_keys())


class SrtGenerationView(QWidget):
    switch_to_translation = pyqtSignal()  # Signal to switch back to translation view

    def __init__(self):
        super().__init__()
        self.video_files = []  # Store video file paths
        self.api_key_manager = ApiKeyManager()
        self.current_worker = None
        self.init_ui()
        self._update_api_key_list()  # Load saved API keys into the UI

    def init_ui(self):
        layout = QVBoxLayout()
        
        # Create a horizontal layout for the buttons
        button_layout = QHBoxLayout()

        # Open Source button
        open_source_btn = QPushButton("Open Source")
        open_source_btn.setFixedWidth(100)  # Set a fixed width to make it less wide
        folder_icon = open_source_btn.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)  # Get the standard folder icon
        open_source_btn.setIcon(folder_icon)  # Set the icon for the button
        open_source_btn.clicked.connect(self._open_source_folder)  # Connect to folder selection
        button_layout.addWidget(open_source_btn)

        # Subtitles Translation button
        back_button = QPushButton("Subtitles translation")
        back_button.setFixedWidth(self.width() // 3)  # Set width to one-third of the window size
        back_button.clicked.connect(self.switch_to_translation.emit)
        button_layout.addWidget(back_button)

        layout.addLayout(button_layout)

        # Drop area for video files
        self.drop_area = VideoDropArea()
        self.drop_area.filesDropped.connect(self._handle_dropped_files)
        layout.addWidget(self.drop_area)

        # File list section
        file_section = QVBoxLayout()
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(200)
        file_section.addWidget(self.file_list)
        
        # File management buttons
        file_buttons_layout = QHBoxLayout()
        
        # Remove selected file button
        remove_file_btn = QPushButton("Remove Selected")
        remove_file_btn.clicked.connect(self._remove_selected_file)
        file_buttons_layout.addWidget(remove_file_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Clear all files button
        clear_files_btn = QPushButton("Clear All")
        clear_files_btn.clicked.connect(self._clear_files)
        file_buttons_layout.addWidget(clear_files_btn, alignment=Qt.AlignmentFlag.AlignCenter)
        
        file_section.addLayout(file_buttons_layout)
        layout.addLayout(file_section)

        # API Provider selection
        provider_layout = QHBoxLayout()
        provider_label = QLabel("API Provider:")
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self.api_key_manager.get_available_providers())
        self.provider_combo.setCurrentText(self.api_key_manager.get_current_provider())
        self.provider_combo.currentTextChanged.connect(self._change_provider)
        provider_layout.addWidget(provider_label)
        provider_layout.addWidget(self.provider_combo)
        layout.addLayout(provider_layout)

        # API Key Input Layout
        api_key_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your API Key")
        api_key_layout.addWidget(self.api_key_input)

        # Button to save API Key
        save_api_key_btn = QPushButton("Add API Key")
        save_api_key_btn.clicked.connect(self._save_api_key)
        api_key_layout.addWidget(save_api_key_btn)

        layout.addLayout(api_key_layout)

        # API Key Display List
        self.api_key_list = QListWidget()  
        self.api_key_list.setMaximumHeight(100)  # Set a smaller maximum height
        layout.addWidget(self.api_key_list)

        # Button to remove all API Keys
        remove_all_keys_btn = QPushButton("Remove All API Keys")
        remove_all_keys_btn.clicked.connect(self._remove_all_api_keys)
        layout.addWidget(remove_all_keys_btn)

        # File extension selection layout
        extension_layout = QHBoxLayout()
        extension_label = QLabel("Output Format:")
        self.file_extension_combo = QComboBox()
        self.file_extension_combo.addItems(['.srt', '.txt', '.vtt'])  # Add options for file extensions
        extension_layout.addWidget(extension_label)
        extension_layout.addWidget(self.file_extension_combo)
        extension_layout.addStretch()  # Add stretch to keep widgets on the left
        layout.addLayout(extension_layout)

        # Progress section
        progress_layout = QVBoxLayout()
        self.progress_label = QLabel("Transcription Progress:")
        self.progress_bar = QProgressBar()
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)

        # Add the 'Generate SRT' button to the bottom of the layout
        generate_srt_btn = QPushButton("Generate SRT")
        generate_srt_btn.clicked.connect(self._generate_srt)
        layout.addWidget(generate_srt_btn)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        self.setLayout(layout)

    def _change_provider(self, provider_name: str):
        """Handle changing the API provider."""
        self.api_key_manager.set_provider(provider_name)
        self._update_api_key_list()

    def _handle_dropped_files(self, files: List[str]):
        """Handle dropped video files or folders."""
        video_extensions = VideoDropArea.VIDEO_EXTENSIONS
        
        for file_path in files:
            if os.path.isdir(file_path):
                # If it's a directory, look for video files inside
                for root, _, filenames in os.walk(file_path):
                    for filename in filenames:
                        if filename.lower().endswith(video_extensions):
                            full_path = os.path.join(root, filename)
                            if full_path not in self.video_files:
                                self.video_files.append(full_path)
            elif file_path.lower().endswith(video_extensions):
                # If it's a video file, add it directly
                if file_path not in self.video_files:
                    self.video_files.append(file_path)
        
        self._update_file_list()

    def _update_file_list(self):
        """Update the list widget with current video files."""
        self.file_list.clear()
        for file_path in self.video_files:
            self.file_list.addItem(os.path.basename(file_path))

    def _open_source_folder(self):
        """Open folder dialog to select video files."""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder with Video Files")
        if folder_path:
            # Simulate dropping the folder
            self._handle_dropped_files([folder_path])

    def _remove_selected_file(self):
        """Remove the selected file from the list."""
        current_item = self.file_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Warning", "Please select a file to remove")
            return
            
        file_name = current_item.text()
        # Find and remove the full file path from self.video_files
        for file_path in self.video_files[:]:  # Create a copy to iterate while modifying
            if os.path.basename(file_path) == file_name:
                self.video_files.remove(file_path)
                break
        
        # Remove from list widget
        self.file_list.takeItem(self.file_list.row(current_item))

    def _clear_files(self):
        """Clear all files from the list."""
        if not self.video_files:
            return
            
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Do you want to clear all video files?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.video_files.clear()
            self._update_file_list()

    def _save_api_key(self):
        api_key = self.api_key_input.text()
        if not api_key:
            QMessageBox.warning(self, "Warning", "Please enter an API key")
            return
            
        self.api_key_manager.set_api_key(api_key)
        self._update_api_key_list()
        self.api_key_input.clear()
        QMessageBox.information(self, "Success", "API Key added successfully!")

    def _remove_all_api_keys(self):
        if not self.api_key_manager.is_api_key_set():
            QMessageBox.warning(self, "Warning", "No API keys to remove")
            return
            
        reply = QMessageBox.question(
            self,
            "Confirm Remove",
            "Are you sure you want to remove all API keys?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            self.api_key_list.clear()
            self.api_key_manager.set_api_key(None)  # Clear the stored API key
            QMessageBox.information(self, "Success", "All API Keys removed successfully!")

    def _generate_srt(self):
        if not self.video_files:
            QMessageBox.warning(self, "Warning", "No video files to process!")
            return

        if not self.api_key_manager.is_api_key_set():
            QMessageBox.warning(self, "Warning", "Please add an API key")
            return

        # Clean up any existing worker
        if self.current_worker:
            if self.current_worker.isRunning():
                self.current_worker.quit()
                self.current_worker.wait()
            self.current_worker.deleteLater()

        # Start async transcription
        self.current_worker = run_async(self._generate_srt_async)
        self.current_worker.finished.connect(self._on_transcription_finished)
        self.current_worker.error.connect(self._on_transcription_error)

    async def _generate_srt_async(self):
        try:
            total_files = len(self.video_files)
            transcribed_files = []
            provider = self.api_key_manager.get_current_provider()

            if provider == "AssemblyAI":
                # Set API key for AssemblyAI
                api_key = self.api_key_manager.get_keys()[0]
                aai.settings.api_key = api_key

                for file_index, file_path in enumerate(self.video_files):
                    self.status_label.setText(f"Processing file {file_index + 1} of {total_files}: {os.path.basename(file_path)}")

                    try:
                        # Transcribe the file using AssemblyAI
                        transcriber = aai.Transcriber()
                        transcript = transcriber.transcribe(file_path)

                        if transcript.status == aai.TranscriptStatus.error:
                            raise ValueError(transcript.error)

                        # Save the transcript to a file with the selected extension
                        selected_extension = self.file_extension_combo.currentText()
                        output_file = os.path.splitext(file_path)[0] + selected_extension
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(transcript.text)

                        transcribed_files.append(output_file)

                        # Update progress
                        progress = ((file_index + 1) * 100) / total_files
                        self.progress_bar.setValue(int(progress))

                    except Exception as e:
                        raise ValueError(f"Error processing file {file_path}: {str(e)}")
                        
            elif provider == "Groq":
                # Use Groq transcription service
                from ..core.groq_transcription_service import GroqTranscriptionService
                groq_service = GroqTranscriptionService()
                
                # Get the API key
                if not self.api_key_manager.get_keys():
                    raise ValueError("No Groq API key found")
                
                # Process each file
                for file_index, file_path in enumerate(self.video_files):
                    self.status_label.setText(f"Processing file {file_index + 1} of {total_files}: {os.path.basename(file_path)}")
                    
                    try:
                        # Transcribe using Groq
                        transcription = groq_service.transcribe(file_path)
                        
                        # Save the transcript to a file with the selected extension
                        selected_extension = self.file_extension_combo.currentText()
                        output_file = os.path.splitext(file_path)[0] + selected_extension
                        with open(output_file, 'w', encoding='utf-8') as f:
                            f.write(transcription)
                            
                        transcribed_files.append(output_file)
                        
                        # Update progress
                        progress = ((file_index + 1) * 100) / total_files
                        self.progress_bar.setValue(int(progress))
                        
                    except Exception as e:
                        raise ValueError(f"Error processing file {file_path}: {str(e)}")

            return transcribed_files

        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            raise e

    def _on_transcription_finished(self, transcribed_files):
        if not transcribed_files:
            self.status_label.setText("No files were transcribed")
            return

        # Show success message with list of transcribed files
        message = "Transcription completed successfully!\n\nTranscribed files:"
        for file in transcribed_files:
            message += f"\n- {file}"

        QMessageBox.information(self, "Success", message)
        self.status_label.setText("Transcription completed successfully")
        self.progress_bar.setValue(0)

        # Clear the file list
        self._clear_files()

    def _on_transcription_error(self, error):
        self.status_label.setText(f"Error: {str(error)}")
        QMessageBox.critical(self, "Error", str(error))
        self.progress_bar.setValue(0)

    def _update_api_key_list(self):
        """Update the list of API keys in the UI."""
        self.api_key_list.clear()
        api_keys = self.api_key_manager.get_keys()
        provider = self.api_key_manager.get_current_provider()
        
        for api_key in api_keys:
            # Mask the key to show only first 5 and last 3 characters with asterisks
            masked_key = f"{api_key[:5]}{'*' * 6}{api_key[-3:]}" if len(api_key) > 8 else "*" * len(api_key)
            self.api_key_list.addItem(f"{provider} API Key: {masked_key}")
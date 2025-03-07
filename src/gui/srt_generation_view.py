from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                         QListWidget, QMessageBox, QFileDialog, QLineEdit, QStyle, QComboBox,
                         QProgressBar, QCheckBox, QFrame)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer  # type: ignore
import os
from typing import List, Optional, Tuple, Dict, Any
from .video_drop_area import VideoDropArea
from PyQt6.QtGui import QIcon, QColor  # type: ignore
import assemblyai as aai  # type: ignore
from ..core.async_utils import run_async
from ..core.api_provider import ApiProviderFactory
import re
import subprocess
import wave
import struct
import math
from PyQt6.QtCore import QUrl, QCoreApplication  # type: ignore
import time
from ..core.subtitle_synchronizer import SubtitleSynchronizer  # Legacy synchronizer
from ..core.whisper_synchronizer import WhisperSynchronizer  # New WhisperX-based synchronizer
import asyncio

# Conditionally import PyQt6.QtMultimedia - it might not be installed
has_qt_multimedia = False
try:
    from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput  # type: ignore
    has_qt_multimedia = True
except ImportError:
    print("PyQt6.QtMultimedia not available. Some duration detection methods will be skipped.")

class ApiKeyManager:
    def __init__(self):
        self.current_provider = "AssemblyAI"  # Default provider
        self.providers = {
            "AssemblyAI": None
        }
        self._initialize_providers()
        
    def _initialize_providers(self):
        """Load API keys from their provider-specific storage."""
        factory = ApiProviderFactory()
        
        # Initialize providers with their factory instances
        for provider_name in self.providers.keys():
            try:
                provider = factory.get_provider(provider_name)
                if provider:
                    # Get the API key from the provider's storage
                    key = provider.get_api_key()
                    if key:
                        self.providers[provider_name] = key
                    else:
                        print(f"No API key found for {provider_name}")
            except Exception as e:
                print(f"Error initializing provider {provider_name}: {str(e)}")
        
    def save_key(self, key):
        """Save an API key for the current provider."""
        if not key:
            raise ValueError("API key cannot be empty")
            
        try:
            # Get the provider to save the key
            factory = ApiProviderFactory()
            provider = factory.get_provider(self.current_provider)
            
            if provider:
                # Save the key using the provider's method
                provider.set_api_key(key)
                # Update our local cache
                self.providers[self.current_provider] = key
                print(f"API key saved for {self.current_provider}")
            else:
                raise ValueError(f"Provider {self.current_provider} not found")
        except Exception as e:
            print(f"Error saving API key: {str(e)}")
            raise
            
    def get_keys(self):
        """Get all API keys as a list."""
        keys = []
        
        # Add the key for the current provider if it exists
        current_key = self.providers.get(self.current_provider)
        if current_key:
            keys.append(current_key)
            
        return keys
        
    def is_api_key_set(self):
        """Check if an API key is set for the current provider."""
        return self.providers.get(self.current_provider) is not None
        
    def remove_all_keys(self):
        """Remove all API keys."""
        try:
            factory = ApiProviderFactory()
            
            for provider_name in self.providers.keys():
                provider = factory.get_provider(provider_name)
                if provider:
                    provider.clear_api_key()
                self.providers[provider_name] = None
                
            print("All API keys removed")
        except Exception as e:
            print(f"Error removing API keys: {str(e)}")
            raise
            
    def set_api_key(self, key):
        """Legacy method - calls save_key for compatibility."""
        return self.save_key(key)


class SrtGenerationView(QWidget):
    switch_to_translation = pyqtSignal()  # Signal to switch back to translation view

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SrtGenerationView")
        self.parent = parent  # Store parent reference
        
        # Initialize variables
        self.video_files = []  # List of video files to be processed
        self.current_video_index = 0  # Index of the current video being processed
        self.worker_thread = None  # Worker thread for transcription
        self.cancel_requested = False  # Flag to cancel processing
        self.whisper_sync = None  # WhisperX synchronizer
        self.temp_audio_files = []  # Temporary audio files to clean up
        self.current_audio_file = None  # Current audio file being processed
        self.current_audio_duration = None  # Duration of the current audio in seconds
        self.dark_mode_active = False  # Dark mode state
        self.api_key = None  # API key
        
        # Variables for sequential processing
        self.video_queue = []
        self.total_videos = 0
        self.processed_videos = 0
        self.successful_videos = 0
        self.current_video = None
        
        # API key manager
        self.api_key_manager = ApiKeyManager()
        
        # Set up the user interface
        self.init_ui()
        
        # Try to load API key on startup
        self._load_api_key_from_manager()
        
        # Resize the window slightly to trigger layout adjustments
        QTimer.singleShot(100, lambda: self.resize(self.width()+1, self.height()))

    def _load_api_key_from_manager(self):
        """Load the stored API key from the manager into the active property"""
        if self.api_key_manager.is_api_key_set():
            try:
                keys = self.api_key_manager.get_keys()
                if keys and len(keys) > 0:
                    self.api_key = keys[0]
                    print(f"Loaded API key from manager: {self.api_key[:4]}...{self.api_key[-4:]}")
                    # Also set it in the AssemblyAI module
                    aai.settings.api_key = self.api_key
                    # Update the UI to show the loaded API key
                    self._update_api_key_list()
                    return True
            except Exception as e:
                print(f"Error loading API key from manager: {str(e)}")
        return False

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

        # API Key Input Layout
        api_key_layout = QHBoxLayout()
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Enter your AssemblyAI API Key")
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
        output_layout = QHBoxLayout()
        extension_label = QLabel("Output Format:")
        self.file_extension_combo = QComboBox()
        self.file_extension_combo.addItems([".srt", ".vtt", ".txt"])
        self.file_extension_combo.setCurrentText(".srt")
        output_layout.addWidget(extension_label)
        output_layout.addWidget(self.file_extension_combo)
        output_layout.addStretch()  # Add stretch to keep widgets on the left
        layout.addLayout(output_layout)

        # Remove the advanced sync checkbox as we'll always use advanced sync
        # Instead, add an informational label about the sync
        sync_info_label = QLabel("Using WhisperX for advanced subtitle synchronization")
        sync_info_label.setToolTip("All subtitles will be synchronized using advanced AI-based alignment")
        layout.addWidget(sync_info_label)

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

    def _validate_video_file(self, file_path):
        """Check if the file is a valid video format for transcription."""
        if not os.path.exists(file_path):
            return False, f"File does not exist: {file_path}"
            
        # Check file extension
        valid_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv']
        _, ext = os.path.splitext(file_path)
        if ext.lower() not in valid_extensions:
            return False, f"Invalid file extension: {ext} (must be one of {', '.join(valid_extensions)})"
            
        # Check if file is accessible and has a reasonable size
        try:
            file_size = os.path.getsize(file_path)
            if file_size < 1000:  # Less than 1KB
                return False, f"File too small to be a valid video: {file_path}"
            
            # Check if file is not too large (>2GB)
            if file_size > 2 * 1024 * 1024 * 1024:
                print(f"Warning: Large file ({file_size / (1024*1024):.2f} MB): {file_path}")
                
            return True, "File is valid"
            
        except Exception as e:
            return False, f"Error checking file: {str(e)}"

    def _handle_dropped_files(self, files: List[str]):
        """Handle dropped video files and folders."""
        all_valid_files = []
        all_invalid_files = []  # Keep for debugging but don't show to user
        
        # Process each dropped item
        for file_path in files:
            if os.path.isdir(file_path):
                # If it's a directory, scan it for videos
                valid_files, invalid_files = self._scan_folder_for_videos(file_path)
                all_valid_files.extend(valid_files)
                all_invalid_files.extend(invalid_files)
            else:
                # If it's a file, validate it directly
                is_valid, message = self._validate_video_file(file_path)
                if is_valid:
                    all_valid_files.append(file_path)
                else:
                    all_invalid_files.append(f"{os.path.basename(file_path)}: {message}")
        
        # Add valid files to the list
        if all_valid_files:
            self.video_files.extend(all_valid_files)
            self._update_file_list()
            
            # Show success message using inlined toast
            self._show_inline_toast(f"{len(all_valid_files)} video files added")
        else:
            QMessageBox.warning(self, "No Videos Found", "No valid video files were found in the dropped items.")

    def _update_file_list(self):
        """Update the list widget with current video files."""
        self.file_list.clear()
        for file_path in self.video_files:
            self.file_list.addItem(os.path.basename(file_path))

    def _scan_folder_for_videos(self, folder_path):
        """Recursively scan a folder for valid video files."""
        valid_files = []
        invalid_files = []
        
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                is_valid, message = self._validate_video_file(file_path)
                if is_valid:
                    valid_files.append(file_path)
                else:
                    invalid_files.append(f"{os.path.basename(file_path)}: {message}")
        
        return valid_files, invalid_files

    def _open_source_folder(self):
        """Open folder dialog to select video files."""
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder with Video Files")
        if folder_path:
            # Scan the folder for video files
            valid_files, invalid_files = self._scan_folder_for_videos(folder_path)
            
            # Add valid files to the list
            if valid_files:
                self.video_files.extend(valid_files)
                self._update_file_list()
                
                # Show success message using inlined toast
                self._show_inline_toast(f"{len(valid_files)} video files added")
            else:
                QMessageBox.warning(self, "No Videos Found", "No valid video files were found in the selected folder.")

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
        """Save API key to the manager and validate it."""
        api_key = self.api_key_input.text().strip()
        
        if not api_key:
            self.status_label.setText("API key cannot be empty.")
            return False
            
        # Validate API key format (AssemblyAI keys are 32-char hex strings)
        if not self._validate_api_key_format(api_key):
            self.status_label.setText("Invalid API key format. Should be a 32-character string.")
            return False
            
        try:
            # Set API key for validation
            aai.settings.api_key = api_key
            
            # Test if the API key is valid by checking with AssemblyAI
            print("Checking API key validity...")
            self.status_label.setText("Checking API key validity...")
            
            # Make a small request to check if the API key is valid
            transcriber = aai.Transcriber()
            try:
                # Just get account details to verify the key works
                account = transcriber.get_account()
                if not account:
                    self.status_label.setText("API key validation failed: Could not retrieve account details")
                    return False
                    
                print(f"API key validated: Connected to AssemblyAI account")
                self.status_label.setText("API key validated and saved!")
                
                # Save the valid API key to both the manager and active property
                self.api_key_manager.save_key(api_key)
                self.api_key = api_key  # Set as active key
                
                # Clear the input field
                self.api_key_input.clear()
                
                # Update the list display
                self._update_api_key_list()
                return True
            except Exception as e:
                error_message = str(e)
                print(f"API key validation failed: {error_message}")
                self.status_label.setText(f"Invalid API key: {error_message}")
                return False
        except Exception as e:
            print(f"Error saving API key: {str(e)}")
            self.status_label.setText(f"Error: {str(e)}")
            return False
            
    def _validate_api_key_format(self, api_key):
        """Validate the API key format (basic format check)."""
        # AssemblyAI API keys are typically 32-character hexadecimal strings
        import re
        hex_pattern = re.compile(r'^[0-9a-f]{32}$')
        return bool(hex_pattern.match(api_key.lower()))

    def _remove_all_api_keys(self):
        """Remove all API keys."""
        reply = QMessageBox.question(
            self,
            "Confirm Removal",
            "Are you sure you want to remove all API keys?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # Clear the API key list widget
                self.api_key_list.clear()
                
                # Clear keys from manager
                self.api_key_manager.remove_all_keys()
                
                # Clear current key
                self.api_key = None
                
                # Update status
                self.status_label.setText("All API keys removed. Please add a new key.")
                
                QMessageBox.information(self, "Success", "All API Keys removed successfully!")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to remove API keys: {str(e)}")
                print(f"Error removing API keys: {str(e)}")

    def _generate_srt(self):
        """Generate SRT files for the selected videos"""
        # Reset progress state
        self.progress_bar.setValue(0)
        
        # Get video files
        video_files = [self.video_files[i] for i in range(self.file_list.count())]
        
        if not video_files:
            QMessageBox.warning(self, "No Files", "No video files have been added. Please add files first.")
            return

        # Check if we have a non-empty API key in the input field
        input_api_key = self.api_key_input.text().strip()
        if input_api_key:
            # User has entered a new key, try to save it
            if not self._save_api_key():
                return  # Save failed, don't proceed
        elif not self.api_key:
            # No API key in input field and no stored key, try to load from manager
            if not self._load_api_key_from_manager():
                QMessageBox.warning(self, "API Key Required", "Please enter a valid AssemblyAI API key")
                return

        # At this point, self.api_key should be set if we have a valid key
        if not self.api_key:
            QMessageBox.warning(self, "API Key Required", "No valid API key available. Please enter a valid AssemblyAI API key")
            return
        
        # Double-check that the API key is set in the AssemblyAI settings
        aai.settings.api_key = self.api_key
            
        # Check for existing worker and stop it if running
        if self.worker_thread:
            print("Stopping existing transcription thread")
            try:
                self.worker_thread.stop()
                self.worker_thread = None
                # Give a moment for thread cleanup
                QCoreApplication.processEvents()
            except Exception as e:
                print(f"Error stopping worker thread: {str(e)}")
        
        # Initialize sequential processing variables
        self.video_queue = video_files.copy()
        self.total_videos = len(video_files)
        self.processed_videos = 0
        self.successful_videos = 0
        
        # Update status
        self.status_label.setText(f"Starting transcription: 0/{self.total_videos} videos processed")
        QCoreApplication.processEvents()  # Force UI update
        
        # Start processing the first video
        self._process_next_video()

    def _process_next_video(self):
        """Process the next video in the queue"""
        try:
            # Check if we have more videos to process
            if not self.video_queue:
                # All videos processed, complete the operation
                self._on_all_videos_finished()
                return
                
            # Get the next video
            self.current_video = self.video_queue.pop(0)
            
            # Update UI
            current_status = f"Processing video {self.processed_videos + 1}/{self.total_videos}: {os.path.basename(self.current_video)}"
            self.status_label.setText(current_status)
            
            # Update progress bar to show overall completion
            overall_progress = int((self.processed_videos / self.total_videos) * 100)
            self.progress_bar.setValue(overall_progress)
            QCoreApplication.processEvents()  # Force UI update
            
            # Create a wrapper function to run the async method for a single video
            async def run_single_video():
                return await self._process_single_video_async(self.current_video)
            
            # Start async operation for this video
            self.worker_thread = run_async(
                run_single_video,
                on_success=self._on_single_video_complete,
                on_error=self._on_single_video_error
            )
        except Exception as e:
            print(f"Error starting video processing: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Try to continue with the next video
            self.processed_videos += 1
            
            # Clean up in case of error
            if hasattr(self, 'current_video'):
                self.current_video = None
            
            if hasattr(self, 'worker_thread') and self.worker_thread:
                try:
                    self.worker_thread.stop()
                except:
                    pass
                self.worker_thread = None
            
            # Try to continue with the next video if there are any left
            if self.video_queue:
                # Use a timer to allow some time for cleanup
                QTimer.singleShot(100, self._process_next_video)
            else:
                # End of queue, finish the process
                self._on_all_videos_finished()

    def _on_single_video_complete(self, result):
        """Handle completion of a single video"""
        try:
            # Update counters
            self.processed_videos += 1
            if result:  # If result is successful
                self.successful_videos += 1
            
            # Clean up the worker thread reference with verification
            if self.worker_thread:
                try:
                    # Ensure the thread is properly stopped
                    if hasattr(self.worker_thread, 'is_running') and self.worker_thread.is_running:
                        self.worker_thread.stop()
                    self.worker_thread = None
                except Exception as e:
                    print(f"Error cleaning up worker thread: {str(e)}")
            
            # Clean up resources from current video
            self._cleanup_current_video_resources()
            
            # Schedule next video processing with QTimer
            # This breaks the recursive chain and allows the call stack to clear
            QTimer.singleShot(100, self._process_next_video)
            
        except Exception as e:
            print(f"Error in video completion handler: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Schedule next video despite error
            QTimer.singleShot(100, self._process_next_video)

    def _cleanup_current_video_resources(self):
        """Clean up resources for the current video before processing next"""
        try:
            # Clean up WhisperX resources if needed
            if self.whisper_sync:
                try:
                    self.whisper_sync._cleanup_gpu()
                except Exception as e:
                    print(f"Error cleaning up WhisperX: {str(e)}")
            
            # Clean up current audio file
            if self.current_audio_file and os.path.exists(self.current_audio_file):
                try:
                    os.remove(self.current_audio_file)
                    if self.current_audio_file in self.temp_audio_files:
                        self.temp_audio_files.remove(self.current_audio_file)
                except Exception as e:
                    print(f"Error removing current audio file: {str(e)}")
            
            # Reset current video resources
            self.current_audio_file = None
            self.current_audio_duration = None
            
            # Force garbage collection
            import gc
            gc.collect()
            
            # Process any pending events
            QCoreApplication.processEvents()
            
        except Exception as e:
            print(f"Error in current video cleanup: {str(e)}")
            # Continue despite cleanup errors

    def _on_single_video_error(self, error):
        """Handle error during processing of a single video"""
        try:
            print(f"Error processing video {self.current_video}: {str(error)}")
            
            # Update counters
            self.processed_videos += 1
            
            # Clean up the worker thread reference with verification
            if self.worker_thread:
                try:
                    # Ensure the thread is properly stopped
                    if hasattr(self.worker_thread, 'is_running') and self.worker_thread.is_running:
                        self.worker_thread.stop()
                    self.worker_thread = None
                except Exception as e:
                    print(f"Error cleaning up worker thread after error: {str(e)}")
            
            # Clean up resources from current video
            self._cleanup_current_video_resources()
            
            # Schedule next video processing with QTimer
            QTimer.singleShot(100, self._process_next_video)
            
        except Exception as e:
            print(f"Error in error handler: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Schedule next video despite error in error handler
            QTimer.singleShot(100, self._process_next_video)
    
    def _on_all_videos_finished(self):
        """Handle completion of all videos"""
        print("All transcriptions completed")
        
        try:
            # Set progress bar to 100%
            self.progress_bar.setValue(100)
            QCoreApplication.processEvents()  # Force UI update
            
            # Clean up any remaining temporary files
            self._cleanup_temp_files()
            
            # Force garbage collection to help with memory
            import gc
            gc.collect()
            
            # Final status message
            if self.successful_videos > 0:
                success_msg = f"Successfully transcribed {self.successful_videos}/{self.total_videos} files."
                self.status_label.setText(success_msg)
                # Create message box with new style
                msg_box = QMessageBox(self)  # Create with parent only
                msg_box.setIcon(QMessageBox.Icon.Information)
                msg_box.setWindowTitle("Transcription Complete")
                msg_box.setText(success_msg)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg_box.setModal(False)
                msg_box.show()
            else:
                error_msg = "No files were transcribed. Check the API key and try again."
                self.status_label.setText(error_msg)
                # Create message box with new style
                msg_box = QMessageBox(self)  # Create with parent only
                msg_box.setIcon(QMessageBox.Icon.Warning)
                msg_box.setWindowTitle("Transcription Failed")
                msg_box.setText(error_msg)
                msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg_box.setModal(False)
                msg_box.show()
            
            # Clean up references
            self.worker_thread = None
            self.current_video = None
            
            # Process any pending events before returning
            QCoreApplication.processEvents()
            
        except Exception as e:
            print(f"Error in completion phase: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Try to at least update the UI
            try:
                self.status_label.setText(f"Error during completion: {str(e)}")
                QCoreApplication.processEvents()
            except:
                pass
    
    # Keep original handlers for backward compatibility with other parts of the code
    def _on_transcription_finished(self, result):
        """Original handler for completed transcription - kept for backward compatibility"""
        print("Original transcription handler called - no additional actions needed")
        # Do nothing else to avoid duplicate cleanup
    
    def _on_transcription_error(self, error):
        """Original handler for transcription error - kept for backward compatibility"""
        print(f"Original transcription error handler called: {str(error)}")
        # Do nothing else to avoid duplicate cleanup

    async def _process_single_video_async(self, video_file):
        """Process a single video file asynchronously"""
        try:
            # Calculate progress increment for this video (0-100 within its portion of the total)
            base_progress = int((self.processed_videos / self.total_videos) * 100)
            video_progress_increment = 100 / self.total_videos
            
            # Update status
            current_status = f"Processing video {self.processed_videos + 1}/{self.total_videos}: {os.path.basename(video_file)}"
            
            # Extract audio from video
            step_progress = base_progress + (video_progress_increment * 0.05)  # 5% of video progress
            self.progress_bar.setValue(int(step_progress))
            self.status_label.setText(f"{current_status} - Extracting audio...")
            QCoreApplication.processEvents()  # Force UI update
            
            audio_path = await self._extract_audio(video_file)
            if not audio_path:
                print(f"Failed to extract audio from {video_file}")
                return False
            
            # Transcribe audio using assemblyai
            step_progress = base_progress + (video_progress_increment * 0.25)  # 25% of video progress
            self.progress_bar.setValue(int(step_progress))
            self.status_label.setText(f"{current_status} - Transcribing...")
            QCoreApplication.processEvents()  # Force UI update
            
            # Create transcript
            transcript = await self._create_transcript(audio_path)
            if not transcript:
                print(f"Failed to create transcript for {video_file}")
                return False
            
            # Generate SRT file
            step_progress = base_progress + (video_progress_increment * 0.80)  # 80% of video progress
            self.progress_bar.setValue(int(step_progress))
            self.status_label.setText(f"{current_status} - Formatting subtitles...")
            QCoreApplication.processEvents()  # Force UI update
            
            srt_path = self._get_srt_path(video_file)
            srt_content = self._format_srt(transcript, self.current_audio_duration)
            
            # Save SRT file
            with open(srt_path, 'w', encoding='utf-8') as f:
                f.write(srt_content)
            
            print(f"Saved SRT file: {srt_path}")
            
            # Set progress for this file complete
            step_progress = base_progress + video_progress_increment
            self.progress_bar.setValue(int(step_progress))
            QCoreApplication.processEvents()  # Force UI update
            
            # Clean up the audio file after processing this video
            try:
                # Ensure any external resources from this video's processing are released
                if audio_path and audio_path in self.temp_audio_files and os.path.exists(audio_path):
                    os.remove(audio_path)
                    self.temp_audio_files.remove(audio_path)
                    print(f"Cleaned up temporary audio file: {audio_path}")
                
                # Reset any video-specific resources
                self.current_audio_file = None
                
                # Force processing any pending events
                QCoreApplication.processEvents()
                
                # Optional: help garbage collector
                import gc
                gc.collect()
            except Exception as e:
                print(f"Error during single video cleanup: {str(e)}")
                # Continue despite cleanup error
            
            return True
            
        except Exception as e:
            print(f"Error processing {video_file}: {str(e)}")
            import traceback
            traceback.print_exc()
            
            # Try to clean up any resources before returning
            try:
                if 'audio_path' in locals() and audio_path and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                        if audio_path in self.temp_audio_files:
                            self.temp_audio_files.remove(audio_path)
                        print(f"Cleaned up temporary audio file after error: {audio_path}")
                    except:
                        pass
            except:
                pass
                
            return False

    async def _generate_srt_async(self, video_files):
        """Legacy method for backward compatibility - now using sequential processing instead"""
        # This method is kept for backward compatibility
        # Now the processing is done one video at a time via _process_single_video_async
        try:
            total_files = len(video_files)
            successful_files = 0
            
            # Process one video at a time
            for i, video_file in enumerate(video_files):
                result = await self._process_single_video_async(video_file)
                if result:
                    successful_files += 1
            
            # Final status message
            if successful_files > 0:
                success_msg = f"Successfully transcribed {successful_files}/{total_files} files."
                return success_msg
            else:
                error_msg = "No files were transcribed. Check the API key and try again."
                return error_msg
        except Exception as e:
            print(f"Error in _generate_srt_async: {str(e)}")
            import traceback
            traceback.print_exc()
            raise e

    def closeEvent(self, event):
        """Handle cleanup when the widget is closed"""
        print("SrtGenerationView is closing, cleaning up resources...")
        
        # Stop any running worker thread
        if self.worker_thread:
            print("Stopping running transcription thread...")
            try:
                self.worker_thread.stop()
                self.worker_thread = None
            except Exception as e:
                print(f"Error stopping worker thread: {str(e)}")
        
        # Clean up any temporary files
        self._cleanup_temp_files()
        
        # Clean up WhisperX synchronizer if it exists
        if self.whisper_sync:
            try:
                self.whisper_sync._cleanup_gpu()
                self.whisper_sync = None
            except Exception as e:
                print(f"Error cleaning up WhisperX synchronizer: {str(e)}")
        
        # Run base class closeEvent to ensure proper Qt cleanup
        super().closeEvent(event)

    def _get_srt_path(self, video_path):
        """Get the path for the SRT file"""
        return os.path.splitext(video_path)[0] + '.srt'
    
    def _format_srt(self, utterances, video_duration=None):
        """Format utterances into SRT format with WhisperX synchronization."""
        if not utterances:
            print("No utterances provided for SRT formatting")
            return "1\n00:00:00,000 --> 00:00:05,000\nNo transcription available.\n"
            
        # Check if utterances have start/end times
        has_timing = hasattr(utterances[0], 'start') and hasattr(utterances[0], 'end')
        
        # If we don't have timing information, use sentence-based approach
        if not has_timing:
            print("Utterances don't have timing information, using sentence-based SRT generation")
            sentences = [u.text for u in utterances if hasattr(u, 'text')]
            return self._generate_srt_from_sentences(sentences, video_duration)
        
        # Try to get more accurate video duration if not provided
        if not video_duration and self.current_audio_file and os.path.exists(self.current_audio_file):
            try:
                with wave.open(self.current_audio_file, 'rb') as wf:
                    # Calculate duration from wave file properties
                    frames = wf.getnframes()
                    rate = wf.getframerate()
                    video_duration = frames / float(rate)
                    print(f"Detected audio duration from wave file: {video_duration:.2f}s")
            except Exception as e:
                print(f"Error detecting duration from audio file: {str(e)}")
        
        # CRITICAL FIX: If we have a known duration from the audio file, use it to scale timestamps
        subtitle_intervals = [(utterance.start, utterance.end) for utterance in utterances]
        subtitle_texts = [utterance.text for utterance in utterances]
        
        # Check if we need to scale timestamps
        max_initial_timestamp = max([end for _, end in subtitle_intervals]) if subtitle_intervals else 0
        print(f"Max initial timestamp: {max_initial_timestamp:.2f}s")
        
        # Force timestamp scaling if:
        # 1. We have audio duration information
        # 2. The max timestamp is significantly different from the audio duration 
        # (either too long or too short by more than 20%)
        force_scaling = False
        if video_duration and max_initial_timestamp > 0:
            # Calculate how far off the timestamps are
            ratio = max_initial_timestamp / video_duration
            print(f"Timestamp ratio: {ratio:.2f} (timestamps / duration)")
            
            # If timestamps are more than 20% off from the actual duration, force scaling
            if ratio > 1.2 or ratio < 0.8:
                print(f"Timestamps are significantly off from actual duration: {ratio:.2f}x difference")
                print(f"Max timestamp: {max_initial_timestamp:.2f}s, Audio duration: {video_duration:.2f}s")
                force_scaling = True
        
        # Apply pre-scaling if timestamps are way off (more than 1 hour for a short video)
        # or if we detect a significant difference from the known duration
        if max_initial_timestamp > 3600 or force_scaling:
            print("Applying pre-synchronization scaling to fix timestamp issues")
            
            # If we have a known duration, scale to it, otherwise use a reasonable default
            scaling_target = video_duration if video_duration else 60  # Default to 1 minute if unknown
            scale_factor = scaling_target / max_initial_timestamp
            subtitle_intervals = [(start * scale_factor, end * scale_factor) 
                                 for start, end in subtitle_intervals]
            print(f"Pre-scaled timestamps by factor of {scale_factor:.6f}")
            
        # Initialize WhisperX synchronizer if we have an audio file
        sync_successful = False
        aligned_intervals = None
        
        # Try to use WhisperX for better alignment if audio file is available
        if self.current_audio_file and os.path.exists(self.current_audio_file):
            try:
                print(f"Synchronizing subtitles with audio using WhisperX...")
                
                # Initialize WhisperX synchronizer if needed
                if not self.whisper_sync:
                    print("Initializing WhisperSynchronizer...")
                    self.whisper_sync = WhisperSynchronizer(model_size="base")
                
                # Use our stored audio duration if available
                if not video_duration and hasattr(self, 'current_audio_duration') and self.current_audio_duration:
                    print(f"Using detected audio duration: {self.current_audio_duration:.2f}s")
                    video_duration = self.current_audio_duration
                
                # Run synchronization
                aligned_intervals = self.whisper_sync.synchronize(
                    self.current_audio_file,
                    subtitle_intervals,
                    subtitle_texts,
                    video_duration
                )
                
                if aligned_intervals and len(aligned_intervals) == len(subtitle_texts):
                    sync_successful = True
                    print("WhisperX synchronization successful!")
                else:
                    print("WhisperX synchronization failed or returned incorrect number of intervals")
                    
            except Exception as e:
                print(f"Error during WhisperX synchronization: {str(e)}")
                import traceback
                traceback.print_exc()
                # Continue with original intervals
        else:
            print("No audio file available for synchronization, using original timing")
        
        # Use aligned intervals if available, otherwise use original intervals
        intervals_to_use = aligned_intervals if sync_successful else subtitle_intervals
        
        # Final validation: Perform an emergency check for unreasonable timestamps
        # This is our last defense against extreme timestamp values
        if intervals_to_use:
            max_time = max([end for _, end in intervals_to_use])
            reasonable_max = video_duration * 1.1 if video_duration else 3600  # 10% margin over audio duration
            
            if max_time > reasonable_max:
                print(f"CRITICAL: Final timestamps still unreasonable after synchronization (max: {max_time:.2f}s)")
                print("Applying emergency timestamp correction")
                
                # If we have video_duration, use it, otherwise use a safe default
                target_duration = video_duration if video_duration else 60  # Default to 1 minute
                
                # Distribute evenly across target duration
                total_segments = len(intervals_to_use)
                segment_duration = target_duration / total_segments
                
                intervals_to_use = [
                    (i * segment_duration, min((i + 1) * segment_duration, target_duration))
                    for i in range(total_segments)
                ]
                print(f"Emergency correction applied - {total_segments} segments distributed across {target_duration:.2f}s")
        
        # Generate SRT format
        srt_lines = []
        
        for i, ((start, end), text) in enumerate(zip(intervals_to_use, subtitle_texts)):
            # Skip empty segments
            if not text.strip():
                continue
                
            # Format timestamps
            start_time = self._format_timestamp_srt(start)
            end_time = self._format_timestamp_srt(end)
            
            # Add SRT entry
            srt_lines.append(f"{i+1}")
            srt_lines.append(f"{start_time} --> {end_time}")
            srt_lines.append(text)
            srt_lines.append("")  # Empty line between entries
            
        # Return the SRT content
        return "\n".join(srt_lines)
    
    def _format_timestamp_srt(self, seconds):
        """Format seconds to SRT timestamp format (HH:MM:SS,mmm)."""
        # Safety check - cap timestamps at a reasonable maximum (10 hours)
        MAX_REASONABLE_TIME = 10 * 60 * 60  # 10 hours in seconds
        
        # Ensure seconds is a valid number
        if not isinstance(seconds, (int, float)) or seconds < 0:
            print(f"Warning: Invalid timestamp value ({seconds}), defaulting to 0")
            seconds = 0
        
        # Apply reasonable upper bound
        if seconds > MAX_REASONABLE_TIME:
            print(f"Warning: Extremely large timestamp detected ({seconds:.2f}s), capping at {MAX_REASONABLE_TIME/3600} hours")
            seconds = MAX_REASONABLE_TIME
            
        # Format the timestamp
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _split_text_into_sentences(self, text):
        """Split text into sentences for formatting when timings are not available."""
        # Enhanced sentence splitting logic
        # First, break on standard punctuation
        partial_sentences = re.split(r'(?<=[.!?])\s+', text)
        
        sentences = []
        # Then, process long sentences that might need further splitting
        for sentence in partial_sentences:
            if len(sentence.split()) > 15:  # If a sentence is very long
                # Try to split on commas, semicolons, colons, or dashes
                chunks = re.split(r'(?<=[,;:\-])\s+', sentence)
                sentences.extend(chunks)
            else:
                sentences.append(sentence)
                
        return [s.strip() for s in sentences if s.strip()]
    
    def _generate_srt_from_sentences(self, sentences, video_duration=None):
        """Generate SRT format from sentences with estimated times, optimized for shorter segments."""
        srt_content = []
        
        # First, split long sentences into smaller chunks
        segments = []
        for sentence in sentences:
            words = sentence.split()
            # For very long sentences, split them into smaller chunks
            max_words_per_segment = 10  # Maximum words per segment
            
            if len(words) <= max_words_per_segment:
                segments.append(sentence)
            else:
                # Split into multiple segments
                for i in range(0, len(words), max_words_per_segment):
                    segment = " ".join(words[i:i+max_words_per_segment])
                    segments.append(segment)
        
        # Use the video duration to calculate appropriate timing if available
        total_segments = len(segments)
        if video_duration and total_segments > 0:
            # Divide the video duration by the number of segments
            avg_seconds_per_segment = video_duration / total_segments
        else:
            avg_seconds_per_segment = 2.5  # Default estimate - shorter for better syncing
        
        # NO overlap - each segment has a distinct time range
        for i, segment in enumerate(segments):
            # Calculate timings WITHOUT overlap - each segment gets its own time slot
            start_seconds = i * avg_seconds_per_segment
            end_seconds = min(
                (i + 1) * avg_seconds_per_segment,
                video_duration if video_duration else float('inf')
            )
            
            # Ensure no overlap by adding a small buffer between segments
            if i > 0:
                start_seconds += 0.01  # Add 10ms to prevent exact overlap with previous segment
            
            start_time = self._format_timestamp_srt(start_seconds)
            end_time = self._format_timestamp_srt(end_seconds)
            
            srt_content.append(f"{i+1}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(segment)
            srt_content.append("")  # Empty line between entries
        
        return "\n".join(srt_content)
    
    def _update_api_key_list(self):
        """Update the list of API keys in the UI."""
        self.api_key_list.clear()
        
        try:
            keys = self.api_key_manager.get_keys()
            for key in keys:
                # Mask the API key for display (show first 4 and last 4 chars)
                if len(key) > 8:
                    masked_key = f"{key[:4]}{'*' * (len(key) - 8)}{key[-4:]}"
                else:
                    masked_key = "****" 
                self.api_key_list.addItem(f"AssemblyAI API Key: {masked_key}")
            
            # Update status message if we have keys
            if keys:
                self.api_key = keys[0]  # Set the first key as active
                aai.settings.api_key = self.api_key  # Set in AssemblyAI
                self.status_label.setText("API key loaded. Ready to transcribe.")
            else:
                self.status_label.setText("Please set your AssemblyAI API key first.")
        except Exception as e:
            print(f"Error updating API key list: {str(e)}")
            self.status_label.setText("Error loading API keys.")

    async def _create_transcript(self, audio_path):
        """Create transcript using AssemblyAI"""
        try:
            # Make sure the API key is set
            if not self.api_key:
                print("API key not set. Transcription cannot proceed.")
                return None
                
            # Configure assemblyai
            aai.settings.api_key = self.api_key
            print(f"Using API key: {self.api_key[:4]}...{self.api_key[-4:]} (length: {len(self.api_key)})")
            
            # Create transcription config with language detection
            config = aai.TranscriptionConfig(
                language_detection=True,  # Enable automatic language detection
                language_confidence_threshold=0.4  # Set minimum confidence threshold
            )
            
            # Create a transcriber
            transcriber = aai.Transcriber()
            
            print(f"Starting transcription for {audio_path}")
            
            # Use run_async_operation to run transcribe in a background thread
            # The transcribe method handles both upload and transcription in one call
            transcript = await self._run_async_operation(
                lambda: transcriber.transcribe(audio_path, config)
            )
            
            # Check if we got a valid transcript
            if transcript is None:
                print("Transcription failed - no transcript returned")
                return None
                
            # Log language detection results if available
            if hasattr(transcript, 'language_code'):
                print(f"Detected language: {transcript.language_code}")
                if hasattr(transcript, 'language_confidence'):
                    print(f"Language detection confidence: {transcript.language_confidence}")
                
            # Debug: Log the transcript structure to understand it
            print(f"Transcript type: {type(transcript)}")
            print(f"Transcript attributes: {dir(transcript)}")
            
            # Check for utterances or similar structure in the transcript
            if hasattr(transcript, 'utterances') and transcript.utterances:
                print(f"Found {len(transcript.utterances)} utterances")
                return transcript.utterances
            elif hasattr(transcript, 'words') and transcript.words:
                print(f"Found {len(transcript.words)} words, converting to utterances format")
                # Convert words to utterance-like format if needed
                return self._convert_words_to_utterances(transcript.words)
            else:
                print("No utterances or words found in transcript")
                # Try to access transcript text directly
                if hasattr(transcript, 'text') and transcript.text:
                    print("Found transcript text, creating utterances from sentences")
                    sentences = self._split_text_into_sentences(transcript.text)
                    return [SimpleUtterance(text=s) for s in sentences]
                return None
        except Exception as e:
            print(f"Error creating transcript: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
            
    def _convert_words_to_utterances(self, words):
        """Convert word-level transcription to utterance format"""
        if not words:
            return []
            
        # Group words into sentences based on punctuation
        utterances = []
        current_utterance = []
        current_start = None
        
        for word in words:
            if current_start is None:
                current_start = word.start
                
            current_utterance.append(word.text)
            
            # Check if this word ends a sentence
            if word.text.endswith(('.', '!', '?')) or len(current_utterance) > 15:
                # Create a new utterance
                text = ' '.join(current_utterance)
                utterances.append(SimpleUtterance(
                    text=text,
                    start=current_start,
                    end=word.end
                ))
                
                # Reset for next utterance
                current_utterance = []
                current_start = None
                
        # Add any remaining words as a final utterance
        if current_utterance:
            text = ' '.join(current_utterance)
            utterances.append(SimpleUtterance(
                text=text,
                start=current_start,
                end=words[-1].end
            ))
            
        return utterances
        
    async def _run_async_operation(self, operation_func):
        """Run an operation asynchronously using loop.run_in_executor"""
        loop = asyncio.get_event_loop()
        try:
            # Run the operation in a separate thread
            result = await loop.run_in_executor(None, operation_func)
            return result
        except Exception as e:
            print(f"Error in async operation: {str(e)}")
            import traceback
            traceback.print_exc()
            raise

    def _cleanup_temp_files(self):
        """Clean up all temporary resources"""
        if not self.temp_audio_files and not self.worker_thread:
            return
            
        print("Starting comprehensive resource cleanup...")
        successful_deletions = 0
        
        try:
            # First, ensure no worker thread is active
            if self.worker_thread:
                try:
                    print("Stopping worker thread before cleanup")
                    self.worker_thread.stop()
                    # Give a moment for thread cleanup
                    QCoreApplication.processEvents()
                    # Set to None to help garbage collection
                    self.worker_thread = None
                except Exception as e:
                    print(f"Error stopping worker thread: {str(e)}")
            
            # Clean up temporary audio files
            for audio_file in self.temp_audio_files[:]:  # Use a copy of the list for safe iteration
                try:
                    if os.path.exists(audio_file):
                        print(f"Deleting temporary audio file: {audio_file}")
                        os.remove(audio_file)
                        successful_deletions += 1
                    self.temp_audio_files.remove(audio_file)  # Remove from list regardless of existence
                except Exception as e:
                    print(f"Error deleting temporary audio file {audio_file}: {str(e)}")
                    # Continue with other files even if this one fails
            
            # Process any pending events
            QCoreApplication.processEvents()
            
            # Help garbage collector
            import gc
            gc.collect()
            
            print(f"Successfully cleaned up {successful_deletions} temporary audio files")
        except Exception as e:
            print(f"Error during resource cleanup: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            # Reset all resource references
            self.temp_audio_files = []
            self.current_audio_file = None
            self.current_audio_duration = None
            # Process any pending events
            QCoreApplication.processEvents()

    async def _extract_audio(self, video_path):
        """Extract audio from video file."""
        try:
            print(f"Extracting audio from {video_path}")
            self.status_label.setText(f"Extracting audio from {os.path.basename(video_path)}...")
            QCoreApplication.processEvents()  # Force UI update
            
            # Get output path for the audio file
            output_dir = os.path.dirname(video_path)
            output_filename = os.path.splitext(os.path.basename(video_path))[0] + '.wav'
            output_path = os.path.join(output_dir, output_filename)
            
            # Optimized ffmpeg command to extract audio - use higher bitrate for better quality
            ffmpeg_cmd = [
                'ffmpeg', '-i', video_path, 
                '-vn',  # No video
                '-acodec', 'pcm_s16le',  # Convert to WAV
                '-ar', '16000',  # 16kHz sample rate (optimal for speech recognition)
                '-ac', '1',  # Mono
                '-y',  # Overwrite output file if it exists
                '-loglevel', 'error',  # Reduce logging output for performance
                output_path
            ]
            
            # Execute ffmpeg
            print(f"Running ffmpeg: {' '.join(ffmpeg_cmd)}")
            process = await asyncio.create_subprocess_exec(
                *ffmpeg_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Wait for the process to complete
            stdout, stderr = await process.communicate()
            
            # Check if process was successful
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown ffmpeg error"
                print(f"Error extracting audio: {error_msg}")
                self.status_label.setText(f"Error extracting audio: {error_msg}")
                QCoreApplication.processEvents()  # Force UI update
                return None
                
            # Get the duration of the audio file
            if os.path.exists(output_path):
                try:
                    with wave.open(output_path, 'rb') as wf:
                        # Calculate duration from wave file properties
                        frames = wf.getnframes()
                        rate = wf.getframerate()
                        duration = frames / float(rate)
                        print(f"Extracted audio duration: {duration:.2f} seconds")
                        
                        # Store the duration for later use in timestamp validation
                        self.current_audio_duration = duration
                except Exception as e:
                    print(f"Error reading audio duration: {str(e)}")
            
                print(f"Audio extracted successfully to {output_path}")
                # Add to temp files list for later cleanup
                if output_path not in self.temp_audio_files:
                    self.temp_audio_files.append(output_path)
                return output_path
            else:
                print(f"Output audio file not found: {output_path}")
                return None
        except Exception as e:
            print(f"Error during audio extraction: {str(e)}")
            import traceback
            traceback.print_exc()
            self.status_label.setText(f"Error during audio extraction: {str(e)}")
            QCoreApplication.processEvents()  # Force UI update
            return None

    def _show_inline_toast(self, message, duration_ms=5000):
        """Show a simple toast message in the top-right corner with a close button"""
        # Create toast frame
        toast = QFrame(self)
        toast.setStyleSheet("""
            QFrame {
                background-color: rgba(46, 125, 50, 178);
                color: white;
                border-radius: 4px 4px 0px 0px; /* Round only the top corners */
                border: none;
            }
            QProgressBar {
                background: transparent;
                border: none;
                height: 2px;
                max-height: 2px;
                min-height: 2px;
                margin: 0px;
                padding: 0px;
                border-radius: 0px;
            }
            QProgressBar::chunk {
                background-color: rgba(200, 255, 200, 255);
            }
            QLabel {
                background-color: transparent;
                color: white;
                font-weight: bold;
            }
            QPushButton {
                background-color: transparent;
                color: white;
                border: none;
                font-weight: bold;
                font-size: 14px;
                min-width: 22px;
                min-height: 22px;
                max-width: 22px;
                max-height: 22px;
                padding: 0px;
                margin: 0px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 50);
                border-radius: 11px;
            }
        """)
        
        # Create main layout
        main_layout = QVBoxLayout(toast)
        main_layout.setContentsMargins(0, 0, 0, 0)  # No margins at all
        main_layout.setSpacing(0)  # No spacing between elements
        
        # Create content widget
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)  # Use horizontal layout for content
        content_layout.setContentsMargins(16, 8, 16, 8)  # Left, top, right, bottom padding
        
        # Add message label
        label = QLabel(message)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter)  # Center text vertically
        content_layout.addWidget(label, 1)  # Add stretch factor to push close button to right
        
        # Create a flag to track if toast is manually closed
        toast.is_closing = False
        
        # Function to safely close the toast
        def close_toast():
            # Set the flag to prevent auto-close timer from triggering
            toast.is_closing = True
            # Stop the progress timer
            if hasattr(toast, 'timer') and toast.timer:
                toast.timer.stop()
            # Delete the toast
            toast.deleteLater()
        
        # Add close button
        close_button = QPushButton("✕")  # Unicode X character
        close_button.setFixedSize(22, 22)  # Set fixed size
        close_button.setToolTip("Close")
        close_button.setCursor(Qt.CursorShape.PointingHandCursor)  # Change cursor on hover
        content_layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        content_layout.setSpacing(10)  # Add spacing between label and button
        
        # Connect close button to the safe close function
        close_button.clicked.connect(close_toast)
        
        # Add content widget to main layout
        main_layout.addWidget(content_widget)
        
        # Add progress bar at the bottom
        progress = QProgressBar()
        progress.setMaximum(1000)  # Increase resolution for smoother animation
        progress.setValue(1000)
        progress.setTextVisible(False)
        progress.setFixedHeight(2)  # Force height to be exactly 2px
        progress.setContentsMargins(0, 0, 0, 0)  # No margins for the progress bar
        main_layout.addWidget(progress, 0, Qt.AlignmentFlag.AlignBottom)  # Align at bottom
        
        # Set minimum width to ensure it's more rectangular
        toast.setMinimumWidth(300)
        
        # Show the toast
        toast.show()
        toast.adjustSize()
        
        # Position in top-right corner
        toast.move(self.width() - toast.width() - 20, 20)
        toast.raise_()
        
        # Setup animation parameters
        update_interval = 16  # Update every ~16ms (60fps) for smooth animation
        remaining_time = duration_ms
        decrements_per_second = 1000 / update_interval  # Number of updates per second
        decrement_per_step = 1000 / (duration_ms / update_interval)  # Amount to decrement per step
        
        # Timer for progress bar
        timer = QTimer(toast)
        
        # Using a property animation for smoother progress
        progress_value = 1000
        
        def update_progress():
            nonlocal progress_value, remaining_time
            
            # Calculate smooth decrement
            remaining_time -= update_interval
            progress_value -= decrement_per_step
            
            # Apply with bounds checking
            if progress_value < 0:
                progress_value = 0
                
            progress.setValue(int(progress_value))
            
            if remaining_time <= 0 or progress_value <= 0:
                timer.stop()
        
        timer.timeout.connect(update_progress)
        timer.start(update_interval)
        
        # Store timer reference as property of toast to prevent garbage collection
        toast.timer = timer
        
        # Auto-close timer with safe closure check
        def auto_close():
            # Only close if not already being closed
            if not toast.is_closing and not toast.isHidden():
                close_toast()
        
        # Use QTimer for auto-close
        auto_close_timer = QTimer(toast)
        auto_close_timer.setSingleShot(True)
        auto_close_timer.timeout.connect(auto_close)
        auto_close_timer.start(duration_ms)
        
        # Store the auto-close timer reference
        toast.auto_close_timer = auto_close_timer
        
        return toast

    def set_dark_mode(self, enabled: bool):
        """Set dark mode for the SRT generation view"""
        self.dark_mode_active = enabled
        
        # Apply dark mode to the drop area
        if hasattr(self, 'drop_area'):
            self.drop_area.set_dark_mode(enabled)
            
        # Apply dark mode to the file list and other components
        if enabled:
            self.setStyleSheet("""
                QWidget#SrtGenerationView {
                    background-color: #121212;
                    color: #e0e0e0;
                }
                QListWidget {
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
                    background-color: #3d3d3d;
                }
                QLineEdit, QTextEdit, QPlainTextEdit, QLabel {
                    background-color: #1e1e1e;
                    color: #e0e0e0;
                    border: 1px solid #3d3d3d;
                }
                QComboBox {
                    background-color: #1e1e1e;
                    color: #e0e0e0;
                    border: 1px solid #3d3d3d;
                    border-radius: 5px;
                    padding: 8px 25px 8px 8px;
                }
                QComboBox:hover {
                    background-color: #3d3d3d;
                }
                QComboBox::drop-down {
                    border: none;
                    width: 20px;
                    border-radius: 5px;
                    background-color: transparent;
                }
                QComboBox::down-arrow {
                    image: url(src/icons/down_arrow_white.svg);
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
            """)
        else:
            # Light mode styling
            self.setStyleSheet("""
                QPushButton { 
                    border-radius: 5px;
                    padding: 5px;
                    border: 1px solid #ccc;
                    background-color: #f8f9fa;
                }
                QPushButton:hover {
                    background-color: #e9ecef;
                }
                QListWidget {
                    border: 1px solid #ddd;
                    border-radius: 5px;
                    background-color: white;
                }
                QLineEdit, QTextEdit, QPlainTextEdit {
                    border: 1px solid #ccc;
                    border-radius: 5px;
                    padding: 5px;
                    background-color: white;
                }
                QComboBox {
                    border-radius: 5px;
                    padding: 8px 25px 8px 8px;
                    border: 1px solid #ccc;
                    min-width: 6em;
                    background-color: white;
                }
                QComboBox:hover {
                    background-color: #f0f0f0;
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
                QProgressBar {
                    border: 1px solid #ccc;
                    border-radius: 3px;
                    text-align: center;
                }
                QProgressBar::chunk {
                    background-color: #4CAF50;
                    width: 10px;
                }
            """)

class SimpleUtterance:
    """Simple class to represent an utterance with text and timing"""
    def __init__(self, text, start=0, end=0):
        self.text = text
        self.start = start
        self.end = end
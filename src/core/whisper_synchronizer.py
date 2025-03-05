import os
import torch
import whisperx  # type: ignore
from typing import List, Tuple, Optional, Dict, Any
import gc
import time


class WhisperSynchronizer:
    """
    A subtitle synchronizer that uses WhisperX to provide high-accuracy forced alignment
    between audio and text.
    """
    
    def __init__(self, 
                 model_size: str = "base", 
                 compute_type: str = "float16",
                 language: str = "en",
                 timeout: int = 300):  # 5 minute timeout
        """
        Initialize the WhisperSynchronizer with the specified parameters.
        
        Args:
            model_size: The Whisper model size to use ('tiny', 'base', 'small', 'medium', 'large', 'large-v2', 'large-v3')
            compute_type: The compute type to use ('float16', 'float32', 'int8') - use int8 for lower memory usage
            language: The language code for the audio (e.g., 'en', 'fr', 'de', etc.)
            timeout: Maximum time in seconds to allow for synchronization
        """
        self.model_size = model_size
        self.compute_type = compute_type
        self.language = language
        self.timeout = timeout
        # Use GPU if available, otherwise CPU
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"WhisperSynchronizer initialized with device: {self.device}, model: {model_size}, compute: {compute_type}")
        
    def synchronize(self, 
                   audio_file: str, 
                   subtitle_intervals: List[Tuple[float, float]], 
                   subtitle_texts: List[str],
                   audio_duration: Optional[float] = None) -> List[Tuple[float, float]]:
        """
        Synchronize subtitle intervals with audio using WhisperX forced alignment.
        
        Args:
            audio_file: Path to the audio file
            subtitle_intervals: List of (start_time, end_time) tuples in seconds
            subtitle_texts: List of subtitle text segments corresponding to the intervals
            audio_duration: Optional audio duration in seconds
            
        Returns:
            List of synchronized (start_time, end_time) tuples
        """
        # Set start time for timeout tracking
        start_time = time.time()
        
        # Check inputs
        if not os.path.exists(audio_file):
            print(f"Audio file not found: {audio_file}")
            return subtitle_intervals
            
        if len(subtitle_intervals) != len(subtitle_texts):
            print(f"Mismatch between intervals ({len(subtitle_intervals)}) and texts ({len(subtitle_texts)})")
            return subtitle_intervals
            
        if not subtitle_intervals:
            print("No subtitle intervals provided for synchronization")
            return []
            
        try:
            print(f"Loading audio file: {audio_file}")
            # Load audio
            audio = whisperx.load_audio(audio_file)
            
            # Get actual audio duration
            actual_audio_duration = len(audio) / 16000  # WhisperX uses 16kHz sample rate
            print(f"Actual audio duration: {actual_audio_duration:.2f} seconds")
            
            # If provided audio_duration differs significantly from actual, use the actual
            if audio_duration and abs(audio_duration - actual_audio_duration) > 5:
                print(f"Warning: Provided duration ({audio_duration:.2f}s) differs from actual ({actual_audio_duration:.2f}s). Using actual.")
                audio_duration = actual_audio_duration
            elif not audio_duration:
                audio_duration = actual_audio_duration
                
            # Check if we've exceeded the timeout
            if time.time() - start_time > self.timeout:
                print(f"Timeout exceeded during audio loading ({self.timeout}s)")
                return subtitle_intervals
                
            print(f"Loading whisper model: {self.model_size} on {self.device}")
            # Try to load the model with the specified compute type
            try:
                model = whisperx.load_model(self.model_size, self.device, compute_type=self.compute_type)
            except RuntimeError as e:
                # If float16 fails, try with float32
                if "float16" in str(e) and self.compute_type == "float16":
                    print("Float16 not supported on this device, falling back to float32")
                    self.compute_type = "float32"
                    model = whisperx.load_model(self.model_size, self.device, compute_type="float32")
                else:
                    # Re-raise if it's not a float16 issue
                    raise
            
            # Check if we've exceeded the timeout
            if time.time() - start_time > self.timeout:
                print(f"Timeout exceeded during model loading ({self.timeout}s)")
                del model
                self._cleanup_gpu()
                return subtitle_intervals
            
            # Create segments from our subtitle intervals and texts
            segments = []
            for i, ((start, end), text) in enumerate(zip(subtitle_intervals, subtitle_texts)):
                if text.strip():  # Skip empty segments
                    segments.append({
                        "id": i,
                        "start": start,
                        "end": end,
                        "text": text
                    })
            
            # Prepare result structure
            result = {"segments": segments}
            
            # Check if we've exceeded the timeout
            if time.time() - start_time > self.timeout:
                print(f"Timeout exceeded during segment preparation ({self.timeout}s)")
                del model
                self._cleanup_gpu()
                return subtitle_intervals
            
            print(f"Loading align model for language: {self.language}")
            # Load align model
            model_a, metadata = whisperx.load_align_model(language_code=self.language, device=self.device)
            
            # Check if we've exceeded the timeout
            if time.time() - start_time > self.timeout:
                print(f"Timeout exceeded during align model loading ({self.timeout}s)")
                del model
                del model_a
                self._cleanup_gpu()
                return subtitle_intervals
            
            print("Aligning segments with audio")
            # Align using whisperx
            aligned_result = whisperx.align(result["segments"], model_a, metadata, audio, self.device, 
                                          return_char_alignments=False)
            
            # Extract aligned timestamps
            aligned_intervals = []
            for seg in aligned_result["segments"]:
                aligned_intervals.append((seg["start"], seg["end"]))
            
            print(f"Alignment complete. Aligned {len(aligned_intervals)} segments")
            
            # Scale check - make sure the synchronized timestamps don't exceed audio duration
            if aligned_intervals and audio_duration:
                # Find max timestamp
                last_end = max([end for _, end in aligned_intervals]) if aligned_intervals else 0
                
                # Check if timestamps are unreasonably large compared to audio duration
                # This detects both slight overruns and massive scaling issues
                if last_end > audio_duration * 1.1:  # More aggressive threshold (was 1.2)
                    print(f"Warning: Synchronized timestamps exceed audio duration")
                    print(f"Last timestamp: {last_end:.2f}s, Audio duration: {audio_duration:.2f}s")
                    print("Scaling timestamps to match audio duration...")
                    
                    # Calculate scaling factor
                    scale_factor = audio_duration / last_end
                    print(f"Applying scaling factor of {scale_factor:.6f}")
                    
                    # Apply scaling to all intervals
                    aligned_intervals = [(start * scale_factor, end * scale_factor) 
                                        for start, end in aligned_intervals]
                
                # Second verification - check if any timestamps are still outside valid range
                # This catches individual outliers that might not be fixed by scaling
                valid_intervals = []
                for start, end in aligned_intervals:
                    # Ensure start time is not negative
                    start = max(0, start)
                    # Ensure end time doesn't exceed audio duration
                    end = min(end, audio_duration)
                    # Ensure minimum segment length
                    if end - start < 0.1:  # Minimum 100ms segment
                        end = min(start + 0.1, audio_duration)
                    valid_intervals.append((start, end))
                
                aligned_intervals = valid_intervals
                print(f"Final timestamp range: {min([start for start, _ in aligned_intervals]):.2f}s - {max([end for _, end in aligned_intervals]):.2f}s")
            
            # Detect truly unreasonable timestamps (hours instead of seconds)
            # This is a last resort check for extreme scaling issues
            max_reasonable_time = 60 * 60  # 1 hour is unreasonable for most videos
            if aligned_intervals and any(end > max_reasonable_time for _, end in aligned_intervals):
                print("ERROR: Detected unreasonably large timestamps (> 1 hour)")
                print("Forcing rescale to audio duration")
                
                # Force linear distribution across audio duration
                total_segments = len(aligned_intervals)
                if total_segments > 0 and audio_duration:
                    segment_duration = audio_duration / total_segments
                    aligned_intervals = [
                        (i * segment_duration, min((i + 1) * segment_duration, audio_duration))
                        for i in range(total_segments)
                    ]
                    print(f"Applied emergency timestamp correction - distributed {total_segments} segments across {audio_duration:.2f}s")
            
            # Clean up to free memory
            del model
            del model_a
            self._cleanup_gpu()
            
            return aligned_intervals
            
        except Exception as e:
            print(f"WhisperX synchronization failed: {str(e)}")
            # Cleanup after exception
            self._cleanup_gpu()
            # Return original intervals if alignment fails
            return subtitle_intervals
            
    def _cleanup_gpu(self):
        """Free GPU memory after processing"""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
                print("GPU memory cleared successfully")
        except Exception as e:
            print(f"Error cleaning up GPU memory: {e}")
    
    def detect_language(self, audio_file: str) -> str:
        """
        Detect the language of the audio file using WhisperX.
        
        Args:
            audio_file: Path to the audio file
            
        Returns:
            Language code (e.g., 'en', 'fr', 'de', etc.)
        """
        try:
            # Set start time for timeout tracking
            start_time = time.time()
            
            print(f"Loading audio for language detection: {audio_file}")
            # Load audio
            audio = whisperx.load_audio(audio_file)
            
            # Check if we've exceeded the timeout
            if time.time() - start_time > self.timeout:
                print(f"Timeout exceeded during audio loading ({self.timeout}s)")
                return "en"
                
            print("Loading whisper model for language detection (using small)")
            # Load whisper model (use small for language detection)
            model = whisperx.load_model("small", self.device, compute_type=self.compute_type)
            
            # Check if we've exceeded the timeout
            if time.time() - start_time > self.timeout:
                print(f"Timeout exceeded during model loading ({self.timeout}s)")
                del model
                self._cleanup_gpu()
                return "en"
            
            print("Detecting language...")
            # Detect language
            result = model.transcribe(audio, language=None)  # Set language to None to detect
            detected_language = result.get("language", "en")  # Default to English
            print(f"Detected language: {detected_language}")
            
            # Clean up
            del model
            self._cleanup_gpu()
            
            return detected_language
            
        except Exception as e:
            print(f"Language detection failed: {str(e)}")
            # Cleanup after exception
            self._cleanup_gpu()
            return "en"  # Default to English on failure 
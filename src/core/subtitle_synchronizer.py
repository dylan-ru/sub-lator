import os
import numpy as np
import subprocess
import math
import tempfile
from typing import List, Tuple, Dict, Any, Optional
from scipy import signal
from scipy.io import wavfile

class SubtitleSynchronizer:
    """Class for synchronizing subtitles with audio using advanced techniques."""
    
    def __init__(self, 
                 window_size_ms: int = 10, 
                 use_dtw: bool = True,
                 max_offset_seconds: float = 10.0):
        """Initialize the subtitle synchronizer.
        
        Args:
            window_size_ms: Size of time window in milliseconds for discretization
            use_dtw: Whether to use dynamic time warping for fine alignment
            max_offset_seconds: Maximum offset to consider for global alignment
        """
        self.window_size_ms = window_size_ms
        self.use_dtw = use_dtw
        self.max_offset_seconds = max_offset_seconds
        
    def extract_audio_features(self, audio_file: str) -> np.ndarray:
        """Extract voice activity features from the audio file."""
        # Convert to WAV if needed
        temp_wav = None
        if not audio_file.lower().endswith('.wav'):
            temp_wav = tempfile.NamedTemporaryFile(suffix='.wav', delete=False)
            ffmpeg_cmd = [
                'ffmpeg', '-i', audio_file, 
                '-ac', '1', '-ar', '16000',  # Mono, 16kHz
                '-hide_banner', '-loglevel', 'error',
                temp_wav.name
            ]
            subprocess.run(ffmpeg_cmd, check=True)
            audio_file = temp_wav.name
        
        # Read audio file
        sample_rate, audio = wavfile.read(audio_file)
        
        # Normalize audio
        if audio.dtype != np.float32:
            audio = audio.astype(np.float32)
            if np.max(np.abs(audio)) > 0:
                audio = audio / np.max(np.abs(audio))
        
        # Calculate window size in samples
        window_size = int(self.window_size_ms * sample_rate / 1000)
        
        # Perform voice activity detection
        # Simple energy-based approach
        energy = np.array([
            np.sum(np.square(audio[i:i+window_size])) / window_size 
            for i in range(0, len(audio), window_size)
        ])
        
        # Apply dynamic threshold
        threshold = 0.05 * np.max(energy)
        vad = (energy > threshold).astype(int)
        
        # Clean up temp file if created
        if temp_wav:
            os.unlink(temp_wav.name)
            
        return vad
        
    def create_subtitle_signal(self, 
                              subtitle_intervals: List[Tuple[float, float]], 
                              audio_duration: float) -> np.ndarray:
        """Create a binary signal from subtitle intervals."""
        # Number of windows
        n_windows = int(audio_duration * 1000 / self.window_size_ms)
        subtitle_signal = np.zeros(n_windows)
        
        for start_time, end_time in subtitle_intervals:
            # Convert times to window indices
            start_idx = int(start_time * 1000 / self.window_size_ms)
            end_idx = int(end_time * 1000 / self.window_size_ms)
            
            # Make sure indices are within bounds
            start_idx = max(0, min(start_idx, n_windows - 1))
            end_idx = max(0, min(end_idx, n_windows))
            
            # Set signal to 1 for these windows
            subtitle_signal[start_idx:end_idx] = 1
            
        return subtitle_signal
        
    def find_global_offset(self, 
                          audio_signal: np.ndarray, 
                          subtitle_signal: np.ndarray) -> float:
        """Find the global offset between audio and subtitles using FFT-based cross-correlation."""
        # Ensure both signals have data
        if len(audio_signal) == 0 or len(subtitle_signal) == 0:
            return 0.0
            
        # Pad the shorter signal
        max_len = max(len(audio_signal), len(subtitle_signal))
        if len(audio_signal) < max_len:
            audio_signal = np.pad(audio_signal, (0, max_len - len(audio_signal)), 'constant')
        if len(subtitle_signal) < max_len:
            subtitle_signal = np.pad(subtitle_signal, (0, max_len - len(subtitle_signal)), 'constant')
        
        # Calculate cross-correlation using FFT
        correlation = signal.correlate(audio_signal, subtitle_signal, mode='full')
        
        # Find the index with maximum correlation
        max_idx = np.argmax(correlation)
        
        # Calculate offset in windows
        offset_windows = max_idx - len(subtitle_signal) + 1
        
        # Convert to seconds
        offset_seconds = offset_windows * self.window_size_ms / 1000
        
        # Limit to max offset
        if abs(offset_seconds) > self.max_offset_seconds:
            offset_seconds = 0.0
            
        return offset_seconds
    
    def apply_dynamic_time_warping(self, 
                                  audio_signal: np.ndarray, 
                                  subtitle_signal: np.ndarray) -> List[Tuple[int, int]]:
        """Apply dynamic time warping to find optimal alignment between signals."""
        # This is a simplified implementation of DTW
        n, m = len(audio_signal), len(subtitle_signal)
        
        # Initialize cost matrix
        cost = np.zeros((n + 1, m + 1))
        cost[0, 0] = 0
        cost[0, 1:] = np.inf
        cost[1:, 0] = np.inf
        
        # Fill cost matrix
        for i in range(1, n + 1):
            for j in range(1, m + 1):
                # Cost is 0 if both signals have the same value, 1 otherwise
                match_cost = 0 if audio_signal[i-1] == subtitle_signal[j-1] else 1
                cost[i, j] = match_cost + min(cost[i-1, j], cost[i, j-1], cost[i-1, j-1])
        
        # Backtrack to find path
        path = []
        i, j = n, m
        while i > 0 and j > 0:
            path.append((i-1, j-1))
            min_cost = min(cost[i-1, j], cost[i, j-1], cost[i-1, j-1])
            if min_cost == cost[i-1, j-1]:
                i -= 1
                j -= 1
            elif min_cost == cost[i-1, j]:
                i -= 1
            else:
                j -= 1
                
        path.reverse()
        return path
        
    def adjust_timings(self, 
                      subtitle_intervals: List[Tuple[float, float]], 
                      offset: float,
                      dtw_path: Optional[List[Tuple[int, int]]] = None,
                      audio_duration: Optional[float] = None) -> List[Tuple[float, float]]:
        """Adjust subtitle timings based on global offset and DTW path."""
        if dtw_path is None or not self.use_dtw:
            # Simple offset adjustment
            adjusted = [(max(0.0, start + offset), 
                        end + offset if audio_duration is None else min(audio_duration, end + offset)) 
                        for start, end in subtitle_intervals]
            return adjusted
        
        # Convert DTW path to a mapping function
        # Each point (i,j) in the path means audio frame i corresponds to subtitle frame j
        window_time = self.window_size_ms / 1000  # Time per window in seconds
        
        # Create a mapping from subtitle time to audio time
        subtitle_to_audio = {}
        for audio_idx, sub_idx in dtw_path:
            subtitle_time = sub_idx * window_time
            audio_time = audio_idx * window_time
            subtitle_to_audio[subtitle_time] = audio_time
        
        # For each subtitle interval, find the closest matching points in the DTW path
        adjusted_intervals = []
        for start_time, end_time in subtitle_intervals:
            # Find closest subtitle times in our mapping
            closest_start = min(subtitle_to_audio.keys(), key=lambda x: abs(x - start_time), default=start_time)
            closest_end = min(subtitle_to_audio.keys(), key=lambda x: abs(x - end_time), default=end_time)
            
            # Get corresponding audio times
            adjusted_start = subtitle_to_audio.get(closest_start, start_time + offset)
            adjusted_end = subtitle_to_audio.get(closest_end, end_time + offset)
            
            # Ensure start < end and times are within bounds
            adjusted_start = max(0.0, adjusted_start)
            if audio_duration is not None:
                adjusted_end = min(audio_duration, adjusted_end)
                
            # Ensure minimum duration
            if adjusted_end - adjusted_start < 0.1:
                adjusted_end = adjusted_start + 0.1
                
            adjusted_intervals.append((adjusted_start, adjusted_end))
            
        return adjusted_intervals
                
    def synchronize(self, 
                   audio_file: str, 
                   subtitle_intervals: List[Tuple[float, float]], 
                   audio_duration: Optional[float] = None) -> List[Tuple[float, float]]:
        """Synchronize subtitles with audio.
        
        Args:
            audio_file: Path to the audio file
            subtitle_intervals: List of (start_time, end_time) tuples in seconds
            audio_duration: Duration of the audio in seconds (optional)
            
        Returns:
            List of adjusted (start_time, end_time) tuples
        """
        try:
            # Extract features from audio
            audio_signal = self.extract_audio_features(audio_file)
            
            # Determine audio duration if not provided
            if audio_duration is None:
                try:
                    result = subprocess.run([
                        'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                        '-of', 'default=noprint_wrappers=1:nokey=1', audio_file
                    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    audio_duration = float(result.stdout.strip())
                except:
                    # If we can't get duration, estimate from the signal
                    audio_duration = len(audio_signal) * self.window_size_ms / 1000
            
            # Create subtitle signal
            subtitle_signal = self.create_subtitle_signal(subtitle_intervals, audio_duration)
            
            # Find global offset
            offset = self.find_global_offset(audio_signal, subtitle_signal)
            
            # Apply DTW if enabled
            dtw_path = None
            if self.use_dtw:
                try:
                    # Apply global offset to subtitle signal first
                    offset_windows = int(offset * 1000 / self.window_size_ms)
                    if offset_windows > 0:
                        adjusted_subtitle_signal = np.pad(subtitle_signal, (offset_windows, 0), 'constant')[:-offset_windows if offset_windows < len(subtitle_signal) else None]
                    elif offset_windows < 0:
                        adjusted_subtitle_signal = np.pad(subtitle_signal, (0, -offset_windows), 'constant')[-offset_windows:]
                    else:
                        adjusted_subtitle_signal = subtitle_signal
                        
                    # Ensure signals are the same length for DTW
                    min_len = min(len(audio_signal), len(adjusted_subtitle_signal))
                    audio_signal_subset = audio_signal[:min_len]
                    adjusted_subtitle_signal = adjusted_subtitle_signal[:min_len]
                    
                    # Perform DTW on the synchronized signals
                    dtw_path = self.apply_dynamic_time_warping(audio_signal_subset, adjusted_subtitle_signal)
                except Exception as e:
                    print(f"DTW failed: {str(e)}")
                    dtw_path = None
            
            # Adjust subtitle timings
            adjusted_intervals = self.adjust_timings(subtitle_intervals, offset, dtw_path, audio_duration)
            
            return adjusted_intervals
            
        except Exception as e:
            print(f"Synchronization failed: {str(e)}")
            # Return original intervals if synchronization fails
            return subtitle_intervals 
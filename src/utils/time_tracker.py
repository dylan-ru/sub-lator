import time
from collections import defaultdict
from typing import Dict, List, Optional, Tuple


class ProcessTimeTracker:
    """
    A class to track processing time for different phases of video processing
    and estimate remaining time for batch operations.
    """
    
    def __init__(self, total_videos: int):
        """
        Initialize the time tracker.
        
        Args:
            total_videos: Total number of videos to be processed
        """
        self.total_videos = total_videos
        self.completed_videos = 0
        self.current_phase = None
        self.current_video = None
        self.phase_start_time = 0
        
        # Store timing data for different phases
        self.phase_times = defaultdict(list)  # phase_name -> list of durations
        self.video_durations = {}  # video_path -> duration in seconds
        self.video_processing_times = {}  # video_path -> total processing time
        
        # Track overall process timing
        self.process_start_time = time.time()
        
    def start_phase(self, phase_name: str, video_path: str, video_duration: Optional[float] = None):
        """
        Start timing a specific processing phase for a video.
        
        Args:
            phase_name: Name of the processing phase (e.g., 'extraction', 'transcription')
            video_path: Path to the video being processed
            video_duration: Duration of the video in seconds (if available)
        """
        self.current_phase = phase_name
        self.current_video = video_path
        self.phase_start_time = time.time()
        
        # Store video duration if provided
        if video_duration is not None:
            self.video_durations[video_path] = video_duration
    
    def end_phase(self, success: bool = True):
        """
        End timing for the current phase.
        
        Args:
            success: Whether the phase completed successfully
        """
        if not self.current_phase or not self.current_video:
            return
            
        # Only record timing if the phase was successful
        if success:
            duration = time.time() - self.phase_start_time
            self.phase_times[self.current_phase].append(duration)
            
            # Update total processing time for this video
            if self.current_video not in self.video_processing_times:
                self.video_processing_times[self.current_video] = 0
            self.video_processing_times[self.current_video] += duration
        
        # Reset current phase
        self.current_phase = None
    
    def complete_video(self, video_path: str):
        """
        Mark a video as completely processed.
        
        Args:
            video_path: Path to the completed video
        """
        self.completed_videos += 1
    
    def get_average_phase_time(self, phase_name: str) -> Optional[float]:
        """
        Get the average time for a specific processing phase.
        
        Args:
            phase_name: Name of the processing phase
            
        Returns:
            Average time in seconds or None if no data
        """
        times = self.phase_times.get(phase_name, [])
        if not times:
            return None
        return sum(times) / len(times)
    
    def get_average_processing_time_per_video(self) -> Optional[float]:
        """
        Get the average total processing time per video.
        
        Returns:
            Average time in seconds or None if no data
        """
        if not self.video_processing_times:
            return None
        return sum(self.video_processing_times.values()) / len(self.video_processing_times)
    
    def get_average_processing_time_per_second(self) -> Optional[float]:
        """
        Get the average processing time per second of video.
        
        Returns:
            Average processing time per second of video or None if no data
        """
        total_processing_time = sum(self.video_processing_times.values())
        total_video_duration = sum(duration for video, duration in self.video_durations.items() 
                                  if video in self.video_processing_times and duration is not None)
        
        if total_video_duration <= 0:
            return None
            
        return total_processing_time / total_video_duration
    
    def estimate_remaining_time(self) -> Optional[float]:
        """
        Estimate the remaining time for the entire process.
        
        Returns:
            Estimated remaining time in seconds or None if unable to estimate
        """
        # If no videos completed yet, can't estimate
        if self.completed_videos == 0:
            return None
            
        # If all videos completed, no time remaining
        if self.completed_videos >= self.total_videos:
            return 0
            
        # Calculate based on average time per video
        avg_time_per_video = self.get_average_processing_time_per_video()
        if avg_time_per_video is not None:
            remaining_videos = self.total_videos - self.completed_videos
            return avg_time_per_video * remaining_videos
            
        # Fallback to elapsed time divided by completion percentage
        elapsed_time = time.time() - self.process_start_time
        completion_percentage = self.completed_videos / self.total_videos
        if completion_percentage > 0:
            total_estimated_time = elapsed_time / completion_percentage
            return total_estimated_time - elapsed_time
            
        return None
    
    def get_statistics(self) -> Dict:
        """
        Get statistics about the processing times.
        
        Returns:
            Dictionary with processing statistics
        """
        stats = {
            "total_videos": self.total_videos,
            "completed_videos": self.completed_videos,
            "elapsed_time": time.time() - self.process_start_time,
            "average_time_per_video": self.get_average_processing_time_per_video(),
            "phase_averages": {phase: self.get_average_phase_time(phase) 
                              for phase in self.phase_times.keys()},
            "estimated_remaining_time": self.estimate_remaining_time()
        }
        return stats 
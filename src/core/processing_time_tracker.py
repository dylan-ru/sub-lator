import time

class ProcessingTimeTracker:
    """Tracks processing times and calculates remaining time estimates."""
    
    def __init__(self, total_videos, total_video_duration=None):
        """
        Initialize the time tracker.
        
        Args:
            total_videos: Total number of videos to process
            total_video_duration: Total duration of videos in seconds (if known)
        """
        self.total_videos = total_videos
        self.total_video_duration = total_video_duration
        self.completed_videos = 0
        
        # Phase tracking for current video
        self.current_video_path = None
        self.current_video_duration = None
        self.current_phase = None
        self.phase_start_time = None
        
        # Historic data for time estimation
        self.extraction_time_per_sec = None  # Time to extract 1s of video
        self.transcription_time_per_sec = None  # Time to transcribe 1s of audio
        self.formatting_time_per_sec = None  # Time to format 1s of transcript
        
        # Overall tracking
        self.process_start_time = time.time()
        self.estimated_finish_time = None
        
        # Phase definitions with default coefficients
        self.phases = {
            'extraction': {'weight': 0.05, 'time_per_sec': 0.1},  # Extraction is fast
            'transcription': {'weight': 0.85, 'time_per_sec': 0.4},  # Transcription takes most time
            'formatting': {'weight': 0.10, 'time_per_sec': 0.05}   # Formatting is relatively quick
        }
        
    def start_phase(self, phase_name, video_path, video_duration=None):
        """
        Start timing a processing phase.
        
        Args:
            phase_name: Name of the phase ('extraction', 'transcription', 'formatting')
            video_path: Path to the current video
            video_duration: Duration of the video in seconds (if known)
        """
        self.current_phase = phase_name
        self.current_video_path = video_path
        self.current_video_duration = video_duration
        self.phase_start_time = time.time()
        
    def end_phase(self, success=True):
        """
        End timing for the current phase and update metrics.
        
        Args:
            success: Whether the phase completed successfully
        
        Returns:
            Elapsed time for the phase in seconds
        """
        if not self.phase_start_time or not self.current_phase:
            return 0
            
        elapsed = time.time() - self.phase_start_time
        
        # Update time_per_sec metrics for this phase if we know the video duration
        if success and self.current_video_duration and self.current_video_duration > 0:
            phase_key = f"{self.current_phase}_time_per_sec"
            current_time_per_sec = elapsed / self.current_video_duration
            
            # Update the rolling average
            if getattr(self, phase_key) is None:
                setattr(self, phase_key, current_time_per_sec)
            else:
                # Use a weighted average favoring newer data (70% new, 30% old)
                old_value = getattr(self, phase_key)
                new_value = (current_time_per_sec * 0.7) + (old_value * 0.3)
                setattr(self, phase_key, new_value)
        
        # Update phase info
        self.phase_start_time = None
        last_phase = self.current_phase
        self.current_phase = None
        
        # If this was the formatting phase, we've completed a video
        if last_phase == 'formatting' and success:
            self.completed_videos += 1
            
        return elapsed
        
    def estimate_remaining_time(self, current_progress=None):
        """
        Estimate remaining processing time based on completed work and historic data.
        
        Args:
            current_progress: Current progress percentage within the current video/phase
            
        Returns:
            Dictionary with estimated seconds remaining, formatted time string,
            and confidence level ('low', 'medium', 'high')
        """
        # If we're just starting, return a placeholder
        if self.completed_videos == 0 and not self.current_phase:
            return {'seconds': None, 'text': 'Calculating...', 'confidence': 'low'}
            
        # Calculate elapsed time so far
        elapsed = time.time() - self.process_start_time
        
        # Case 1: We have good per-second timing data
        if (self.extraction_time_per_sec and 
            self.transcription_time_per_sec and 
            self.formatting_time_per_sec and 
            self.total_video_duration):
            
            # Calculate how much time we'll need for remaining videos
            remaining_duration = self.total_video_duration * (self.total_videos - self.completed_videos) / self.total_videos
            
            # Calculate remaining time based on our per-second rates
            remaining_extraction = remaining_duration * self.extraction_time_per_sec
            remaining_transcription = remaining_duration * self.transcription_time_per_sec
            remaining_formatting = remaining_duration * self.formatting_time_per_sec
            
            total_remaining = remaining_extraction + remaining_transcription + remaining_formatting
            confidence = 'high'
            
        # Case 2: Estimate based on elapsed time and progress so far
        else:
            work_done_ratio = self.completed_videos / self.total_videos
            if self.current_phase:
                # Add partial progress from current video
                phase_weights = {'extraction': 0.05, 'transcription': 0.85, 'formatting': 0.10}
                
                # Calculate completed work within the current video
                completed_phases_weight = 0
                for phase, weight in phase_weights.items():
                    if phase == self.current_phase:
                        break
                    completed_phases_weight += weight
                
                # Add current phase partial progress if we have it
                current_phase_progress = 0
                if current_progress is not None:
                    current_phase_progress = current_progress / 100.0 * phase_weights[self.current_phase]
                
                # Calculate total work progress including partial current video
                video_progress = (completed_phases_weight + current_phase_progress)
                work_done_ratio += video_progress / self.total_videos
            
            # Estimate based on time elapsed so far and work completed
            if work_done_ratio > 0:
                total_remaining = (elapsed / work_done_ratio) - elapsed
                confidence = 'medium'
            else:
                # Fall back to a very rough estimate
                total_remaining = elapsed * self.total_videos * 2  # Rough guess
                confidence = 'low'
        
        # Format the time string
        if total_remaining < 60:
            time_text = f"About {int(total_remaining)} seconds"
        elif total_remaining < 3600:
            time_text = f"About {int(total_remaining / 60)} minutes"
        else:
            hours = int(total_remaining / 3600)
            minutes = int((total_remaining % 3600) / 60)
            time_text = f"About {hours} hours, {minutes} minutes"
            
        return {
            'seconds': total_remaining,
            'text': time_text,
            'confidence': confidence
        } 
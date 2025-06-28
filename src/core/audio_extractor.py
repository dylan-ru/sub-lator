import subprocess
import os
import threading
import time
import re

def extract_audio(video_path, audio_path, progress_callback=None, status_callback=None):
    """
    Extracts audio from a video file using ffmpeg.
    
    Args:
        video_path: Path to the video file
        audio_path: Path to save the extracted audio
        progress_callback: Function to call with progress updates (0-100)
        status_callback: Function to call with status updates
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    
    # Report initial status
    if status_callback:
        status_callback("Starting audio extraction...")
    
    # Get video duration for progress calculation
    try:
        duration_cmd = [
            "ffmpeg",
            "-i", video_path,
            "-f", "null",
            "-"
        ]
        duration_output = subprocess.check_output(duration_cmd, stderr=subprocess.STDOUT, text=True)
        duration_match = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", duration_output)
        
        if duration_match:
            hours, minutes, seconds = map(float, duration_match.groups())
            total_duration = hours * 3600 + minutes * 60 + seconds
        else:
            total_duration = 0
            
    except subprocess.CalledProcessError:
        total_duration = 0
    
    command = [
        "ffmpeg",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        "-y",  # Overwrite output file if it exists
        audio_path
    ]
    
    # Create a process to run ffmpeg
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True
    )
    
    # Function to read output and update progress
    def read_output():
        if total_duration > 0 and progress_callback:
            for line in process.stdout:
                time_match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                if time_match:
                    hours, minutes, seconds = map(float, time_match.groups())
                    current_time = hours * 3600 + minutes * 60 + seconds
                    progress = min(int((current_time / total_duration) * 100), 100)
                    progress_callback(progress)
                    
                    if status_callback:
                        status_callback(f"Extracting audio... {progress}%")
        
        # Wait for process to complete
        return_code = process.wait()
        if return_code != 0:
            if status_callback:
                status_callback(f"Error extracting audio. Return code: {return_code}")
            raise RuntimeError(f"ffmpeg error: Return code {return_code}")
        else:
            if progress_callback:
                progress_callback(100)
            if status_callback:
                status_callback("Audio extraction complete")
    
    # Create a custom thread with terminate method
    class ExtractionThread(threading.Thread):
        def __init__(self, target):
            super().__init__(target=target)
            self.daemon = True
            self.process = process
            self.cancelled = False
            
        def terminate(self):
            """Terminate the ffmpeg process"""
            if self.process:
                try:
                    self.cancelled = True
                    # On Windows, use taskkill to forcefully terminate the process
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/F', '/T', '/PID', str(self.process.pid)], 
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        # On Unix-like systems, use regular termination
                        self.process.terminate()
                        # Give it a moment to terminate
                        self.process.wait(timeout=1)
                        # If not terminated, kill it
                        if self.process.poll() is None:
                            self.process.kill()
                    
                    print(f"Terminated ffmpeg process with PID {self.process.pid}")
                    return True
                except Exception as e:
                    print(f"Error terminating ffmpeg process: {str(e)}")
                    return False
            return False
    
    # Start reading output in a custom thread
    thread = ExtractionThread(target=read_output)
    thread.start()
    
    return thread  # Return the thread so caller can terminate it if needed 
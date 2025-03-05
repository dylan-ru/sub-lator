from PyQt6.QtCore import QThread, pyqtSignal
import asyncio
from typing import Callable, Any, Optional
from functools import partial
import concurrent.futures
import traceback

class AsyncWorker(QThread):
    """Worker thread for running async operations."""
    finished = pyqtSignal(object)
    error = pyqtSignal(object)
    progress = pyqtSignal(object)

    def __init__(self, coro: Callable, *args, **kwargs):
        super().__init__()
        self.coro = coro
        self.args = args
        self.kwargs = kwargs
        self.is_running = False
        self.loop = None
        self.future = None
        self.task = None
        
    def run(self):
        """Execute the coroutine in a new event loop."""
        self.is_running = True
        try:
            # Create new event loop for this thread
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            
            # Create and run the task
            self.task = self.loop.create_task(self.coro(*self.args, **self.kwargs))
            self.future = asyncio.ensure_future(self.task)
            result = self.loop.run_until_complete(self.future)
            
            # Emit result only if we're still running (not cancelled)
            if self.is_running:
                self.finished.emit(result)
        except asyncio.CancelledError:
            print("AsyncWorker task was cancelled")
        except Exception as e:
            if self.is_running:
                print(f"AsyncWorker encountered an error: {str(e)}")
                traceback.print_exc()
                self.error.emit(e)
        finally:
            # Clean up resources
            try:
                # Cancel any pending tasks
                if self.task and not self.task.done():
                    self.task.cancel()
                
                # Run the event loop once more to process any callbacks
                if self.loop and self.loop.is_running():
                    self.loop.stop()
                    
                # Close the loop
                if self.loop:
                    self.loop.run_until_complete(self.loop.shutdown_asyncgens())
                    self.loop.close()
            except Exception as e:
                print(f"Error during AsyncWorker cleanup: {str(e)}")
            
            self.is_running = False
    
    def stop(self):
        """Safely stop the worker thread."""
        if not self.is_running:
            return
            
        print("Stopping AsyncWorker thread...")
        self.is_running = False
        
        # Cancel the task if it's running
        if self.task and not self.task.done() and self.loop:
            self.loop.call_soon_threadsafe(self.task.cancel)
            
        # Wait for the thread to finish with a timeout
        self.wait(5000)  # 5 second timeout
        print("AsyncWorker thread stopped")

def run_async(coro: Callable, *args, on_success=None, on_error=None, **kwargs) -> AsyncWorker:
    """Run a coroutine asynchronously in a separate thread"""
    worker = AsyncWorker(coro, *args, **kwargs)
    
    # Connect the callback signals if provided
    if on_success:
        worker.finished.connect(on_success)
    if on_error:
        worker.error.connect(on_error)
        
    worker.start()
    return worker 
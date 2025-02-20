from PyQt6.QtCore import QThread, pyqtSignal
import asyncio
from typing import Callable, Any
from functools import partial

class AsyncWorker(QThread):
    """Worker thread for running async operations."""
    finished = pyqtSignal(object)
    error = pyqtSignal(Exception)
    progress = pyqtSignal(int)

    def __init__(self, coro: Callable, *args, **kwargs):
        super().__init__()
        self.coro = coro
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.coro(*self.args, **self.kwargs))
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(e)
        finally:
            loop.close()

def run_async(coro: Callable, *args, **kwargs) -> AsyncWorker:
    """Run an async operation in a separate thread."""
    worker = AsyncWorker(coro, *args, **kwargs)
    worker.start()
    return worker 
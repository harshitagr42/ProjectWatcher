# move/rename events will be treated as file create + file delete the time-tracking continuity will be 
# loss for that file and that is acceptable edge case since not all OS/filesystem reports a move/rename
# and i do not want it to be present for some OS/filesystem and not for others and i do not want to 
# implement a custom move/rename detection logic for other OS/filesystem that do not report it. 
# so for simplicity, i will treat move/rename as file create + file delete





# we need a way to track old events and by categories like created, modified, deleted, moved. so the app 
# will know for this path the file was creates or deleted or modified instead of guess what event occured
# for this path and notify the other processes that event(s) has occured

from watchdog.events import FileSystemEventHandler
from config import TRACKED_EXTENSIONS
from pathlib import Path
import time


class EventHandlerWrapper(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.last_created_path = None
        self.last_modified_path = None
        self.last_deleted_path = None
        self.modified_call_count = 0
        self.Throttle_counter = 0
        self._last_signal_time = {} # path (str) → timestamp (float)
        self.THROTTLE_SECONDS = 0.5 # seconds

    def on_created(self, event):
        if event.is_directory:
            return
        created_path = event.src_path
        
        if Path(created_path).suffix in TRACKED_EXTENSIONS:
            self.last_created_path = created_path
    
    def on_modified(self, event):
        if event.is_directory:
            return
        Modified_path = event.src_path
        
        if Path(Modified_path).suffix in TRACKED_EXTENSIONS:
            self.modified_call_count += 1
            temp = self._last_signal_time.get(Modified_path)
            if temp is None or (time.time() - temp) >= self.THROTTLE_SECONDS:
                self._last_signal_time[Modified_path] = time.time()
                self.last_modified_path = Modified_path
                self.Throttle_counter += 1

    def on_deleted(self, event):
        if event.is_directory:
            return
        deleted_path = event.src_path
        
        if Path(deleted_path).suffix in TRACKED_EXTENSIONS:
            self.last_deleted_path = deleted_path

    def on_moved(self, event):
        if event.is_directory:
            return
        old_path = event.src_path
        new_path = event.dest_path
        
        if Path(old_path).suffix in TRACKED_EXTENSIONS:
            self.last_deleted_path = old_path
        if Path(new_path).suffix in TRACKED_EXTENSIONS:
            self.last_created_path = new_path
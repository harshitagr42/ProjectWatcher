from watchdog.events import FileSystemEventHandler
from config import TRACKED_EXTENSIONS
from pathlib import Path


class EventHandlerWrapper(FileSystemEventHandler):
    def __init__(self):
        super().__init__()
        self.last_created_path = None
        self.last_modified_path = None
        self.last_deleted_path = None
        self.last_moved_paths = None

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
            self.last_modified_path = Modified_path

    def on_deleted(self, event):
        if event.is_directory:
            return
        deleted_path = event.src_path
        
        if Path(deleted_path).suffix in TRACKED_EXTENSIONS:
            self.last_deleted_path = deleted_path

    # rename that changes extension (temp.py → temp.swift) should be treated as a new file, not a rename, 
    # because the content/purpose fundamentally changed
    def on_moved(self, event):
        if event.is_directory:
            return
        original_path = event.src_path
        
        if (Path(original_path).suffix in TRACKED_EXTENSIONS 
            and Path(event.dest_path).suffix in TRACKED_EXTENSIONS 
            and Path(original_path).suffix == Path(event.dest_path).suffix):
            
            self.last_moved_paths = (event.src_path, event.dest_path)
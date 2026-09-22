import time
from pathlib import Path
from watchdog.observers import Observer
import pytest

from src.watcher import EventHandlerWrapper
from config import TRACKED_EXTENSIONS
from test.helpers import wait_until, wait_until_timeout


@pytest.fixture
def watcher(tmp_path):
    """
    Pytest fixture that creates a fresh EventHandlerWrapper and Observer instance
    for each test function, automatically starting and stopping the observer.
    """
    handler = EventHandlerWrapper()
    observer = Observer()
    observer.schedule(handler, str(tmp_path), recursive=True)
    observer.start()

    # Yield both handler and observer to the test function
    yield handler, observer, tmp_path

    # Clean teardown after test finishes
    observer.stop()
    observer.join()

# 1. Creating a file with a tracked extension inside a watched directory produces a "created" event.
def test_tracked_extension(watcher):
    handler, _, tmp_path = watcher

    (tmp_path / "parcel1.py").write_text("print('Hello')")
    created_path = wait_until(lambda: handler.last_created_path)

    assert Path(created_path).suffix in TRACKED_EXTENSIONS


# 2. Creating a file with an untracked extension produces no event at all.
def test_untracked_extension(watcher):
    handler, _, tmp_path = watcher

    (tmp_path / "parcel1.txt").write_text("print('Hello')")
    
    # Wait to ensure handler remains untouched (no created event produced)
    triggered = wait_until_timeout(lambda: handler.last_created_path is not None, timeout=0.3)
    assert not triggered

# 3. Modifying an existing tracked file produces a "modified" event.
def test_modified_tracked_file(watcher):
    handler, _, tmp_path = watcher

    file_path = tmp_path / "test.py"
    file_path.write_text("initial content")

    file_path.write_text("updated content")
    modified_path = wait_until(lambda: handler.last_modified_path)
    assert "test.py" in modified_path


# 4. Deleting a tracked file produces a "deleted" event.
def test_deleted_tracked_file(watcher):
    handler, _, tmp_path = watcher

    file_path = tmp_path / "test.py"
    file_path.write_text("to be deleted")

    file_path.unlink()
    deleted_path = wait_until(lambda: handler.last_deleted_path)
    assert Path(deleted_path).name == "test.py"


# 5-1. Rapid modifications collapse into a single logical "still active" signal (Throttle). for one file
def test_debounced_rapid_modifications_one_file(watcher):
    handler, _, tmp_path = watcher

    file_path = tmp_path / "rapid.py"
    file_path.write_text("v0")

    for i in range(5):
        file_path.write_text(f"v{i+1}")
        time.sleep(0.01)

    time.sleep(0.2)

    assert handler.Throttle_counter == 1
    assert handler.modified_call_count >= 1

# 5-2. Rapid modifications collapse into a single logical "still active" signal (Throttle). for multiple files
def test_debounced_rapid_modifications_multiple_files(watcher):
    handler, _, tmp_path = watcher

    file_1 = tmp_path / "rapid_1.py"
    file_1.write_text("v0")
    file_2 = tmp_path / "rapid_2.py"
    file_2.write_text("v0")

    for i in range(5):
        file_1.write_text(f"v{i+1}")
        time.sleep(0.001)
        file_2.write_text(f"v{i+1}")
        time.sleep(0.005)

    time.sleep(0.2)

    assert handler.Throttle_counter == 2
    assert handler.modified_call_count >= 2


# 6. Idle threshold triggers idle state transition.
def test_idle_state_trigger(watcher):
    handler, _, tmp_path = watcher

    (tmp_path / "active.py").write_text("work")
    wait_until(lambda: handler.last_created_path)

    # Add idle assertion here once implemented in watcher.py
    assert wait_until(lambda: handler.is_idle, timeout=300)


# 7. Activity resuming after an idle period produces a new "active" state transition.
def test_resuming_activity_after_idle(watcher):
    handler, _, tmp_path = watcher

    file_path = tmp_path / "resume.py"
    file_path.write_text("content")
    wait_until(lambda: handler.last_created_path)

    file_path.write_text("new activity")
    assert handler.current_state == "active"


# 8. Events inside nested subdirectories are detected (recursive watching).
def test_nested_subdirectory_event(watcher):
    handler, _, tmp_path = watcher

    sub_dir = tmp_path / "nested" / "deep"
    sub_dir.mkdir(parents=True)

    nested_file = sub_dir / "deep_file.py"
    nested_file.write_text("nested code")

    created_path = wait_until(lambda: handler.last_created_path)
    assert Path(created_path).name == "deep_file.py"


# 9. Events in directories outside configured watch roots produce nothing.
def test_events_outside_watched_root(tmp_path):
    # This test explicitly manages its own paths since it creates outside directory
    handler = EventHandlerWrapper()
    watched_dir = tmp_path / "watched"
    unwatched_dir = tmp_path / "unwatched"
    watched_dir.mkdir()
    unwatched_dir.mkdir()

    observer = Observer()
    observer.schedule(handler, str(watched_dir), recursive=False)
    observer.start()

    try:
        (unwatched_dir / "outside.py").write_text("ignored")
        triggered = wait_until_timeout(lambda: handler.last_created_path is not None, timeout=0.3)
        assert not triggered
    finally:
        observer.stop()
        observer.join()


# 10. Creating a directory itself does not produce a file-content event.
def test_create_directory_only(watcher):
    handler, _, tmp_path = watcher

    new_dir = tmp_path / "empty_folder"
    new_dir.mkdir()

    triggered = wait_until_timeout(lambda: handler.last_created_path is not None, timeout=0.3)
    assert not triggered


# 11. Multiple watched roots are monitored simultaneously and correctly attributed.
def test_multiple_watched_roots(tmp_path):
    root_a = tmp_path / "root_a"
    root_b = tmp_path / "root_b"
    root_a.mkdir()
    root_b.mkdir()

    handler = EventHandlerWrapper()
    observer = Observer()
    observer.schedule(handler, str(root_a), recursive=False)
    observer.schedule(handler, str(root_b), recursive=False)
    observer.start()

    try:
        (root_a / "file_a.py").write_text("a")
        created_path_a = wait_until(lambda: handler.last_created_path)
        assert str(root_a) in created_path_a

        handler.last_created_path = None

        (root_b / "file_b.py").write_text("b")
        created_path_b = wait_until(lambda: handler.last_created_path)
        assert str(root_b) in created_path_b
    finally:
        observer.stop()
        observer.join()


# 12. Rename of a tracked file (handled as a delete and reapear). if extensions are tracked of both
def test_rename_both_tracked_file(watcher):
    handler, _, tmp_path = watcher

    src_file = tmp_path / "old_name.py"
    dst_file = tmp_path / "new_name.py"
    src_file.write_text("content")

    src_file.rename(dst_file)
    created_path = wait_until(lambda: handler.last_created_path)
    deleted_path = wait_until(lambda: handler.last_deleted_path)

    assert Path(created_path).name == "new_name.py"
    assert Path(deleted_path).name == "old_name.py"

# 13. Rename of a tracked file (handled as a delete and reapear). if extensions of old file was tracked 
# and new file is not tracked then only delete event will be produced
def test_rename_old_tracked_file(watcher):
    handler, _, tmp_path = watcher

    src_file = tmp_path / "old_name.py"
    dst_file = tmp_path / "new_name.txt"
    src_file.write_text("content")

    wait_until(lambda: handler.last_created_path)
    handler.last_created_path = None # since we have created a file to rename it this value gets populated which we do not want 

    src_file.rename(dst_file)
    triggered_created = wait_until_timeout(lambda: handler.last_created_path is not None)
    deleted_path = wait_until(lambda: handler.last_deleted_path)

    assert not triggered_created
    assert Path(deleted_path).name == "old_name.py"

# 14. Rename of a tracked file (handled as a delete and reapear). if extensions of new file is tracked and 
# not the old file then only create event will be produced
def test_rename_new_tracked_file(watcher):
    handler, _, tmp_path = watcher

    src_file = tmp_path / "old_name.txt"
    dst_file = tmp_path / "new_name.py"
    src_file.write_text("content")

    src_file.rename(dst_file)
    created_path = wait_until(lambda: handler.last_created_path)
    triggered_deleted = wait_until_timeout(lambda: handler.last_deleted_path is not None)

    assert Path(created_path).name == "new_name.py"
    assert not triggered_deleted
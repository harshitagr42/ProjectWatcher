import time

def wait_until(condition_fn, timeout=2.0, interval=0.05):
    """Poll condition_fn() until it returns a truthy value or timeout expires."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if result := condition_fn():
            return result
        time.sleep(interval)
    raise TimeoutError(f"Condition was not met within {timeout} seconds.")

def wait_until_timeout(condition_fn, timeout=0.5, interval=0.05):
    """Wait for duration to ensure a condition remains false/None (useful for negative assertion tests)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition_fn():
            return True
        time.sleep(interval)
    return False
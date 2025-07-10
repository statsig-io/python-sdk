import statsig
import psutil
import time
import os

MAX_MEMORY_MB = 100
LOOP_COUNT = 100
SECRET_KEY = "secret-key"  # Replace or mock as needed

def get_memory_usage_mb() -> float:
    process = psutil.Process(os.getpid())
    return process.memory_info().rss / (1024 * 1024)  # in MB

def test_statsig_memory_usage():
    for i in range(LOOP_COUNT):
        statsig.initialize(SECRET_KEY, {"tier": "test", "environment": "python_test"})
        statsig.shutdown()

        mem_mb = get_memory_usage_mb()
        print(f"[{i+1}/{LOOP_COUNT}] Memory usage: {mem_mb:.2f} MB")
        assert mem_mb < MAX_MEMORY_MB, f"Memory exceeded: {mem_mb:.2f} MB"

        time.sleep(0.1)  # Prevent CPU hogging

if __name__ == "__main__":
    test_statsig_memory_usage()
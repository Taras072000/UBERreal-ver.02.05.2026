import sys
from unittest.mock import MagicMock

# Mock runpod module before importing serverless_handler
sys.modules["runpod"] = MagicMock()
sys.modules["runpod.serverless"] = MagicMock()

# Add engine directory to path
import os
sys.path.append(os.path.join(os.path.dirname(__file__), "engine"))

from serverless_handler import handler

# Test job
test_job = {
    "id": "test_job_1",
    "input": {
        "prompt": "A beautiful landscape with mountains and a lake, highly detailed, 8k",
        "negative_prompt": "blurry, low quality",
        "width": 1024,
        "height": 1024,
        "steps": 20,
        "cfg": 7.0,
        "sampler_name": "dpmpp_2m",
        "scheduler": "karras"
    }
}

print("Starting test job...")
result = handler(test_job)
print("Job finished.")
print(result)

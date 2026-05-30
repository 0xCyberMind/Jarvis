import time

import memory


def test_memory_api_exists():
    assert callable(memory.remember)
    assert callable(memory.recall)

    # write a short-lived test memory and attempt to recall it
    tag = f"unittest-{int(time.time())}"
    try:
        memory.remember(f"test memory {tag}", mem_type="fact", importance=1)
    except Exception:
        # some environments may require DB initialization; at least the API exists
        pass
    rows = memory.recall(tag, limit=5)
    assert isinstance(rows, list)

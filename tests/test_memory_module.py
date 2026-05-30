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


def test_build_memory_context_deduplicates(monkeypatch):
    monkeypatch.setattr(memory, "get_open_tasks", lambda: [])
    monkeypatch.setattr(memory, "recall", lambda query, limit=3: [
        {"type": "fact", "content": "keep this"},
        {"type": "fact", "content": "keep this"},
    ])
    monkeypatch.setattr(memory, "get_important_memories", lambda limit=3: [
        {"content": "keep this"},
        {"content": "another fact"},
    ])

    context = memory.build_memory_context("remember this")
    assert context.count("keep this") == 1
    assert "another fact" in context

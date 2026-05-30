import time
from memory import recall, remember


def bench_recall(iterations: int = 100):
    # seed a few memories
    for i in range(10):
        remember(f"bench memory {i}", mem_type="fact")

    start = time.time()
    for i in range(iterations):
        recall("bench memory", limit=5)
    duration = time.time() - start
    print(f"Ran {iterations} recalls in {duration:.3f}s — {iterations/duration:.1f} req/s")


if __name__ == '__main__':
    bench_recall(200)

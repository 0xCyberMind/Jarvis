from prometheus_client import Counter, Histogram, Gauge
from prometheus_client import CollectorRegistry, generate_latest
import time

# Registry (use default registry by importing in server for exposition)
registry = CollectorRegistry(auto_describe=True)

# Memory metrics
memory_recall_count = Counter('jarvis_memory_recall_total', 'Number of memory recall calls')
memory_recall_latency = Histogram('jarvis_memory_recall_seconds', 'Memory recall latency seconds')

# Event bus metrics
event_publish_count = Counter('jarvis_event_publish_total', 'Number of events published')
event_publish_latency = Histogram('jarvis_event_publish_seconds', 'Event publish latency seconds')
event_publish_failures = Counter('jarvis_event_publish_failures_total', 'Event publish failures')

# Agent metrics
agent_failures = Counter('jarvis_agent_failures_total', 'Agent execution failures')

# System gauges
cpu_usage = Gauge('jarvis_cpu_percent', 'CPU usage percent')
memory_rss = Gauge('jarvis_memory_rss_bytes', 'RSS memory in bytes')


def observe_memory_recall(func):
    def wrapper(*args, **kwargs):
        memory_recall_count.inc()
        start = time.time()
        try:
            return func(*args, **kwargs)
        finally:
            memory_recall_latency.observe(time.time() - start)
    return wrapper


def metrics_output():
    # Use the default registry to include registered metrics
    from prometheus_client import generate_latest, REGISTRY
    return generate_latest(REGISTRY)

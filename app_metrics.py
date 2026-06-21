from prometheus_client import Counter


EVENTS = Counter(
    'events_total',
    'Total HTTP Events received',
    namespace='app'
)
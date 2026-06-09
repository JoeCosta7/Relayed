from prometheus_client import Counter, Gauge, Histogram


EVENTS = Counter(
    'events_total',
    'Total HTTP Events received',
    namespace='app'
)

DELIVERED = Counter(
    'delivered_events_total',
    'Total HTTP Events delivered',
    namespace='app'
)

FAILED = Counter(
    'failed_events_total',
    'Total HTTP Events failed',
    namespace='app'
)

RETRYING = Gauge(
    'events_retrying',
    'Number of active events retrying',
    namespace='app'
)

DELIVERY_DURATION = Histogram(
    'delivery_duration_seconds',
    'Time in seconds for a delivery',
    namespace='app',
    buckets=[.01, .05, .1, .25, .5, 1, 2.5, 5],
)

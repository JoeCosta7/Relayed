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
    "delivery_duration_seconds",
    "Time in seconds for the delivery as a histogram",
    namespace='app'
)

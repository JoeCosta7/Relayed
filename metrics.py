from prometheus_client import Counter, Gauge, Histogram


EVENTS = Counter(
    'events_total',
    'Total HTTP Events received',
    namespace='app'
)

DELIVERED = Gauge(
    'delivered_events_total',
    'Total HTTP Events delivered',
    namespace='app'
)

FAILED = Gauge(
    'failed_events_total',
    'Total HTTP Events failed',
    namespace='app'
)

RETRYING = Gauge(
    'events_retrying',
    'Number of active events retrying',
    namespace='app'
)

LAST_DELIVERY_DURATION = Gauge(
    'last_delivery_duration_seconds',
    'Time in seconds for a delivery',
    namespace='app',
)

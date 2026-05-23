from prometheus_client import Counter, Gauge, Histogram

price_check_runs = Counter(
    "price_check_runs_total",
    "Total price check job runs",
)

price_check_last_run = Gauge(
    "price_check_last_run_timestamp",
    "Unix timestamp of last completed price check run",
)

price_check_duration = Histogram(
    "price_check_duration_seconds",
    "Price check job duration in seconds",
)

price_check_regions = Counter(
    "price_check_regions_total",
    "Price check outcomes per region",
    ["result"],  # dropped | unchanged | skipped
)

price_drops_created = Counter(
    "price_drops_created_total",
    "Price drops recorded in the database",
)

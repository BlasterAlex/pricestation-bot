from prometheus_client import Counter, Histogram

ps_api_requests = Counter(
    "ps_api_requests_total",
    "Total PS Store API requests",
    ["operation", "status"],
)
ps_api_none_results = Counter(
    "ps_api_none_results_total",
    "PS Store API calls that returned no usable result",
    ["operation"],
)
ps_api_duration = Histogram(
    "ps_api_request_duration_seconds",
    "PS Store API request duration in seconds",
    ["operation"],
)

subscriptions_created = Counter(
    "subscriptions_created_total",
    "New subscriptions successfully created",
)
subscriptions_already_exists = Counter(
    "subscriptions_already_exists_total",
    "Subscribe attempts rejected because subscription already exists",
)

bot_handler_errors = Counter(
    "bot_messages_failed_total",
    "Bot handler errors (stale state, missing entries, etc.)",
)

region_sync_not_found = Counter(
    "region_sync_games_not_found_total",
    "Games not found in PS Store during region sync fallback search",
)

import os

from celery import Celery

# Celery app instance
celery_app = Celery(
    "multiagents",
    broker=os.getenv("CELERY_BROKER_URL"),
    backend=os.getenv("CELERY_RESULT_BACKEND"),
    include=[  # list of modules to import when the Celery worker starts
        "tasks.agent_chat",
    ]
)

# Conf Celery with essential settings

celery_app.conf.update(
    task_serializer=os.getenv("CELERY_TASK_SERIALIZER", "json"),
    result_serializer=os.getenv("CELERY_TASK_SERIALIZER", "json"),
    accept_content=[
        os.getenv("CELERY_TASK_SERIALIZER", "json")
    ],
    # Task safety - late ack prevents task loss on worker crash
    task_acks_late=os.getenv("CELERY_TASK_ACKS_LATE", "true").lower() == "true",

    # Time limits - Prevent hanging tasks
    task_time_limit=int(os.getenv("CELERY_TASK_TIME_LIMIT", "3600")),

    # Result backend - store results for status tracking
    task_ignore_result=False,
    result_expires=3600,

    # worker settings
    worker_concurrency=int(os.getenv("CELERY_WORKER_CONCURRENCY", "4")),

    # Connection settings for better reliability
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,  # in case we lose the connection while working
    broker_connection_max_retries=10,
    worker_cancel_long_running_tasks_on_connection_loss=True,

    task_routes={
        "tasks.agent_chat.run_orchestrator_chat": {"queue": "orchestrator_queue"},
        "tasks.agent_chat.run_property_deals_chat": {"queue": "property_deals_queue"},
        "tasks.agent_chat.run_people_chat": {"queue": "people_queue"},
        "tasks.agent_chat.run_sales_payments_chat": {"queue": "sales_payments_queue"},
    },

    timezone="UTC",
)

celery_app.conf.task_default_queue = "default"  # name of the main queue

from dotenv import dotenv_values

config = dotenv_values(".env")

# Flower Configuration
port = 5555
max_tasks = 10000
auto_refresh = True

# Authentication
basic_auth = [f'admin:{config["CELERY_FLOWER_PASSWORD"]}']

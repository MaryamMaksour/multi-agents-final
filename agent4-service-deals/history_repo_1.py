# agent4-service-deals/history_repo_1.py
#
# Thin binding of the shared agent_common history-logging API to this
# domain's table. Kept as its own module (rather than folded into
# agent_config.py) so that tools.py's `from .history_repo_1 import
# log_sql_query` needs no changes, and so agent_config.py can import the
# same `history_repo` instance without a circular import through
# agent_tools -> tools -> history_repo_1 -> agent_config.
from agent_common.history_repo import build_history_repo

history_repo = build_history_repo(table_name="history4")
log_sql_query = history_repo.log_sql_query

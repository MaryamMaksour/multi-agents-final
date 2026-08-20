# agents-service/history_repo.py
#
# The orchestrator used to keep its own separate copy of this logic in
# main/history_repo.py - same implementation as every sub-agent's
# history_repo_1.py had, just never deduplicated because the orchestrator
# wasn't in scope of the first extraction pass. Binds the shared,
# bug-fixed controllers/history_repo.py implementation to this service's
# own table instead of maintaining a third copy.
from controllers.history_repo import build_history_repo

history_repo = build_history_repo(table_name="history_orchestrator")

new_turn_id = history_repo.new_turn_id
ensure_history_schema = history_repo.ensure_history_schema
log_user_message = history_repo.log_user_message
log_assistant_final = history_repo.log_assistant_final
log_tool_call = history_repo.log_tool_call
log_sql_query = history_repo.log_sql_query
get_session_history = history_repo.get_session_history
get_turn_history = history_repo.get_turn_history
delete_session_history = history_repo.delete_session_history
get_memory = history_repo.get_memory

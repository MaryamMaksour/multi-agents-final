"""Semantic memory: past turns retrieved as few-shot examples.

Reads the same table HistoryModel writes, and deliberately reads only
one key of it. `payload->'shape'` is the turn's reasoning - which tools
were called, in what order, with what SQL - and never the rows those
calls returned. That is what makes an example useful: the model needs to
see *how* a similar question was answered, not what the answer was.

Two lookups, run independently so a failure in one never erases the
other's results:

  good  the closest successful turns, each with its full reasoning trace
  bad   the closest failed turn, with the reason it failed, as a short
        counter-example
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from models.enums import EventType

from .BaseDataModel import BaseDataModel

logger = logging.getLogger(__name__)


class MemoryModel(BaseDataModel):

    def __init__(self, pg_client, config, table_name: str):
        super().__init__(pg_client, config)
        self.table_name = self.validate_table_name(table_name)

    @classmethod
    async def create_instance(cls, pg_client, config, table_name: str) -> "MemoryModel":
        return cls(pg_client, config, table_name)

    async def _fetch_successful(self, conn, vector: str, limit: int) -> List[Dict[str, Any]]:
        sql = f"""
        WITH matched AS (
            SELECT turn_id
              FROM {self.table_name}
             WHERE event_type = $3
               AND valid = true
               AND embed_user_query IS NOT NULL
               AND created_at >= NOW() - ($4 || ' days')::interval
             ORDER BY embed_user_query {self.config.DIST_OP} $1::vector ASC, created_at DESC
             LIMIT $2
        )
        SELECT u.payload -> 'user_query' AS question,
               f.payload -> 'shape'      AS steps
          FROM matched m
          JOIN {self.table_name} u ON u.turn_id = m.turn_id AND u.event_type = $3
          JOIN {self.table_name} f ON f.turn_id = m.turn_id AND f.event_type = $5
        """
        records = await conn.fetch(
            sql, vector, limit,
            EventType.USER.value, str(self.config.MEMORY_WINDOW_DAYS),
            EventType.ASSISTANT_FINAL.value,
        )
        return [{"question": r["question"], "steps": r["steps"]} for r in records]

    async def _fetch_failed(self, conn, vector: str, limit: int) -> List[Dict[str, Any]]:
        sql = f"""
        SELECT payload -> 'user_query' AS question, reason
          FROM {self.table_name}
         WHERE event_type = $3
           AND valid = false
           AND embed_user_query IS NOT NULL
           AND created_at >= NOW() - ($4 || ' days')::interval
         ORDER BY embed_user_query {self.config.DIST_OP} $1::vector ASC, created_at DESC
         LIMIT $2
        """
        records = await conn.fetch(
            sql, vector, limit,
            EventType.USER.value, str(self.config.MEMORY_WINDOW_DAYS),
        )
        return [{"question": r["question"], "why_it_failed": r["reason"]} for r in records]

    async def get_examples(self, query_vector: Optional[str]) -> Dict[str, Any]:
        """Worked examples for a question, as {successful: [...], failed: [...]}."""
        if not self.config.MEMORY_ENABLED or not query_vector:
            return {}

        examples: Dict[str, Any] = {}

        try:
            async with self.pg_client.acquire() as conn:
                try:
                    successful = await self._fetch_successful(
                        conn, query_vector, self.config.MEMORY_GOOD_EXAMPLES
                    )
                    if successful:
                        examples["successful"] = successful
                except Exception:
                    logger.exception("Memory lookup for successful examples failed")

                try:
                    failed = await self._fetch_failed(
                        conn, query_vector, self.config.MEMORY_BAD_EXAMPLES
                    )
                    if failed:
                        examples["failed"] = failed
                except Exception:
                    logger.exception("Memory lookup for failed examples failed")

        except Exception:
            logger.exception("Memory lookup failed")

        return examples

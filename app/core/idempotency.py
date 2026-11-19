"""Idempotency management and request deduplication store."""
import hashlib
import json
from typing import Optional, Dict, Any, Tuple
from app.core.database import get_db_connection

def hash_payload(data: Any) -> str:
    serialized = json.dumps(data, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

class IdempotencyManager:
    def get_existing_record(self, idempotency_key: str, tenant_id: str) -> Optional[Dict[str, Any]]:
        with get_db_connection() as conn:
            row = conn.execute(
                """
                SELECT idempotency_key, tenant_id, request_hash, response_status, response_body, created_at
                FROM idempotency_records
                WHERE idempotency_key = ? AND tenant_id = ?
                """,
                (idempotency_key, tenant_id)
            ).fetchone()
            if row:
                return {
                    "idempotency_key": row["idempotency_key"],
                    "tenant_id": row["tenant_id"],
                    "request_hash": row["request_hash"],
                    "status_code": row["response_status"],
                    "response_body": json.loads(row["response_body"]),
                    "created_at": row["created_at"]
                }
            return None

    def store_record(
        self,
        idempotency_key: str,
        tenant_id: str,
        request_hash: str,
        status_code: int,
        response_body: Dict[str, Any]
    ):
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO idempotency_records (idempotency_key, tenant_id, request_hash, response_status, response_body)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(idempotency_key) DO UPDATE SET
                    response_status = excluded.response_status,
                    response_body = excluded.response_body
                """,
                (idempotency_key, tenant_id, request_hash, status_code, json.dumps(response_body))
            )
            conn.commit()

idempotency_manager = IdempotencyManager()

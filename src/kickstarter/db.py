import psycopg
from psycopg.types.json import Json
import json

from kickstarter.config import settings

DDL = """
CREATE TABLE IF NOT EXISTS predictions (

    request_id      uuid PRIMARY KEY,
    ts      timestamptz NOT NULL DEFAULT now(),
    model_version       text NOT NULL,
    features        jsonb NOT NULL,
    score       double precision NOT NULL,
    latency_ms real,
    http_status SMALLINT NOT NULL CHECK (http_status BETWEEN 100 AND 599)
)
"""

def init() -> None:
    if not settings.database_url:
        return
    with psycopg.connect(settings.database_url) as conn:
        conn.execute(DDL)


def save_prediction(request_id: str, features: dict, score: float, model_version: str, latency_ms: float, http_status: int) -> None:
    if not settings.database_url:
        return
    with psycopg.connect(settings.database_url) as conn:
        payload_json = json.dumps(features, default=str)
        conn.execute(
            "INSERT INTO predictions (request_id, model_version, features, score, latency_ms, http_status) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (request_id, model_version, Json(payload_json), score, latency_ms, http_status),
        )

    
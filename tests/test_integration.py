import os
import time

import psycopg
import pytest

DATABASE_URL = os.getenv("DATABASE_URL")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not DATABASE_URL, reason="Postgres: DATABASE_URL not set"),
]


def test_good_row(client, good_row):
    body = client.post("/v1/predict", json=good_row).json()
    time.sleep(0.1)
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT model_version, score, (features->>'goal')::float, http_status "
            "FROM predictions WHERE request_id = %s",
            (body["request_id"],),
        ).fetchone()

    assert row is not None
    assert row[0] == body["model_version"]
    assert row[1] == pytest.approx(body["score"])
    assert row[2] == good_row["goal"]
    assert row[3] == 200
    
    
def test_bad_row(client, good_row):
    body = client.post("/v1/predict", json={**good_row, "category": 1}).json()
    time.sleep(0.1)
    with psycopg.connect(DATABASE_URL) as conn:
        row = conn.execute(
            "SELECT model_version, http_status "
            "FROM predictions WHERE request_id = %s",
            (body["request_id"],),
        ).fetchone()

    assert row is not None
    assert row[1] == 422
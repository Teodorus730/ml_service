import pytest
from fastapi.testclient import TestClient

from kickstarter.service.app import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def good_row():
    return {
        "name": "Greeting From Earth: ZGAC Arts Capsule For ET",
        "category": "Narrative Film",
        "main_category": "Film & Video",
        "currency": "USD",
        "deadline": "2017-11-01",
        "goal": 30000.0,
        "launched": "2017-09-02",
        "country": "US",
        "usd_goal_real": 30000.00
    }
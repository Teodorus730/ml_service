import pandas as pd
import pandera.pandas as pa
import pytest

from kickstarter.data import ROWS, clean


@pytest.fixture()
def raw():
    return pd.DataFrame({
    "name": ["Solar-Powered Smart Backpack", "Retro Pixel Art Bluetooth Speaker", None, "Leather Wallet with RFID", "Indie Cyberpunk Board Game"],
    "category": ["Product Design", "Gadgets", "Hardware", "Accessories", "Tabletop Games"],
    "main_category": ["Design", "Technology", "Technology", "Design", "Games"],
    "currency": ["USD", "EUR", "GBP", "USD", "CAD"],
    "country": ["US", "DE", "GB", "US", "CA"],
    "goal": [10000.0, 25000.0, 5000.0, 1500.0, 50000.0],
    "state": ["successful", "failed", "live", "successful", "canceled"],
    "launched": ["2017-01-05 13:00:00", "2018-05-12 10:30:00", "2019-03-01 00:00:00", "2020-07-15 08:00:00", "2021-10-10 15:45:00"],
    "deadline": ["2017-02-04 13:00:00", "2018-06-11 10:30:00", "2019-04-01 00:00:00", "2020-08-14 08:00:00", "2021-11-09 15:45:00"],
    "usd_goal_real": [10000.0, 29450.2, 6500.0, 1500.0, 39200.0]
})
    

def test_clean_keeps_valid_kickstarter_data(raw):
    df = clean(raw)
    assert df["state"].tolist()[:2] == ["successful", "failed"]
    assert pd.api.types.is_datetime64_any_dtype(df["launched"])
    assert pd.api.types.is_datetime64_any_dtype(df["deadline"])
    ROWS.validate(df)


def test_negative_goal_is_caught(raw):
    bad = clean(raw).assign(goal=lambda d: d["goal"] * -1 - 100)
    
    with pytest.raises(pa.errors.SchemaErrors) as e:
        ROWS.validate(bad, lazy=True)
        
    assert set(e.value.failure_cases["column"]) == {"goal"}


def test_invalid_launched_deadline_order(raw):
    bad = clean(raw).copy()
    bad["launched"] = pd.to_datetime("2025-01-01")
    bad["deadline"] = pd.to_datetime("2024-01-01")
    
    with pytest.raises(pa.errors.SchemaErrors) as e:
        ROWS.validate(bad, lazy=True)
        
    assert "Дата запуска (launched) должна быть раньше дедлайна (deadline)" in set(e.value.failure_cases["check"])


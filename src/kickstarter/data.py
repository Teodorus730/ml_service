import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd
import pandera.pandas as pa

RAW_PATH = Path(os.getenv("DATA_PATH", "data/ks-projects-201801.csv"))
EXPERIMENT = os.getenv("EXPERIMENT", "kickstarter")

ROWS = pa.DataFrameSchema(
    {
        "name": pa.Column(str, nullable=True, coerce=True),
        "category": pa.Column(str, checks=pa.Check.str_length(min_value=3), coerce=True),
        "main_category": pa.Column(str, checks=pa.Check.str_length(min_value=3), coerce=True),
        "currency": pa.Column(
            str, 
            checks=[
                pa.Check.str_length(min_value=1), 
                pa.Check.isin(['USD','GBP','CAD','EUR','AUD','SEK','NZD','DKK','MXN','CHF','NOK','HKD','SGD','JPY'])
            ],
            coerce=True),
        "country": pa.Column(str, checks=pa.Check.str_length(min_value=1), coerce=True),
        "goal": pa.Column(float, checks=pa.Check.ge(0), coerce=True),
        "state": pa.Column(
            str, 
            checks=pa.Check.isin(["successful", "failed", "canceled", "suspended", "live", "undefined"]), 
            coerce=True
        ),
        "launched": pa.Column("datetime64[ns]", coerce=True),
        "deadline": pa.Column("datetime64[ns]", coerce=True),
        "usd_goal_real": pa.Column(float, checks=pa.Check.ge(0), coerce=True),
    },
    strict=True,
    coerce=True,
    checks=[
        pa.Check(lambda df: df["launched"] < df["deadline"], error="Дата запуска (launched) должна быть раньше дедлайна (deadline)")
    ]
)

# (реальная медиана по usd_goal_real 5500)
EXPORT = pa.DataFrameSchema(
    ROWS.columns,
    checks=[
        pa.Check(lambda df: len(df) >= 10000, error="меньше 10 тысяч строк: выгрузка неполная"),
        pa.Check(lambda df: len(df[df['state'].isin(['successful', 'failed'])]) >= 1000, 
                 error="меньше 1к строк пойдет на обучение, нужно больше данных"),
        pa.Check(lambda df: df["name"].nunique() >= 1_000, error="меньше 1000 проектов"),
        pa.Check(lambda df: 0.5 <= df["usd_goal_real"].median() <= 6000.0, error="медиана выше 6к, мб косяки с конвертацией валюты"),
    ],
    strict=True,
)


def file_md5(path: Path) -> str:
    """Тот же md5, что DVC пишет в .dvc-файл: по нему видно, на какой версии данных обучена модель."""
    return hashlib.md5(path.read_bytes()).hexdigest()


def load_raw(path: Path = RAW_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw[list(ROWS.columns)].drop_duplicates().copy()
    
    df["launched"] = pd.to_datetime(df["launched"], errors="coerce")
    df["deadline"] = pd.to_datetime(df["deadline"], errors="coerce")
    
    # Приведение строк к норм формату
    for col in ["name", "category", "main_category", "currency", "country", "state"]:
        df[col] = df[col].str.strip().str.upper() if col in ["currency", "country"] else df[col].str.strip()
        
    # На всякий, больше 1кк - выброс, может поломать модель
    df = df[(df["goal"] > 0)]
    df = df[(df["usd_goal_real"] > 0) & (df["usd_goal_real"] <= 1_000_000)]
    
    # Вообще срок 30 дней, но мб и больше
    df["duration"] = (df["deadline"] - df["launched"]).dt.days
    df = df[(df["duration"] >= 1) & (df["duration"] <= 90)]
    return df.drop(columns=["duration"]).reset_index(drop=True)

def load_clean(path: Path = RAW_PATH) -> pd.DataFrame:
    return EXPORT.validate(clean(load_raw(path)), lazy=True)


def main() -> int:
    import mlflow

    raw = load_raw()
    df = clean(raw)
    md5 = file_md5(RAW_PATH)
    mlflow.set_experiment(EXPERIMENT)
    
    with mlflow.start_run(run_name="validate"):
        mlflow.log_params({"step": "validate", "data": str(RAW_PATH), "data_md5": md5})
        mlflow.log_metrics({"raw_rows": len(raw), "clean_rows": len(df)})
        
        try:
            EXPORT.validate(df, lazy=True)
        except pa.errors.SchemaErrors as e:
            fc = e.failure_cases
            summary = fc.groupby(["column", "check"], dropna=False).size().rename("cases").reset_index()
            
            with tempfile.TemporaryDirectory() as tmp:
                fc.head(1000).to_csv(Path(tmp) / "failure_cases.csv", index=False)
                mlflow.log_artifact(str(Path(tmp) / "failure_cases.csv"))
                
            mlflow.log_metric("failed_checks", len(summary))
            mlflow.set_tag("valid", "false")
            
            print("Данные не прошли проверку, отчёт failure_cases.csv в MLflow:")
            print(summary.to_string(index=False))
            return 1
        
        mlflow.set_tag("valid", "true")
        
        state_counts = df["state"].value_counts(normalize=True)
        successful_pct = float(state_counts.get("successful", 0) * 100)
        failed_pct = float(state_counts.get("failed", 0) * 100)

        goal_median = float(df["goal"].median())
        usd_goal_median = float(df["usd_goal_real"].median())

        drop_rate = float((len(raw) - len(df)) / len(raw) * 100)

        unique_categories = int(df["main_category"].nunique())
        unique_countries = int(df["country"].nunique())

        mlflow.log_metrics({
            "successful_pct": successful_pct,
            "failed_pct": failed_pct,
            "goal_median": goal_median,
            "usd_goal_median": usd_goal_median,
            "drop_rate": drop_rate,
            "unique_categories": unique_categories,
            "unique_countries": unique_countries,
        })
        
    result = {
        "valid": True,
        "data_md5": md5, 
        "clean_rows": len(df),
        "successful_pct": successful_pct,
        "failed_pct": failed_pct,
        "goal_median": goal_median,
        "usd_goal_median": usd_goal_median,
        "drop_rate": drop_rate,
        "unique_categories": unique_categories,
        "unique_countries": unique_countries,
    }
    
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
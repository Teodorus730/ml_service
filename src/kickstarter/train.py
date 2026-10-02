import json
import os
from pathlib import Path

import matplotlib.pyplot as plt
import mlflow
import numpy as np
import pandas as pd
import sklearn
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, precision_recall_curve, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from kickstarter.service.transformers import (
    DateFeatureExtractor,
    SqueezedTfidfVectorizer,
)

# Мок того как бы работал дсер
DATA_PATH = Path(os.getenv("DATA_PATH", "data/ks-projects-201801.csv"))
MODEL_NAME = os.getenv("MODEL_NAME", "kickstarter")
EXPERIMENT = os.getenv("MLFLOW_EXPERIMENT", "kickstarter")
C = float(os.getenv("C", "1.0"))
MIN_GAIN = float(os.getenv("GATE_MIN_GAIN", "0.0"))
SEED = 42
SKOPS_TRUSTED = [
    "numpy.dtype", 
    "sklearn.compose._column_transformer._RemainderColsList",
    'kickstarter.service.transformers.DateFeatureExtractor', 
    'kickstarter.service.transformers.SqueezedTfidfVectorizer'
]

validate_cols = [
    'ID',
    'goal',
    'pledged',
    'backers',
    'usd pledged',
    'usd_pledged_real',
    'usd_goal_real',
    'name',
    'category',
    'main_category',
    'currency',
    'deadline',
    'launched',
    'state',
    'country'
]

TEST_SIZE = 0.2

MIN_TARGET_PRECICION = 0.7

date_columns = ["deadline", "launched"]
text_columns = ["name"]
num_columns = ["goal", "usd_goal_real"]
obj_columns = ["category", "main_category", "currency", "country"]

def load_and_prepare(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    missing = set(validate_cols) - set(df.columns)
    if missing:
        raise ValueError(f"в данных нет колонок: {sorted(missing)}")
    
    df = df[df['state'].isin(['successful', 'failed'])]
    
    if len(df) < 1000:
        raise ValueError(f"слишком мало строк: {len(df)}")
    
    df['target'] = (df['state'] == 'successful').astype(int)
    df = df.drop(columns=['ID', 'pledged', 'backers', 'state', 'usd pledged', 'usd_pledged_real'])

    return df


def build_pipeline(c: float) -> Pipeline:
    preprocess = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline([("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler())]), 
                num_columns,
            ),
            (
                "cat",
                Pipeline([("impute", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore"))]),
                obj_columns,
            ),
            (
                "text",
                Pipeline([("impute",
                            SimpleImputer(strategy="constant", fill_value="")),
                        ("tfidf", SqueezedTfidfVectorizer(max_features=1000))]),
                text_columns,
            ),
            (
                "date",
                Pipeline([("extract_dates",
                            DateFeatureExtractor(date_cols=date_columns)),
                        ("impute", SimpleImputer(strategy="median")),
                        ("scale", StandardScaler())]),
                date_columns,
            ),
        ],
        remainder="drop",
    )
    return Pipeline([("preprocess", preprocess), ("model", LogisticRegression(max_iter=1000, C=C, random_state=SEED))])


def champion_auc(client: MlflowClient) -> tuple[str | None, float | None]:
    try:
        mv = client.get_model_version_by_alias(MODEL_NAME, "champion")
    except MlflowException:
        return None, None
    return mv.version, client.get_run(mv.run_id).data.metrics.get("roc_auc")


def main() -> dict:
    df = load_and_prepare(DATA_PATH)
    features = date_columns + text_columns + num_columns + obj_columns
    
    # Train test отсортируем руками и отключим рандом, тк задача зависит от времени
    df["sort"] = pd.to_datetime(df["launched"])
    df = df.sort_values(by="sort", ascending=True)
    df = df.reset_index(drop=True)
    df.drop(columns=["sort"], inplace=True)

    X = df[features]
    y = df['target']

    x_train, x_test, y_train, y_test = train_test_split(
        X, y, test_size=TEST_SIZE, shuffle=False
    )

    pipeline = build_pipeline(C).fit(x_train, y_train)
    proba = pipeline.predict_proba(x_test)[:, 1]
    auc = float(roc_auc_score(y_test, proba))
    precision, recall, thresholds = precision_recall_curve(y_test, proba)
        
    mask = precision >= MIN_TARGET_PRECICION
    target_precision, target_recall, target_threshold = None, None, None

    if np.any(mask):
        idx = np.where(mask)[0][0]
        target_precision = precision[idx]
        target_recall = recall[idx]
        target_threshold = thresholds[idx - 1] if idx > 0 else thresholds[0]
    
    best_threshold = float(target_threshold) if target_threshold is not None else 0.5

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(recall, precision, marker='.', label='PR Curve', color='blue')

    if target_precision is not None:
        ax.scatter([target_recall], [target_precision], color='red', zorder=5, s=100,
                    label=f'Цель: Precision = {target_precision:.2f}\nRecall = {target_recall:.2f}\nThreshold = {target_threshold:.4f}')
        ax.axhline(0.7, color='green', linestyle='--', alpha=0.7, label=f'Target Precision = {MIN_TARGET_PRECICION}')

    ax.set_xlabel('Recall')
    ax.set_ylabel('Precision')
    ax.set_title('Precision-Recall Curve (Investor Focus: Minimize False Positives)')
    ax.legend(loc='lower left')
    ax.grid(True, alpha=0.3)
    plt.tight_layout()

    mlflow.set_experiment(EXPERIMENT)
    client = MlflowClient()
    with mlflow.start_run() as run:
        mlflow.log_figure(fig, "pr_curve.png")
        plt.close(fig)
        
        metadata = {
            "model_name": "kickstarter-logreg",
            "model_version": "0.1.0",
            "trained_at": pd.Timestamp.utcnow().isoformat(timespec="seconds"),
            "n_train": int(len(X)),
            "features": list(X.columns),
            "numeric_cols": num_columns,
            "categorical_cols": obj_columns,
            "text_cols": text_columns,
            "date_cols": date_columns,
            "threshold": float(round(best_threshold, 4)),
            "libs": {
                "pandas": pd.__version__, 
                "scikit-learn": sklearn.__version__
            },
        }
        mlflow.log_params({"C": C, "model": "LogisticRegression", "seed": SEED, "data": str(DATA_PATH)})
        mlflow.log_metrics({"roc_auc": auc, "pr_auc": float(average_precision_score(y_test, proba)), "threshold": best_threshold})
        mlflow.log_dict(metadata, "metadata.json")
        
        info = mlflow.sklearn.log_model(pipeline, name="model", registered_model_name=MODEL_NAME,
                                        skops_trusted_types=SKOPS_TRUSTED)
        version = info.registered_model_version

    old_version, old_auc = champion_auc(client)
    promoted = old_auc is None or auc > old_auc + MIN_GAIN
    client.set_registered_model_alias(MODEL_NAME, "challenger", version)
    if promoted:
        client.set_registered_model_alias(MODEL_NAME, "champion", version)

    result = {"run_id": run.info.run_id, "version": version, "roc_auc": round(auc, 4),
              "champion_before": old_version, "champion_auc_before": old_auc, "promoted": promoted}
    print(json.dumps(result, ensure_ascii=False))
    xcom = Path("/airflow/xcom")
    if xcom.is_dir():
        (xcom / "return.json").write_text(json.dumps(result))
    return result


if __name__ == "__main__":
    main()
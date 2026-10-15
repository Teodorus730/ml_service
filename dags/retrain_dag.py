"""Переобучение модели оттока.

train     под с образом сервиса (тот же код, что в проде): dvc pull датасета из S3, kickstarter.train, всё в MLflow
promoted  дальше идём, только если гейт в train.py отдал новой версии алиас champion (вообще странно, в чем тогда смысл переобучения)
rollout   перезапуск kickstarter-service: новые поды загрузят нового champion из реестра

Образ для обучения берётся из переменной kickstarter_image, её выставляет CI при каждом деплое.
"""
from datetime import UTC, datetime

from airflow.providers.cncf.kubernetes.operators.pod import KubernetesPodOperator
from airflow.sdk import CronTriggerTimetable, Param, dag, task
from kubernetes.client import models as k8s

PULL = "uv run --no-sync dvc pull -r cluster data/ks-projects-201801.csv && "

COMMON = dict(
    namespace="mlops",
    in_cluster=True,
    image="{{ var.value.kickstarter_image }}",
    image_pull_policy="IfNotPresent",
    get_logs=True, 
    on_finish_action="delete_pod"
)

MLFLOW = {"MLFLOW_TRACKING_URI": "http://mlflow.mlops:5000"}


@dag(
    # 2 раза в месяц в 03:00 по Москве; пропущенные запуски не догоняем, в том числе при снятии с паузы
    schedule=CronTriggerTimetable("0 3 1,15 * *", timezone="Europe/Moscow"),
    catchup=False,
    params={"C": Param(1.0, type="number", exclusiveMinimum=0, description="регуляризация LogisticRegression")},
    tags=["kickstarter"],
)
def kickstarter_retrain():
    validate = KubernetesPodOperator(
        task_id="validate",
        name="recs-validate",
        env_vars=MLFLOW,
        env_from=[k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="s3-credentials"))],
        cmds=["sh", "-c", PULL + "uv run --no-sync python -m kickstarter.data"], 
        **COMMON,
    )
    train = KubernetesPodOperator(
        task_id="train",
        name="kickstarter-train",        
        env_vars={**MLFLOW, "C": "{{ params.C }}"},
        env_from=[k8s.V1EnvFromSource(secret_ref=k8s.V1SecretEnvSource(name="s3-credentials"))],
        cmds=["sh", "-c", PULL + "uv run --no-sync python -m kickstarter.train"],
        do_xcom_push=True,
    )
    
    @task.short_circuit
    def promoted(result: dict) -> bool:
        print(f"версия {result['version']}, roc_auc {result['roc_auc']}, champion до этого {result['champion_before']}")
        return result["promoted"]

    @task
    def rollout():
        from kubernetes import client, config

        config.load_incluster_config()
        now = datetime.now(UTC).isoformat()
        client.AppsV1Api().patch_namespaced_deployment(
            "kickstarter-service", "default",
            {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": now}}}}},
        )
        print("kickstarter-service перезапущен", now)

    validate >> train
    promoted(train.output) >> rollout()

kickstarter_retrain()
import pandas as pd
import requests


# Хотел сделать отдельной табличкой в DVC и обновлением в DAG но слишком запарно
def fetch_and_save_rates():
    url = 'https://open.er-api.com/v6/latest/USD'
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        return data.get('rates', {})
    return {}


rates_dict = fetch_and_save_rates()

df_2016 = pd.read_csv("data/ks-projects-201612.csv", encoding='latin1').iloc[:10000].dropna()
df_2018 = pd.read_csv("data/ks-projects-201801.csv")

df_2016.columns = df_2016.columns.str.strip()
df_2018.columns = df_2018.columns.str.strip()

df_2016 = df_2016.rename(columns={'usd pledged': 'usd_pledged'})

all_columns = df_2018.columns
df_2016 = df_2016.reindex(columns=all_columns)

df_2016['pledged'] = pd.to_numeric(df_2016['pledged'].astype(str).str.replace(',', ''), errors='coerce')
df_2016['goal'] = pd.to_numeric(df_2016['goal'].astype(str).str.replace(',', ''), errors='coerce')

df_2016['exchange_rate'] = df_2016['currency'].map(rates_dict).fillna(1.0)

df_2016["usd_pledged_real"] = df_2016["pledged"] / df_2016["exchange_rate"]
df_2016["usd_goal_real"] = df_2016["goal"] / df_2016["exchange_rate"]

df_2016 = df_2016.drop(columns=['exchange_rate'])

new_df = pd.concat([df_2018, df_2016], ignore_index=True)
new_df.to_csv("data/ks-projects-201801.csv", index=False)

print("Объединение завершено. Размер нового датасета:", new_df.shape)

print(new_df.isna().sum())

"""Этот файл - по сути мок обновления данных, которые пришли с апи. 

Запуск (при условии что в папке data лежат оба датасета с кагла https://www.kaggle.com/datasets/kemical/kickstarter-projects)

uv run python data/make_split.py

Проверка

MLFLOW_TRACKING_URI=http://mlflow.localhost uv run python -m kickstarter.data

Пуш в dvc

uv run dvc add data/ks-projects-201801.csv
git add data/ks-projects-201801.csv.dvc
git commit -m "update dataset: added mock updates"
uv run dvc push

"""
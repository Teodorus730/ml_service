# Что делал

Переписал мидлварю (не уверерен что норм получилось) и поправил баги из ревью

# Ссылки на pr/коммиты

1. [рабочий pr](https://github.com/Teodorus730/ml_service/pull/6)

2. [красно-зеленый pr](https://github.com/Teodorus730/ml_service/pull/2)

3. Сломать/починить

- Поставил [неверное название модели](https://github.com/Teodorus730/ml_service/actions/runs/36251317991/job/108429909313) в configmap - упал пункт service. В логах (диагностика): 

```FileNotFoundError: [Errno 2] No such file or directory: 'artifact/test_cicd.joblib'```

- Поставил [неверный secretRef](https://github.com/Teodorus730/ml_service/actions/runs/36253003424), упал пункт service. В диагностике ничего полезного, но в самих логах service

```spec.template.spec.containers[0].envFrom[1].secretRef.name: Invalid value: "kickstarter-test_secrets"```

- Поставил в [requests](https://github.com/Teodorus730/ml_service/actions/runs/36257162966) 1000000000Mi, упал пункт service, сразу в логах превышение лимитов

```The Deployment "kickstarter-service" is invalid: spec.template.spec.containers[0].resources.requests: Invalid value: "1000000000Mi": must be less than or equal to memory limit of 256Mi```


# Вопросы

1. На [этом](https://github.com/Teodorus730/ml_service/actions/runs/36250790195) прогоне изменялся докерфайл, джоба работала 47 секунд. На буквально следующем [коммите](https://github.com/Teodorus730/ml_service/actions/runs/36251317991) джоба build уже 20 секунд. По сути весь образ (все слои) подтянулись их кэша, в логах это видно (пункт run build-push-action). 

2. Поды со статусом ImagePullBackOff означают проблемы с подтягиванием образа. Я не поймал такого на зеленых (мб и поймал, но не смотрел diagnostics, там условие менять надо). Мб образ просто не успел подтянуться когда джоба уже пошла к следующей команде

3. Нельзя в configmap потому что он хранится в открытом виде. Путь: github secrets -> env workflow (${{ secrets.DB_PASSWORD }}) -> кубер секрет (точнее не скажу) -> подтягивается в контейнер пода через deployment.yaml 

4. Допустим оставили деплой после сборки. тогда тесты в лучшем случае выполняются параллельно со сборкой и выкатом в прод. Если тесты на самом деле падают - говнокод уже в проде

5. За это отвечают строки

```
tests:
  on:
    push: {branches: [main]}
    pull_request:

  ...

  build:
    if: github.ref == 'refs/heads/main'
```

Все джобы запускаются минимум из pr в main, build (и следовательно deploy) требуют именно коммит в main

6. Если бд пустая, обе реплики (контейнеры api) попытаются создать таблицу (тк сам функционал создания таблицы находится в контейнере api а их 2) и одна из них упадет. Не критично, когда она перезапустится база уже будет существавать, но нехорошо. Сама строчка с pg_advisory_xact_lock гарантирует что базу попытается создать только 1 под.

7. Статусы подов

- [Pending](https://github.com/Teodorus730/ml_service/actions/runs/36260947942/job/108456668828) (для этого провел еще один тест, поднял лимиты вместе с требованиями). Статус: под принят планировщиком, контейнеры еще не созданы.

- [ImagePullBackOff](https://github.com/Teodorus730/ml_service/actions/runs/36251317991/job/108429909313). Статус: образ не найден

- [CrashLoopBackOff](https://github.com/Teodorus730/ml_service/actions/runs/36251317991/job/108429909313). Статус: образ скачан, контейнер запущен, но сразу падает



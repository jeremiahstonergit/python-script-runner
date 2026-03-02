# Python Script Runner (FastAPI) for Knative Serving

Это минимальный сервис под Knative Serving: веб-форма на `/` → загрузка файла → выбор обработчика → скачивание результата.

## Как работает

- `GET /` — форма: upload + выбор скрипта (из папки `scripts/`) + submit
- `POST /run` — сохраняет upload во временный файл, запускает выбранный скрипт как subprocess:
  ```bash
  python scripts/<script>.py --input <tmp_in> --output <tmp_out>
  ```
  после завершения отдаёт `<tmp_out>` как скачивание.

## Basic Auth (опционально)

Если задать ENV:
- `USER`
- `PASSWORD`

то будет включён HTTP Basic Auth для `/` и `/run`.  
Если переменные не заданы — доступ открыт.

## Метаданные скриптов

Чтобы UI показывал подсказку и корректное расширение результата, каждый скрипт в `scripts/` содержит в начале:

- `#TITLE: ...` — человекочитаемое имя
- `#INPUT_HINT: ...` — подсказка по входному файлу
- `#OUTPUT_EXT: .xlsx|.csv|.zip|...` — расширение результирующего файла

## Локальный запуск (Docker)

Сборка:
```bash
docker build -t python-script-runner:local .
```

Запуск без auth:
```bash
docker run --rm -p 8080:8080 python-script-runner:local
```

Запуск с auth:
```bash
docker run --rm -p 8080:8080 -e USER=admin -e PASSWORD=change_me python-script-runner:local
```

Открыть:
- http://localhost:8080/

## Деплой в Knative

1) Собери и запушь образ:
```bash
docker build -t YOUR_REGISTRY/python-script-runner:latest .
docker push YOUR_REGISTRY/python-script-runner:latest
```

2) В `knative-service.yaml` замени `YOUR_REGISTRY/...` на свой образ.

3) Применяй:
```bash
kubectl apply -f knative-service.yaml
```

## Что внутри scripts/

Скрипты были адаптированы под единый контракт `--input/--output` и под отдачу одного файла (для нескольких CSV используется ZIP).
Смотри подсказку в форме — там указано, что именно загрузить и что получится на выходе.

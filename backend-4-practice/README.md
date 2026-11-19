# Backend. Задание 4

Добавлена модель `ServiceCreate` и `POST /services`. Название и описание — от 1 до 100 символов, длительность — 30–180 минут, цена — больше нуля. Пустые строки и строки из пробелов не принимаются.

Запуск (Python 3.10+):

```sh
cd backend-4-practice
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe main.py
```

Проверка: [Swagger](http://127.0.0.1:8002/docs) → `POST /services` → `Try it out`.

```json
{
  "categoryId": 3,
  "title": "Наращивание ресниц",
  "desc": "Огромные ресницы уже через 30 минут",
  "duration": 30,
  "price": 1500.00
}
```

Корректная услуга сохраняется в `salon.db`, ответ — 201. Неверные данные дают 422, несуществующая категория — 404. База и четыре категории создаются при запуске. API мастеров и категорий сохранены; `servicesCount` теперь считается по БД.

Тесты:

```sh
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

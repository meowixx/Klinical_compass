# Клинический компас — frontend

Frontend-приложение в папке `clinical-compass/` основной ветки `main`. Оно работает с локальными стартовыми данными или с FastAPI из корня репозитория через единый `ClinicalRepository`.

Next.js, React и TypeScript. В статической сборке локальные данные сохраняются в браузере через mock-репозиторий. При `NEXT_PUBLIC_DATA_SOURCE=api` вход и данные обслуживает FastAPI с HttpOnly cookie-сессией и SQLAlchemy. Реализованы отдельные кабинеты администратора, врача и пациента.

## Роли

- `Admin` — мониторинг показателей, проверка функций, состояние будущего backend и аудит.
- `Persent` — рабочий кабинет врача с пациентами, алертами, задачами и ИИ-черновиками.
- `Doctor` — кабинет пациента с дневником, опросниками, отметками терапии и заданиями.

Для входа используйте пароли, переданные владельцем проекта отдельно.

## Запуск

```sh
cd clinical-compass
npm ci
npm run dev
```

## Структура

```text
clinical-compass/
  src/app/             страницы и стили
  src/components/      интерфейс
  src/types/           модели данных
  src/repositories/    контракты доступа к данным
  src/mock/            стартовые данные и локальное хранение
  src/services/        бизнес-правила и валидация
  src/api/             адаптер FastAPI
  tests/               проверки репозитория и критических сценариев
```

## Правовые реквизиты

Перед публикацией заполните в `.env.local` значения `NEXT_PUBLIC_OPERATOR_NAME`, `NEXT_PUBLIC_OPERATOR_ADDRESS`, `NEXT_PUBLIC_PRIVACY_EMAIL` и при необходимости `NEXT_PUBLIC_OPERATOR_REGISTRY`. Они выводятся на страницах правил использования, политики обработки персональных данных, согласия и cookie. Без наименования, адреса и контакта оператора юридические страницы показывают предупреждение о незаполненных реквизитах.

## Проверки и сборка

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

Production-сборка экспортируется в `out/` и может обслуживаться статическим хостингом.

## Подключение API

Скопируйте `.env.example` в `.env.local`. По умолчанию `NEXT_PUBLIC_DATA_SOURCE=mock`. Для локального FastAPI задайте `NEXT_PUBLIC_DATA_SOURCE=api` и `NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1`, затем пересоберите frontend. Сервер использует SQLite. Для отдельного публичного домена API задайте HTTPS-адрес, разрешите домен frontend в `FRONTEND_ORIGINS`, а cookie настройте через `COOKIE_SECURE=1` и `COOKIE_SAMESITE=none`.

Система не устанавливает диагноз и не назначает лечение самостоятельно. Окончательное решение принимает врач.

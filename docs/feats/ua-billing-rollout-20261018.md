# Оновлення робочої CRM: українські документи — 18.10.2026

Запит користувача: «обнови», після готового й перевіреного модуля.
Змінюється лише застосунок CRM та встановлюється `recuite_billing` у
`crm.recuite.com`. Жодного імпорту SuiteCRM, робочих тестових рахунків, нових
облікових записів, зміни пароля Administrator або автоматичної видачі ролей.
Administrator має штатний доступ; іншим користувачам ролі призначаються окремо.

## Кандидат і база

- Джерело: `alexkash/frappe-ua-billing`, `ef08effe85ef9d2b8f2869cc8db64d579cd96f4c`.
- Framework 15.123.1 / CRM 1.88.0 / billing 0.1.0.
- Поточний робочий образ: `sha256:9874d97aff504aebc1a2bd4fede3c4d42d8f75af78b3d0d06a3e51631cd5db06`.
- Робочий Compose: `/opt/frappe-crm/compose.yaml`, SHA-256
  `f453a7bd4d21abb39c49b1e6df418ea5f5dbbb8b288d1072251dd9a78dee7e29`.
- Новий образ збирається з перевіреного локального source manifest і готових
  frontend assets через `ops/recuite/Dockerfile.local`; test Nginx/паролі/дані
  не переносяться. Фінальний образ: `recuite/crm:billing-20261018-ef08effe`,
  `sha256:cb1db0ce22d68cce0d205b3d86364f759c28bbde546ebf20e8dc443818977e9d`.
  Source/base integrity, versions/assets/no-test-config smoke та 83 billing tests
  на ізольованому site — PASS. Поточна production БД ще не змінювалася.
- Паралельний HEAD `d5dc0bffb` змінює лише migration ops/docs; runtime CRM/Vue
  після спільної бази не змінені. Communication guards ще не реалізовані;
  ця викладка їх не замінює й не дозволяє робочий імпорт.

## Погоджуваний точний доступ

Тільки VPS `crm`, тільки site `crm.recuite.com`. Секретні значення не виводяться в chat,
argv, Git або звичайні логи; резервні копії лишаються на VPS.

| Файл / ресурс | Дозволена дія |
|---|---|
| `/var/lib/docker/volumes/frappe_sites/_data/crm.recuite.com/site_config.json` | Штатний Frappe ORM використовує `db_name`, optional `db_user`, `db_password`, `db_type`, `db_host`, `db_port`. Прочитати/тимчасово встановити/точно відновити `maintenance_mode`, `mute_emails`, `pause_scheduler`; перевірити `host_name`. Решту blob лише зберегти/хешувати/відновити без перегляду значень. |
| `/var/lib/docker/volumes/frappe_sites/_data/common_site_config.json` | Прочитати тільки успадковані `db_user`, `db_type`, `db_host`, `db_port`, `redis_cache`, `redis_queue`, `redis_socketio`, `socketio_port`; не змінювати. |
| `/var/lib/docker/volumes/frappe_sites/_data/apps.txt` | Зберегти оригінал та додати тільки `recuite_billing`; не прибирати наявні apps. |
| БД цього site | Перевірити apps/schema/counts/черги й ролі без перегляду секретних credential rows; встановити billing, виконати штатний migrate; зберегти бізнес-картки та файли. |
| Public/private файли site і SQL/config backup | Закрита непрозора повна копія перед зміною, включно з зашифрованими credential rows/ключем у config; без витягування або використання сторонніх секретів. |
| `/opt/frappe-crm/compose.yaml` | Зберегти оригінал; замінити тільки app-image на новий immutable tag/digest. DB/Redis/proxy не пересоздавати. |
| `/opt/frappe-crm/billing-update/20261018/` | Root-private code manifest, receipts, backup/config/app-registry copies та діагностика. Sensitive files0600, dirs0700. |

`/etc/recuite/credentials/frappe.env`, SMTP/Cloudflare/OAuth/телефонні ключі та
Administrator password **не читаються**. Для `compose up --no-deps` тільки app
services використовуються не-секретні DB/ADMIN placeholders, потрібні лише для
парсингу невибраних DB/setup service definitions; їх не передають і не застосовують
до робочої БД. Перевірено: робочий Compose побайтово збігається з reviewed source,
app services не використовують ці два ключі.

## Backup і послідовність

Попередня робоча копія іншої сесії перевірена: 290 tables / 7850 rows,
public0/private1, усі row/DDL/file hashes збігаються; read-lock4.496s.
Backup manifest `b021e6e5554d60d208203abf6a32a90ad1328ac3712cf27199fd47779c606e63`,
restore receipt `66b4060063ddfcc393962adda04e838cd7b415a37b0bf42534b688c892a5320f`.
Каталоги: `/opt/frappe-crm/migration-production/20261017/backup-preliminary-v2`
та `restore-preliminary-v2`. Це доказ відновлення початкової версії,
не заміна фінальної копії перед зміною.

Після погодження цього доступу:

1. Перевірити незмінну базу, відсутність конфліктів UA DocTypes/custom fields та
   іншого File override, наявні ролі/черги, вільне місце й MemAvailable≥2048MiB.
2. У вікні до 5 хвилин зберегти режими, увімкнути maintenance/mute/pause та
   зупинити frontend/websocket/queue-short/queue-long/scheduler. Backend поки
   лишається тільки для перевіреного backup CLI, без публічного frontend/черг;
   після backup зупинити також backend до schema upgrade. Proxy, DB і Redis
   працюють. Це закриває зовнішні записи до backup й під час зміни.
3. Зняти фінальну закриту копію БД, config, public/private files та apps.txt,
   перевірити hashes і стабільність. Якщо потрібен DB read-lock, максимум60s;
   прострочення/помилка припиняє оновлення. Не використовувати тестовий site/backup.
4. На новому образі додати app у registry, виконати
   `bench --site crm.recuite.com install-app recuite_billing`, потім migrate.
5. Перевірити нові DocTypes/custom fields, незмінні бізнес-counts, штатні права
   Administrator, доступність frontend assets та відсутність нових листів/фінансових
   записів. Жодних synthetic fixtures чи тестів на production.
6. Змінити тільки app image в Compose, запустити тільки потрібні app services,
   перевірити health/pong/HTTPS/assets/socket та доступний authenticated UI.
   Точно відновити початкові mute/pause/maintenance і початковий стан служб;
   не вмикати раніше вимкнені канали або jobs.

Якщо перевірка не пройшла до відкриття записів: повернути з цього фінального
checkpoint старі DB/config/apps.txt/Compose та image, потім початкові режими служб.
Не робити uninstall або volume deletion. Після відкриття записів автоматичний
відкат БД заборонений: потрібне окреме рішення щодо нових даних.

# Handoff: слой юридической верификации требований (сессия 29–30.07.2026)

## Цель

**Сессия не ограничена по времени. Работа считается законченной только тогда, когда ВЕСЬ перечисленный ниже флоу юриста работает end-to-end, качественно и проверен агентом-верификатором:**

1. Юрист регистрируется на сайте, логинится, подаёт заявку «стать экспертом» из кабинета.
2. После верификации админом получает статус эксперта: в кабинете появляются дешборд, очередь «Ждут проверки», рейтинг.
3. Открывает требование, оставляет заключение с вердиктом → премодерация → публикация → заключение видят все посетители.
4. Пользователи голосуют «Помогло»/«Не помогло», на строке требования появляется бейдж «Подтвердили N юристов», админ может оставить официальный ответ.
5. Юристу приходят in-app уведомления: «ваше заключение опубликовано/отклонено», «на площадке новое требование — оставьте заключение».
6. Дешборд юриста — красивый, с анимированными элементами (счётчики, плавные появления), показывает его вклад и полезность.
7. Юрист может пошерить свою статистику: кнопка «Поделиться» генерирует изображение-карточку со статистикой (имя, регалии, цифры, брендинг InspectorX) — скачивание PNG + share-ссылка в Telegram.
8. Рейтинг между юристами: юрист видит своё место и топ-10 по полезности.

Готово = все 8 пунктов реализованы, `npm run build` и `npm run lint` зелёные, `supabase db reset --local` проходит, Playwright-скриншоты сняты и просмотрены, **протокол E2E-верификации (раздел «Верификация end-to-end») пройден отдельным агентом-верификатором на 100% pass**, финальный отчёт с чек-листом наката на прод написан. Не останавливаться на частичном результате — итерировать до полного прохождения. Вне скоупа только: биллинг юристов, uz/en-тексты, связка вердиктов с `change_events`, ограничение доступа юриста по выбранным продуктам.

**Качество обязательно.** Каждая фича доводится до отполированного состояния (loading/empty/error, тёмная тема, мобильная вёрстка), а не «работает в happy path».

**Этот документ — рамка, а не полная карта кода.** Мы могли не учесть детали реализации. Если реальность кода расходится со спекой — изучи код, прими лучшее решение сам и зафиксируй его в финальном отчёте в разделе «Отступления от спеки». Додумывать разрешено и ожидается; менять принятые продуктовые решения — нет.

## Правила безопасности данных (важнее всего остального)

- **Ничего не удалять.** Никаких `drop table/column/type`, `truncate`, `delete` по данным — ни в миграциях, ни запросами. Только создавать и добавлять. (Исключения: `drop policy` + пересоздание при расширении RLS-политик — можно; операции на локальной тестовой базе при E2E — можно.)
- **Прод не трогать вообще**: ни DDL, ни DML с service-ключом. Накат миграции — только руками владельца.
- Если по ходу выяснится, что что-то *нужно* удалить, переименовать или изменить несовместимо — НЕ делать, а записать в отдельный журнал `docs/superpowers/specs/2026-07-29-lawyer-reviews-followups.md`: что, зачем, каким SQL/правкой, какие риски. Владелец применит сам.

Основа — `docs/adr/0001-expert-verification.md` (ADR уже описывает эту фичу: вердикты, апвоуты по модели Reddit, репутация). Этот документ — его первая реализационная итерация. Прочитай ADR перед началом.

## Принятые продуктовые решения (не пересматривать)

1. **Вход юриста бесплатный + ручная верификация админом** — как с подписками (`is_subscribed`). Никакого биллинга для юристов сейчас.
2. **Опубликованные комментарии и бейдж видят все** (anon и authenticated). Details требования остаются под пейволлом как есть.
3. **Премодерация**: комментарий создаётся в статусе `pending`, публикует админ через service_role. Отказ публикации не показывается публично.
4. **Скоуп сессии**: заявка юриста, заключение с вердиктом, голоса «помогло/не помогло», официальный ответ админа, бейдж, дешборд юриста с анимациями, очередь «Ждут проверки», in-app уведомления юристу, share-карточка статистики, рейтинг юристов. Отдельная публичная страница-профиль юриста — следующая итерация.
5. **Доступ юриста к закрытому контенту**: верифицированный юрист читает `requirement_details` (и faqs/citations/revisions) наравне с подписчиком — расширяем существующие политики. Ограничение «только по выбранным продуктам» — итерация 2 (маппинг требование→продукт через applicability-скоупы слишком тяжёл для RLS за одну ночь).
6. **`trust_label` требования сегодня не трогаем.** Бейдж считается из опубликованных комментариев, а не из `trust_label`. Автоматическая связка «вердикт „устарело“ → `change_event`» — итерация 2 (записать в ADR как открытый вопрос, не кодировать).

## Модель данных (новая миграция `supabase/migrations/20260729<HHMMSS>_lawyer_reviews.sql`)

Миграция строго аддитивная — образец стиля: `20260712100000_services_module.sql`. RLS-паттерны копировать из `20260711120001_rls.sql`.

### `lawyer_profiles` — заявка и статус юриста

```sql
create type public.lawyer_status as enum ('pending', 'verified', 'rejected');

create table public.lawyer_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null,          -- как подписываются комментарии
  credentials text not null,            -- регалии свободным текстом: стаж, место работы
  license_no text,                      -- номер лицензии/удостоверения адвоката, если есть
  specializations text,                 -- свободным текстом: «фарма, ВЭД, маркировка»
  status public.lawyer_status not null default 'pending',
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
```

RLS: `insert` — authenticated, `with check (user_id = auth.uid() )`, и только со статусом pending (не давать грант на колонку `status`, как сделано с `profiles.is_subscribed`: `revoke insert/update... ; grant insert (user_id, display_name, credentials, license_no, specializations) ...`). `select`: own read всегда + публичное чтение строк `status = 'verified'` (чтобы подписать комментарий именем юриста). `update` собственных полей заявки — по желанию, можно опустить в MVP. Верификация — только service_role.

Функция-помощник по образцу `is_subscriber()` (security definer, stable):

```sql
create function public.is_verified_lawyer() returns boolean ...
  select exists (select 1 from public.lawyer_profiles lp
    where lp.user_id = (select auth.uid()) and lp.status = 'verified');
```

### Доступ юриста к закрытому контенту

Существующие политики `"subscriber read"` на `requirement_details`, `requirement_faqs`, `requirement_citations`, `requirement_revisions` заменить (drop/create в этой же миграции) на вариант `using (( public.is_subscriber() or public.is_verified_lawyer() ) and exists (...))` — внутренний exists-подзапрос не менять.

### `requirement_reviews` — комментарий юриста с вердиктом

```sql
create type public.review_verdict as enum ('confirm', 'inaccurate', 'outdated', 'addition');
-- подтверждаю / есть неточность / устарело / дополнение
create type public.review_status as enum ('pending', 'published', 'rejected');

create table public.requirement_reviews (
  id uuid primary key default gen_random_uuid(),
  requirement_id uuid not null references public.requirements(id) on delete cascade,
  lawyer_id uuid not null references public.lawyer_profiles(user_id) on delete cascade,
  verdict public.review_verdict not null,
  comment_text text not null,           -- фронт валидирует минимум ~20 символов
  status public.review_status not null default 'pending',
  official_reply text,                  -- ответ команды InspectorX, пишет только service_role
  official_replied_at timestamptz,
  published_at timestamptz,
  created_at timestamptz not null default now()
);
create index requirement_reviews_req_idx on public.requirement_reviews (requirement_id, status);
create index requirement_reviews_lawyer_idx on public.requirement_reviews (lawyer_id);
```

RLS: `insert` — authenticated, `with check (lawyer_id = auth.uid() and public.is_verified_lawyer())`; статус клиенту не отдавать в грант (всегда default pending), `official_reply` — тоже. `select`: публично (anon+authenticated) строки `status = 'published'` при условии, что требование published (паттерн `"read teaser of published"`); own read юристу — все свои в любом статусе (чтобы видел «на модерации»). Публикация/отклонение/официальный ответ — service_role.

Ограничение от спама: не больше одного pending-комментария юриста на одно требование — `create unique index ... on requirement_reviews (lawyer_id, requirement_id) where status = 'pending'`.

### `review_votes` — голоса «помогло / не помогло»

```sql
create table public.review_votes (
  review_id uuid not null references public.requirement_reviews(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  vote smallint not null check (vote in (1, -1)),   -- 1 = помогло, -1 = не помогло
  created_at timestamptz not null default now(),
  primary key (review_id, user_id)
);
```

**Точный флоу голосования (реализовать ровно так):**
- один голос на пользователя на комментарий (PK это гарантирует);
- голос можно **изменить** (помогло → не помогло: upsert / update own) и **снять** (delete own);
- за свой комментарий голосовать нельзя (`with check`: `not exists (select 1 from requirement_reviews r where r.id = review_id and r.lawyer_id = auth.uid())`);
- голосовать можно только за комментарии в статусе `published`;
- anon видит счётчики, но не кнопки — клик по месту кнопок ведёт на `/login`;
- юристы голосуют за комментарии других юристов наравне со всеми — так несколько юристов на одном требовании ранжируются между собой (сортировка комментариев: сначала по `helpful - not_helpful` убыв., затем по дате).

RLS: `insert`/`update`/`delete` — authenticated, own (`user_id = auth.uid()`), с условиями выше. `select` own — для отметки «ваш голос». Публичные счётчики — через view:

```sql
create view public.review_vote_counts with (security_invoker = off) as
  select review_id,
         count(*) filter (where vote = 1)::int  as helpful,
         count(*) filter (where vote = -1)::int as not_helpful
  from public.review_votes group by review_id;
grant select on public.review_vote_counts to anon, authenticated;
```

### `lawyer_stats` и счётчик подтверждений — «калькулятор»

Две агрегатные view (обе `security_invoker = off`, grant select anon+authenticated, только по published):

```sql
-- бейдж на требовании: сколько юристов подтвердили / оставили замечания
create view public.requirement_review_stats as
  select requirement_id,
         count(*) filter (where verdict = 'confirm')::int as confirms,
         count(*) filter (where verdict in ('inaccurate','outdated'))::int as disputes,
         count(*)::int as total
  from public.requirement_reviews where status = 'published' group by requirement_id;

-- дешборд юриста: его вклад и полезность
create view public.lawyer_stats as
  select r.lawyer_id,
         count(distinct r.requirement_id)::int as requirements_reviewed,
         count(*)::int as reviews_published,
         coalesce(sum(v.helpful), 0)::int as helpful_total,
         coalesce(sum(v.not_helpful), 0)::int as not_helpful_total
  from public.requirement_reviews r
  left join public.review_vote_counts v on v.review_id = r.id
  where r.status = 'published' group by r.lawyer_id;
```

### `lawyer_notifications` — in-app уведомления юристу

Существующую `user_notifications` не переиспользовать (она зарезервирована под цепочку change_events и закрыта для клиентского insert) — завести отдельную таблицу:

```sql
create type public.lawyer_notification_kind as enum
  ('review_published', 'review_rejected', 'new_requirement');

create table public.lawyer_notifications (
  id uuid primary key default gen_random_uuid(),
  lawyer_id uuid not null references public.lawyer_profiles(user_id) on delete cascade,
  kind public.lawyer_notification_kind not null,
  requirement_id uuid references public.requirements(id) on delete cascade,
  review_id uuid references public.requirement_reviews(id) on delete cascade,
  is_read boolean not null default false,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index lawyer_notifications_lawyer_idx on public.lawyer_notifications (lawyer_id, is_read, created_at desc);
```

RLS — точная копия паттерна `user_notifications`: own read; own update, но грантом только `(is_read, read_at)`; клиентский insert запрещён. Писатели — триггеры (`security definer`):

- `after update` на `requirement_reviews`: переход `pending → published` → уведомление `review_published` автору; `pending → rejected` → `review_rejected`;
- `after insert/update` на `requirements`: когда `status` становится `published` — по одному уведомлению `new_requirement` каждому verified-юристу (на старте юристов мало, объём безопасен; в триггере ограничиться `on conflict do nothing`-семантикой, не падать).

UI: колокольчик/счётчик непрочитанных в кабинете юриста, список уведомлений с человеческими текстами из `ru.ts`, клик по `new_requirement` ведёт к требованию, отметка прочитанного — по клику.

### Рейтинг юристов

На базе `lawyer_stats`: ранжирование по `helpful_total` (при равенстве — по `reviews_published`). Отдельная view `lawyer_leaderboard` (`security_invoker = off`, публичный select) с `rank() over (...)`, полями display_name/credentials из verified-профилей и цифрами. В дешборде юриста: крупный блок «Ваше место: №K из N» + таблица топ-10 (своя строка подсвечена). Публичной страницы не делать.

### Уведомление модератору

Триггер `after insert` на `requirement_reviews` → `public.notify_admin_telegram(...)` по точному образцу `20260727120000_lead_notifications.sql` (`security definer`, исключение никогда не роняет вставку, при отсутствии секретов молча пропускает).

## Слой данных (`src/data/`)

Не обходить `index.ts` — компоненты ходят только через хуки. После миграции регенерировать `src/lib/database.types.ts`.

- `types.ts`: типы `LawyerReview { id, requirementId, verdict, commentText, status, lawyerName, credentials?, officialReply?, helpful, notHelpful, myVote: 1 | -1 | null, createdAt }`, `RequirementReviewStats { confirms, disputes, total }`, `LawyerStats`. В `RequirementCard` добавить поле `reviews: LawyerReview[]` (без `Gated` — публичные).
- `real.ts`: `fetchRequirementReviewsReal(requirementId, userId?)` (published + свои pending для юриста; join имени из `lawyer_profiles`, счётчики из `review_vote_counts`, `myVote` из own-select `review_votes`), `setReviewVote(reviewId, vote | null)` (upsert/delete), `submitLawyerReview()`, `submitLawyerApplication()`, `fetchMyLawyerProfileReal()`, `fetchLawyerStatsReal()`, `fetchReviewQueueReal()`, `fetchReviewStatsForProductReal(requirementIds)` (для бейджей — один запрос к `requirement_review_stats`).
- `index.ts`: в композицию карточки. Для мок-требований (`isMockRequirementId`) — пустой список или одна демо-фикстура в `mock/fixtures.ts` (по вкусу; демо-фикстура лучше покажет UI на молоке/парацетамоле). Паттерн фильтрации мок-id смотри в `useAskQuestion` (`hooks.ts` ~180).
- `hooks.ts`: `useLawyerReviews(requirementId)` — ключ `['lawyer-reviews', requirementId, session?.user.id ?? 'anon']`; мутации `useSubmitLawyerReview`, `useSetReviewVote` (с оптимистичным обновлением), `useLawyerApplication`, `useMarkNotificationRead` с `invalidateQueries`; `useLawyerStats()`, `useReviewQueue()`, `useLawyerNotifications()` (с умеренным `refetchInterval` ~60с), `useLeaderboard()`. Счётчики для бейджей — один агрегирующий запрос `['review-stats', productId]` по requirement_ids продукта.
- `src/app/auth.tsx`: расширить select профиля/контекст полем `lawyerStatus` (запрос `lawyer_profiles` own read), по аналогии с `realSubscriber`.

## UI (кокпит C)

Все новые строки — в `src/i18n/ru.ts`, секция `requirement`, новая под-секция `lawyerReviews` (плюс `cabinet.lawyer` для заявки). Не хардкодить.

### Матрица состояний (реализовать все четыре роли)

| Состояние | Секция на карточке | Голоса | Кабинет |
|---|---|---|---|
| anon | видит published-комментарии, бейджи, счётчики | счётчики без кнопок; клик → `/login` | — |
| юзер залогинен | то же | кнопки «Помогло»/«Не помогло», свой голос подсвечен, повторный клик снимает | карточка «Вы юрист? Станьте экспертом» |
| юрист pending | то же, что юзер | то же | «Заявка на рассмотрении» (форма скрыта) |
| юрист verified | + кнопка «Оставить заключение», + свои pending-комментарии с пометкой «на модерации» | голосует за чужие, за свои — кнопки скрыты | дешборд + очередь «Ждут проверки» |

Кейс «reject»: юрист со статусом `rejected` видит «Заявка отклонена» и может подать заново (upsert own строки обратно в pending — предусмотреть в RLS/грантах).

### Элементы

1. **Секция в раскрытой карточке** — `src/pages/c/CRequirementCard.tsx`, новая `<section>` после FAQ (~строка 206), перед панелью кнопок. `CEyebrow` «Проверка юристами». Каждый комментарий: чип вердикта (confirm — позитивный, inaccurate/outdated — предупреждающий, addition — нейтральный; по образцу `CDeonticChip` из `src/pages/c/ui.tsx`), имя + регалии юриста, текст, кнопки голоса со счётчиками, при наличии — блок «Ответ InspectorX» с визуальной отметкой команды (по стилю `CTrustStamp`/`CSeal`). Сортировка — по полезности (см. флоу голосования). Дисклеймер мелким текстом: «Мнение специалиста, не официальная юридическая консультация». Пустое состояние: «Это требование ещё не проверено юристом».
2. **Диалог «Оставить заключение»** по образцу `AskQuestionDialog.tsx`: выбор вердикта (4 радио-варианта с короткими описаниями), textarea (мин ~20 символов, счётчик символов), после отправки — «Отправлено на модерацию». Обработать ошибку вставки (RLS-отказ) человеческим текстом.
3. **Бейдж на строке требования** — `src/pages/c/CRequirementList.tsx`, `CRow`, рядом с чипом `row.underReview` (~строка 156), тот же класс чипа. Данные из `requirement_review_stats`: «Подтвердил юрист» при confirms=1, «Подтвердили N юристов» при N≥2; если confirms=0, но disputes>0 — «Есть замечание юриста».
4. **Заявка юриста** — блок в `src/pages/c/CCabinetPage.tsx` (форма: display_name, credentials, license_no, specializations). Отдельный маршрут не заводить.
5. **Дешборд юриста** (кабинет, только verified) — на существующих `CStatTile` + `CountUp` из `ui.tsx`, данные из `lawyer_stats`: «Проверено требований», «Заключений опубликовано», «Помогло ×N» (и рядом мелко not_helpful). Плюс список своих последних заключений со статусами (pending/published/rejected) и голосами, блок рейтинга («Ваше место: №K из N» + топ-10), колокольчик уведомлений. Анимации: `CountUp` для цифр, плавное появление блоков (CSS transitions/`animate-*` Tailwind, без новых тяжёлых зависимостей), аккуратные hover-состояния. Дешборд — витрина фичи, он должен выглядеть дорого.
6. **Очередь «Ждут проверки»** (кабинет, только verified): до 10 последних published-требований без единого published/pending-заключения, каждая строка — ссылка на страницу продукта. Один агрегирующий запрос, без пагинации.
7. **Share-карточка статистики**: кнопка «Поделиться» в дешборде → генерируется изображение-карточка (имя, регалии, «Проверено X требований · Помогло N предпринимателям», место в рейтинге, логотип/домен inspectorx.uz) в стиле кокпита. Реализация: отрисовать карточку как скрытый DOM/SVG фиксированного размера (1200×630) и сконвертировать в PNG через canvas (если нужна библиотека — взять лёгкую вроде `html-to-image`; решение за исполнителем). UX: превью карточки в диалоге, кнопки «Скачать PNG» и «Поделиться в Telegram» (`https://t.me/share/url?url=<https://inspectorx.uz>&text=<текст со статистикой>`; изображение юрист прикладывает из скачанного файла). Карточка обязана хорошо выглядеть в обеих темах — выбрать одну фиксированную тему для изображения.

### Планка качества UI

- Иконки — `lucide-react` (уже в проекте): вердикты (например `CircleCheck` / `TriangleAlert` / `Clock` / `MessageSquarePlus`), голоса (`ThumbsUp`/`ThumbsDown`), печать команды (`BadgeCheck`). Размер и толщина — как у существующих иконок кокпита.
- Все новые блоки обязаны иметь три состояния: loading (`skeleton.tsx`), пустое (осмысленный текст), ошибка. Никаких «мигающих» перескоков вёрстки.
- Тёмная тема и мобильная ширина 375px — обязательны (скрипт `shot.mjs` и так снимает light/dark × 1440/375 — все четыре снимка должны выглядеть аккуратно, проверить глазами через Read).
- Оптимистичное обновление голосов (`onMutate` в мутации или мгновенный локальный пересчёт) — клик не должен ждать сервер.
- Цвета/радиусы/типографика — только существующие токены кокпита, ничего нового не изобретать.

## Порядок работы и проверка

1. Прочитать `docs/adr/0001-expert-verification.md`, `20260711120001_rls.sql`, `20260727120000_lead_notifications.sql`, `src/data/index.ts`.
2. Миграция → `supabase db start && supabase db reset --local` до зелёного.
3. Регенерация `database.types.ts` (из локальной базы: `supabase gen types typescript --local`).
4. Слой данных → хуки → UI.
5. `npm run build` (это же и тайпчек), `npm run lint`.
6. Скриншоты: `node scripts/shot.mjs product/<id> lawyer-reviews <steps>` со steps, раскрывающим карточку с комментарием; открыть все четыре снимка через Read и проверить глазами; консольные ошибки в stdout = блокер. Прогнать `node scripts/walkthrough.mjs` — ничего не сломано.
7. **E2E-верификация отдельным агентом** (см. следующий раздел) — обязательна, не пропускать.
8. Коммиты — conventional по-русски (`feat(reviews): …`), работать в ветке `feat/lawyer-reviews`, PR на `main`, **не мерджить** — merge = автодеплой фронта на прод, а миграция на прод ещё не накатана.
9. Финальный отчёт в `docs/superpowers/specs/2026-07-29-lawyer-reviews-report.md`: что сделано, что отложено, отчёт верификатора, и **чек-лист для утра**: (а) выполнить SQL миграции в SQL-редакторе прод-проекта `kcjlrvgjtoefqgzxuizz`, (б) проверить REST-запросом с service-ключом из `.env.importer`, (в) смерджить PR, (г) верифицировать первого юриста руками (SQL `update lawyer_profiles set status='verified'...`), (д) SQL-сниппеты для модерации: publish/reject комментария, official_reply.

## Верификация end-to-end (агент-верификатор — обязательный этап)

После завершения реализации запустить **отдельного субагента-верификатора** (свежий контекст, без знания о том, как писался код), который на локальной базе (`supabase db reset --local` + dev-сервер) проходит весь флоу и пишет отчёт. Верификатор не чинит код — только фиксирует проблемы; чинит основная сессия, затем верификация повторяется до чистого прогона.

**Позитивный сценарий (SQL через локальный psql/supabase + Playwright для UI):**

1. Создать тестового юзера A (юрист) и юзера B (голосующий) в локальном auth (email-confirm локально отключён либо подтвердить через SQL).
2. A подаёт заявку юриста из кабинета → строка в `lawyer_profiles` со статусом `pending`, кабинет показывает «на рассмотрении».
3. SQL от имени service_role: `status='verified'` → кабинет A показывает дешборд и очередь «Ждут проверки».
4. A открывает требование, оставляет заключение с вердиктом → строка `pending`, публично не видна (проверить анонимным запросом), A видит её с пометкой «на модерации».
5. SQL: publish → комментарий виден anon (Playwright без логина), бейдж «Подтвердил юрист» появился на строке требования.
6. B голосует «Помогло» → счётчик 1; меняет на «Не помогло» → helpful 0 / not_helpful 1; снимает голос → 0/0. Всё без перезагрузки страницы.
7. SQL: official_reply → блок «Ответ InspectorX» отрисован.
8. Публикация заключения из шага 5 создала юристу A уведомление `review_published`; SQL-публикация нового требования создала `new_requirement`; колокольчик показывает счётчик, отметка «прочитано» работает и переживает перезагрузку.
9. Дешборд A: цифры совпадают с фактическими данными, блок рейтинга показывает место A, топ-10 отсортирован по helpful.
10. Share: диалог открывается, PNG скачивается, файл не пустой и содержит ожидаемые цифры (открыть изображение через Read и посмотреть), ссылка Telegram корректна.
11. Удаление (только локальная база): SQL delete заключения → голоса и уведомления каскадно удалились, бейдж исчез, дешборд и рейтинг пересчитались, UI нигде не падает.

**Негативные проверки (все должны быть ЗАПРЕЩЕНЫ):**

- anon: insert в `lawyer_profiles`, `requirement_reviews`, `review_votes`;
- юзер без verified-статуса: insert в `requirement_reviews`; чтение чужих `lawyer_notifications`;
- любой клиент: insert в `lawyer_notifications`; update её полей кроме `is_read`/`read_at`;
- юрист A: голос за собственный комментарий;
- любой клиент: update `requirement_reviews.status` / `official_reply`, update `lawyer_profiles.status`;
- select чужих голосов из `review_votes`; select чужого pending-комментария;
- второй pending-комментарий A на то же требование.

**Отчёт верификатора** — таблица «шаг → ожидание → факт → pass/fail» по всем пунктам, вкладывается в финальный отчёт. Фича считается готовой только при 100% pass.

## Жёсткие ограничения

- **Правила безопасности данных** (раздел в начале документа) — приоритет №1: ничего не удалять, прод не трогать, отложенные удаления/несовместимые изменения — в `2026-07-29-lawyer-reviews-followups.md`.
- Не обходить `src/data/index.ts` прямыми запросами из компонентов.
- Пейволл не ослаблять: изменение политик details — строго добавление `or is_verified_lawyer()`, ничего больше.
- Новые npm-зависимости — только лёгкие и только при реальной необходимости (кандидат: `html-to-image` для share-карточки); каждую добавленную зависимость перечислить в отчёте с обоснованием.
- `docs/LAUNCH_CHECKLIST.md` (заморозка): по завершении дописать в `docs/TARGET_FORMAT.md` короткий раздел о слое юр-верификации, а в ADR-0001 отметить статус «реализовано, итерация 1» со ссылкой на этот handoff.
- Вне скоупа: биллинг юристов, отдельные публичные страницы-профили юристов, email/Telegram-пуши юристам (in-app — в скоупе), uz/en-тексты, связка вердиктов с `change_events`, ограничение доступа юриста по выбранным продуктам.

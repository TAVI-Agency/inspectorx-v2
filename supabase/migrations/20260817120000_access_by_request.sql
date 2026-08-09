-- Доступ только по одобренной заявке (владелец апрувит в Telegram).
--
-- Идея: самостоятельная регистрация выключается (Auth → Sign Up, руками
-- владельца — вне этой миграции, см. docs/ACCESS_GATE_SETUP.md). Заявка на
-- доступ (бывшая форма /register, форма /pricing) теперь обязательно несёт
-- email; уведомление в Telegram (20260727120000_lead_notifications.sql)
-- получает инлайн-кнопки «Одобрить»/«Отклонить». Нажатие обрабатывает
-- Vercel-функция api/telegram/webhook.ts: approve — приглашает пользователя
-- письмом (auth.admin.inviteUserByEmail) и включает profiles.is_subscribed;
-- reject — просто закрывает заявку. Callback-данные — `sr:approve:<id>` /
-- `sr:reject:<id>`, обрабатываются идемпотентно (см. вебхук).

-- ----------------------------------------------------------------------------
-- 1. email на заявке + колоночный грант insert (в стиле profiles/lawyer_profiles)
-- ----------------------------------------------------------------------------

alter table public.subscription_requests add column if not exists email text;

-- Раньше insert был доступен на весь набор колонок (табличный грант по
-- умолчанию — subscription_requests единственная из «заявочных» таблиц, где
-- его явно не сужали). Теперь сужаем: заявитель вставляет только свои
-- данные, status/note/handled_at/id/created_at остаются за апрувом владельца.
revoke insert on public.subscription_requests from anon, authenticated;
grant insert (full_name, contact, company, email, user_id)
  on public.subscription_requests to anon, authenticated;

-- ----------------------------------------------------------------------------
-- 2. notify_admin_telegram: второй (необязательный) параметр reply_markup.
-- Идентичность функции в Postgres — это имя + ПОЛНЫЙ список типов
-- аргументов; CREATE OR REPLACE с добавленным параметром (даже с default)
-- не заменяет старую функцию notify_admin_telegram(text), а создал бы рядом
-- отдельную перегрузку notify_admin_telegram(text, jsonb) — в базе остались
-- бы две функции с одним именем. Поэтому явно дропаем старую однопараметровую
-- версию и создаём новую; вызовы из notify_new_request ниже всегда идут с
-- двумя аргументами (для content_requests/user_questions markup = null).
-- ----------------------------------------------------------------------------

drop function if exists public.notify_admin_telegram(text);

create function public.notify_admin_telegram(
  message text,
  reply_markup jsonb default null
)
returns void
language plpgsql
security definer
set search_path = public, net, extensions
as $$
declare
  token text;
  chat  text;
  body  jsonb;
begin
  select decrypted_secret into token
    from vault.decrypted_secrets where name = 'telegram_bot_token';
  select decrypted_secret into chat
    from vault.decrypted_secrets where name = 'telegram_chat_id';

  if token is null or chat is null then
    raise warning 'notify_admin_telegram: секреты не заведены, уведомление пропущено';
    return;
  end if;

  body := jsonb_build_object('chat_id', chat, 'text', message);
  if reply_markup is not null then
    body := body || jsonb_build_object('reply_markup', reply_markup);
  end if;

  perform http_post(
    url     := 'https://api.telegram.org/bot' || token || '/sendMessage',
    body    := body,
    headers := '{"Content-Type": "application/json"}'::jsonb
  );
exception when others then
  -- Заявка дороже уведомления: любая ошибка — предупреждение, не отказ вставки.
  raise warning 'notify_admin_telegram: %', sqlerrm;
end;
$$;

revoke all on function public.notify_admin_telegram(text, jsonb) from public;
revoke all on function public.notify_admin_telegram(text, jsonb) from anon, authenticated;

-- ----------------------------------------------------------------------------
-- 3. notify_new_request: заявка на подписку получает email в тексте и
-- инлайн-кнопки апрува. Остальные ветки case (content_requests, user_questions)
-- не меняются — markup для них остаётся null, notify_admin_telegram шлёт
-- обычный текст (обратная совместимость).
-- ----------------------------------------------------------------------------

create or replace function public.notify_new_request()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  msg      text;
  markup   jsonb;
  stamp    text := to_char(now() at time zone 'Asia/Tashkent', 'DD.MM.YYYY HH24:MI');
begin
  case tg_table_name
    when 'subscription_requests' then
      msg := '🔔 Заявка на доступ' || E'\n'
          || 'Имя: '      || coalesce(new.full_name, '—') || E'\n'
          || 'Контакт: '  || coalesce(new.contact, '—')   || E'\n'
          || 'Email: '    || coalesce(new.email, '—')     || E'\n'
          || 'Компания: ' || coalesce(new.company, '—')   || E'\n'
          || stamp;
      -- Владелец жмёт кнопку прямо в чате; callback_data разбирает
      -- api/telegram/webhook.ts (Vercel), id заявки — в открытом виде
      -- (заявка и так читается только владельцем/service_role).
      markup := jsonb_build_object(
        'inline_keyboard', jsonb_build_array(
          jsonb_build_array(
            jsonb_build_object('text', '✅ Одобрить', 'callback_data', 'sr:approve:' || new.id::text),
            jsonb_build_object('text', '❌ Отклонить', 'callback_data', 'sr:reject:' || new.id::text)
          )
        )
      );

    when 'content_requests' then
      msg := '📋 Заявка на контент (' || coalesce(new.kind::text, '—') || ')' || E'\n'
          || 'Запрос: ' || coalesce(new.query_text, '—') || E'\n'
          || coalesce('Комментарий: ' || new.comment || E'\n', '')
          || stamp;

    when 'user_questions' then
      msg := '❓ Вопрос пользователя' || E'\n'
          || case when new.is_urgent then 'СРОЧНЫЙ' || E'\n' else '' end
          || left(coalesce(new.question_text, '—'), 300) || E'\n'
          || stamp;

    else
      return new;
  end case;

  perform public.notify_admin_telegram(msg, markup);
  return new;
exception when others then
  raise warning 'notify_new_request(%): %', tg_table_name, sqlerrm;
  return new;
end;
$$;

revoke all on function public.notify_new_request() from public;
revoke all on function public.notify_new_request() from anon, authenticated;

-- ----------------------------------------------------------------------------
-- 4. Поиск пользователя по email для approve-флоу.
--
-- auth.admin.inviteUserByEmail на уже существующий email просто вернёт
-- ошибку («уже зарегистрирован»), а не user_id — он нам всё равно нужен,
-- чтобы включить profiles.is_subscribed. auth.users обычным ролям
-- недоступен, отсюда SECURITY DEFINER (стандартный приём для auth.users —
-- тот же, что и в handle_new_user). Выполняет только service_role
-- (Vercel-функция вебхука), больше никому доступ не нужен.
-- ----------------------------------------------------------------------------

create or replace function public.find_user_id_by_email(p_email text)
returns uuid
language sql
stable
security definer
set search_path = public, auth
as $$
  select id from auth.users where lower(email) = lower(p_email) limit 1;
$$;

revoke all on function public.find_user_id_by_email(text) from public;
revoke all on function public.find_user_id_by_email(text) from anon, authenticated;
grant execute on function public.find_user_id_by_email(text) to service_role;

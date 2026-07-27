-- Уведомления о заявках в Telegram (блок A чек-листа запуска).
-- Дизайн: docs/superpowers/specs/2026-07-27-lead-notifications-design.md
--
-- Триггеры на трёх таблицах заявок шлют сообщение боту через pg_net.
-- Секреты (токен бота и chat_id) — в Supabase Vault, в репозиторий не попадают.
-- ГЛАВНОЕ ПРАВИЛО: отказ отправки НИКОГДА не роняет вставку заявки.
--
-- ПОСЛЕ наката выполнить в SQL-редакторе, подставив свои значения:
--   select vault.create_secret('<токен от @BotFather>', 'telegram_bot_token',
--                              'Бот уведомлений о заявках');
--   select vault.create_secret('<ваш chat_id>',         'telegram_chat_id',
--                              'Куда слать уведомления о заявках');
-- Пока секретов нет — уведомления молча пропускаются (так работает локальная база).

create extension if not exists pg_net;

-- ----------------------------------------------------------------------------
-- Отправитель. security definer: читает Vault, недоступный обычным ролям.
-- search_path включает и net, и extensions — pg_net на разных проектах Supabase
-- ставится то в одну схему, то в другую.
-- ----------------------------------------------------------------------------
create or replace function public.notify_admin_telegram(message text)
returns void
language plpgsql
security definer
set search_path = public, net, extensions
as $$
declare
  token text;
  chat  text;
begin
  select decrypted_secret into token
    from vault.decrypted_secrets where name = 'telegram_bot_token';
  select decrypted_secret into chat
    from vault.decrypted_secrets where name = 'telegram_chat_id';

  if token is null or chat is null then
    raise warning 'notify_admin_telegram: секреты не заведены, уведомление пропущено';
    return;
  end if;

  -- Обычный текст без parse_mode: имя клиента с любыми символами не сломает
  -- сообщение и не даст подставить в него разметку.
  perform http_post(
    url     := 'https://api.telegram.org/bot' || token || '/sendMessage',
    body    := jsonb_build_object('chat_id', chat, 'text', message),
    headers := '{"Content-Type": "application/json"}'::jsonb
  );
exception when others then
  -- Заявка дороже уведомления: любая ошибка — предупреждение, не отказ вставки.
  raise warning 'notify_admin_telegram: %', sqlerrm;
end;
$$;

-- Функция шлёт сообщения нашим ботом — посторонним вызывать её нельзя,
-- иначе любой анонимный посетитель завалит нас сообщениями через PostgREST.
revoke all on function public.notify_admin_telegram(text) from public;
revoke all on function public.notify_admin_telegram(text) from anon, authenticated;

-- ----------------------------------------------------------------------------
-- Один триггер на три таблицы: текст собирается по tg_table_name.
-- ----------------------------------------------------------------------------
create or replace function public.notify_new_request()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
declare
  msg      text;
  stamp    text := to_char(now() at time zone 'Asia/Tashkent', 'DD.MM.YYYY HH24:MI');
begin
  case tg_table_name
    when 'subscription_requests' then
      msg := '🔔 Заявка на подписку' || E'\n'
          || 'Имя: '      || coalesce(new.full_name, '—') || E'\n'
          || 'Контакт: '  || coalesce(new.contact, '—')   || E'\n'
          || 'Компания: ' || coalesce(new.company, '—')   || E'\n'
          || stamp;

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

  perform public.notify_admin_telegram(msg);
  return new;
exception when others then
  raise warning 'notify_new_request(%): %', tg_table_name, sqlerrm;
  return new;
end;
$$;

revoke all on function public.notify_new_request() from public;
revoke all on function public.notify_new_request() from anon, authenticated;

-- ----------------------------------------------------------------------------
-- Триггеры (drop if exists — чтобы миграцию можно было накатить повторно).
-- ----------------------------------------------------------------------------
drop trigger if exists notify_on_subscription_request on public.subscription_requests;
create trigger notify_on_subscription_request
  after insert on public.subscription_requests
  for each row execute function public.notify_new_request();

drop trigger if exists notify_on_content_request on public.content_requests;
create trigger notify_on_content_request
  after insert on public.content_requests
  for each row execute function public.notify_new_request();

drop trigger if exists notify_on_user_question on public.user_questions;
create trigger notify_on_user_question
  after insert on public.user_questions
  for each row execute function public.notify_new_request();

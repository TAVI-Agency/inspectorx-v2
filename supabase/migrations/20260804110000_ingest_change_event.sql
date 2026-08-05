-- ============================================================================
-- InspectorX v2 — Задача 39: приём webhook изменений LegalX (Блок 6, контур C)
-- Контракт 3 (payload) — docs/adr/0005-ecosystem-contracts.md, финализирован
-- Задачей 1. change_type ∈ new | amended | repealed | effective_soon (тот же
-- набор, что enum public.change_event_type — совпадение контракта и схемы
-- намеренное).
--
-- LegalX шлёт HTTP POST (pg_net) на PostgREST-RPC public.ingest_change_event.
-- Сигнатура — ingest_change_event(p_secret text, p_payload jsonb): у
-- PostgREST top-level ключи тела запроса маппятся на имена параметров, поэтому
-- тело — КОНВЕРТ с двумя ключами, а не плоский объект контракта (найдено на
-- код-ревью 03.08.2026, задокументировано в ADR-0005, чтобы сторона LegalX не
-- получила «could not find function»):
--
--   POST {SUPABASE_URL}/rest/v1/rpc/ingest_change_event
--   apikey: <anon/publishable ключ InspectorX>
--   Content-Type: application/json
--
--   {
--     "p_secret": "<из Vault LegalX>",
--     "p_payload": {
--       "jurisdiction": "UZ",
--       "act_id": "<uuid в LegalX>",
--       "fragment_ids": ["<uuid>"],
--       "change_type": "new | amended | repealed | effective_soon",
--       "effective_date": "2027-01-01",
--       "summary": "краткое описание изменения"
--     }
--   }
--
-- act_id внутри p_payload — uuid акта В БАЗЕ LEGALX, а change_events.act_id —
-- FK на ЛОКАЛЬНУЮ public.acts: чужой uuid в эту FK-колонку не пишем (нарушил
-- бы FK либо сослался бы не на тот акт). Локальный act_id/paragraph_id
-- оставляем NULL — сопоставление LegalX-идентификаторов с локальными acts
-- делает Impact-маппер (Задача 40) из payload jsonb, который сохраняется
-- целиком (без секрета — он живёт только в p_secret, в БД не попадает).
--
-- Идемпотентности на этом уровне нет: повторная доставка одного события
-- (ретрай/дубль в очереди LegalX) создаёт новую строку change_events —
-- дедупликация делается на стороне Impact-маппера (Задача 40), не здесь.
--
-- Секрет — общий секрет из Vault LegalX (см. ADR-0005, Контракт 3), сверяется
-- с локальным Vault-секретом 'legalx_webhook_secret' по паттерну
-- notify_admin_telegram (20260727120000_lead_notifications.sql).
--
-- ПОСЛЕ наката на прод завести секрет в Vault (Dashboard → Database → Vault,
-- НЕ через SQL-миграцию — секреты в репозиторий не попадают). Пункт в
-- docs/LAUNCH_CHECKLIST.md перед мёржем:
--   select vault.create_secret('<общий секрет из Vault LegalX>',
--                              'legalx_webhook_secret',
--                              'Секрет webhook-а изменений LegalX → ingest_change_event');
-- Локально для теста — тот же insert через supabase db query / psql (см.
-- отчёт задачи, там же тест-строка и её уборка).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- ingest_change_event — точка входа вебхука. security definer: читает Vault
-- (недоступен обычным ролям) и пишет change_events мимо RLS (insert-политики
-- на change_events нет — только subscriber read, см. 20260711120001_rls.sql).
-- search_path закреплён явно (security definer + незафиксированный
-- search_path — стандартная дыра); vault.* вызывается полным именем, поэтому
-- саму схему vault в search_path добавлять не нужно.
-- ----------------------------------------------------------------------------

create or replace function public.ingest_change_event(p_secret text, p_payload jsonb)
returns uuid
language plpgsql
security definer
set search_path = public, pg_temp
as $$
declare
  v_vault_secret   text;
  v_jurisdiction   text;
  v_change_type    text;
  v_effective_date date;
  v_act_id         text;
  v_id             uuid;
begin
  -- 1) Секрет. Отсутствие секрета в Vault и неверный секрет — разные ошибки:
  -- первая говорит эксплуатанту «секрет не заведён», вторая нарочно без
  -- деталей (не подсказывать посторонним вызовам, что именно не так).
  select decrypted_secret into v_vault_secret
    from vault.decrypted_secrets where name = 'legalx_webhook_secret';

  if v_vault_secret is null then
    raise exception 'webhook secret not configured';
  end if;

  if p_secret is null or p_secret <> v_vault_secret then
    raise exception 'invalid secret';
  end if;

  -- 2) Валидация payload Контракта 3.
  v_jurisdiction := p_payload ->> 'jurisdiction';
  if v_jurisdiction is null or v_jurisdiction !~ '^[A-Z]{2}$' then
    raise exception 'ingest_change_event: jurisdiction must be ISO 3166-1 alpha-2, got %',
      coalesce(v_jurisdiction, 'null');
  end if;

  v_change_type := p_payload ->> 'change_type';
  if v_change_type is null
     or v_change_type not in ('new', 'amended', 'repealed', 'effective_soon') then
    raise exception
      'ingest_change_event: change_type must be one of new|amended|repealed|effective_soon, got %',
      coalesce(v_change_type, 'null');
  end if;

  begin
    v_effective_date := nullif(p_payload ->> 'effective_date', '')::date;
  exception when others then
    raise exception 'ingest_change_event: effective_date is not a valid date: %',
      p_payload ->> 'effective_date';
  end;

  -- act_id обязателен контрактом, но title строим defensively: пустой uuid
  -- не должен уронить insert через NOT NULL на title.
  v_act_id := coalesce(p_payload ->> 'act_id', '');

  -- 3) Insert. payload — целиком (нужен Impact-мапперу, Задача 40).
  insert into public.change_events (
    source, act_id, paragraph_id, event_type, title, summary,
    effective_date, jurisdiction, payload
  ) values (
    'jurisbase',
    null,
    null,
    v_change_type::public.change_event_type,
    'LegalX: ' || v_change_type || ' ' || v_act_id,
    p_payload ->> 'summary',
    v_effective_date,
    v_jurisdiction,
    p_payload
  )
  returning id into v_id;

  return v_id;
end;
$$;

comment on function public.ingest_change_event(text, jsonb) is
  'Задача 39 / Контракт 3 (ADR-0005): точка входа webhook-а LegalX. Секрет '
  'сверяется с Vault (legalx_webhook_secret); валидирует jurisdiction/'
  'change_type/effective_date; пишет change_events с source=jurisbase, '
  'act_id/paragraph_id=NULL (сопоставление с локальными acts — Impact-маппер, '
  'Задача 40), payload сохраняется целиком. Возвращает id новой строки.';

-- PostgREST-вызов от LegalX идёт под anon (публичный ключ, без auth) — тело
-- защищено секретом, а не ролью. authenticated этой функции не нужна.
-- "revoke ... from public" одной не хватает: у локального (и прод-) кластера
-- Supabase на схему public настроен default ACL (ALTER DEFAULT PRIVILEGES),
-- который автоматически выдаёт EXECUTE на КАЖДУЮ новую функцию для
-- anon/authenticated/service_role — revoke от public его не отменяет, поэтому
-- authenticated нужно отзывать явно (тот же приём, что в
-- process_lifecycle_transitions / notify_admin_telegram).
revoke all on function public.ingest_change_event(text, jsonb) from public;
revoke all on function public.ingest_change_event(text, jsonb) from authenticated;
grant execute on function public.ingest_change_event(text, jsonb) to anon;

-- =============================================================================
-- Каталог: типы для услуг, добавленных на прод после снапшота v1
-- (research-loop 13.07: 9 услуг — отходы 38.12, бухучёт 69.20, юруслуги 69.10,
-- кадровые агентства 78.10, реклама 73.11, хостинг 63.11, интернет-торговля 47.91,
-- парикмахерские 96.02, связь 61.10). Сид каталога (20260803110000) строился из
-- локальных данных и этих услуг не видел. Идемпотентно; локально — no-op.
--
-- Маппинг ОКЭД → UNSPSC: по конвенции сида (константа с пометкой «уточнить»
-- у неточных кодов). Псевдокоды с нулевым хвостом = уровень сегмента/семейства,
-- та же практика кодового дополнения, что и HS6-паддинг в 20260806090000.
-- Услуга с ОКЭД вне маппинга остаётся сиротой (notice в логе) — лучше пробел,
-- чем неверный код.
-- =============================================================================

do $$
declare
  r record;
  v_type_id uuid;
  v_unspsc text;
begin
  for r in select id, name_ru, oked_code, ikpu_code from public.services where product_type_id is null loop
    v_unspsc := case r.oked_code
      when '38.12' then '76121500'  -- сбор и вывоз отходов (Refuse collection and disposal)
      when '69.20' then '84111500'  -- бухучёт и аудит (Accounting services)
      when '69.10' then '80121600'  -- юридические услуги (уточнить family)
      when '78.10' then '80111600'  -- подбор персонала (Personnel services)
      when '73.11' then '82101500'  -- рекламные агентства (уточнить)
      when '63.11' then '81112000'  -- обработка данных, хостинг (Data services; уточнить)
      when '47.91' then '78102200'  -- интернет-торговля (псевдокод семейства; уточнить)
      when '96.02' then '91111500'  -- парикмахерские и салоны (Personal care; уточнить)
      when '61.10' then '83111500'  -- проводная связь (Local telephone service)
      else null
    end;

    if v_unspsc is null then
      raise notice 'catalog_orphan_services: ОКЭД % (услуга %) вне маппинга — пропущена', r.oked_code, r.id;
      continue;
    end if;

    select id into v_type_id from catalog.product_types where unspsc_code = v_unspsc;
    if v_type_id is null then
      insert into catalog.product_types (kind, unspsc_code, name_ru)
      values ('service', v_unspsc, split_part(r.name_ru, ' (', 1))
      returning id into v_type_id;
    end if;

    insert into catalog.country_codes (country, system, code, name, product_type_id)
    values ('UZ', 'oked', r.oked_code, split_part(r.name_ru, ' (', 1), v_type_id)
    on conflict (country, system, code) do update set product_type_id = excluded.product_type_id;

    if r.ikpu_code is not null then
      insert into catalog.country_codes (country, system, code, name, product_type_id)
      values ('UZ', 'ikpu', r.ikpu_code, split_part(r.name_ru, ' (', 1), v_type_id)
      on conflict (country, system, code) do update set product_type_id = excluded.product_type_id;
    end if;

    update public.services set product_type_id = v_type_id where id = r.id;
  end loop;

  -- Добэкофилл applicability по точным кодам (та же логика, что 20260803130000/20260806090000)
  update public.requirement_applicability ra
  set product_type_id = cc.product_type_id
  from public.requirements req, catalog.country_codes cc
  where ra.requirement_id = req.id
    and ra.product_type_id is null
    and ra.scope in ('hs_code', 'ikpu_code', 'oked_code')
    and cc.country = req.jurisdiction
    and cc.code = ra.code;
end $$;

-- =============================================================================
-- Каталог: досоздание типов для товаров, добавленных на прод после снапшота v1
-- (цемент 2523290000, краски 3208, электромобиль 870380, шины 4011 — research-loop 13.07).
-- Сид каталога (20260803110000) строился из локальных данных и этих товаров не видел:
-- на проде они остались без product_type_id, их requirement_applicability — без бэкофилла.
-- Миграция идемпотентна и данные-зависима: обрабатывает ЛЮБЫЕ товары-сироты,
-- локально (где сирот нет) — no-op.
-- HS6-код типа: первые 6 цифр кода товара; короткие коды (3208, 4011)
-- дополняются нулями справа — стандартная практика кодовых дополнений ТН ВЭД.
-- =============================================================================

do $$
declare
  r record;
  v_type_id uuid;
  v_hs6 text;
begin
  for r in select id, name_ru, hs_code from public.products where product_type_id is null loop
    v_hs6 := rpad(substr(r.hs_code, 1, 6), 6, '0');

    select id into v_type_id from catalog.product_types where hs_code = v_hs6;
    if v_type_id is null then
      insert into catalog.product_types (kind, hs_code, name_ru)
      values ('good', v_hs6, split_part(r.name_ru, ' (', 1))
      returning id into v_type_id;
    end if;

    insert into catalog.country_codes (country, system, code, name, product_type_id)
    values ('UZ', 'tnved', r.hs_code, split_part(r.name_ru, ' (', 1), v_type_id)
    on conflict (country, system, code) do update set product_type_id = excluded.product_type_id;

    update public.products set product_type_id = v_type_id where id = r.id;
  end loop;

  -- Добэкофилл applicability по точным кодам — та же логика, что в 20260803130000,
  -- для требований товаров, чьи типы появились только сейчас.
  update public.requirement_applicability ra
  set product_type_id = cc.product_type_id
  from public.requirements req, catalog.country_codes cc
  where ra.requirement_id = req.id
    and ra.product_type_id is null
    and ra.scope in ('hs_code', 'ikpu_code', 'oked_code')
    and cc.country = req.jurisdiction
    and cc.code = ra.code;
end $$;

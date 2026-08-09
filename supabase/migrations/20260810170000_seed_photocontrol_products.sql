-- ============================================================================
-- Сид товаров под фотоконтроль: табак (2402) и бытовая электроника (85).
--
-- ЗАЧЕМ. public.photo_profile_for_product() (20260810100000_photo_runtime.sql)
-- резолвит профиль движка по префиксу public.products.hs_code:
--   tobacco → {2402,2403}, dairy → {0401..0406}, electronics → {84,85}.
-- В каталоге витрины из этих трёх вертикалей был представлен ТОЛЬКО молочный
-- товар 0401201100. Товаров 2402*/2403* и 84*/85* не было ни одного, поэтому
-- api/vision/checklist.ts отдавал 404 {reason:'no_checklist'} для всего, кроме
-- молока, — при том что в базе уже лежат 53 правила пакета tobacco и 34 правила
-- пакета electronics (20260810140000_photo_checks_content.sql).
--
-- Витринные «сигареты» — это НЕ 2402: карточка-флагман витрины (константа
-- CIGARETTES_PRODUCT_ID в src/data/mock/fixtures.ts) указывает на живой товар
-- 2404110001 «стики IQOS» (heat-not-burn), алиас «IQOS». Префикс 2404 ни в
-- один профиль движка не попадает — это отдельная развилка для владельца
-- (расширять ли tobacco до {2402,2403,2404}), НАМЕРЕННО не решаемая здесь:
-- пакет правил tobacco собран под пачку сигарет, а не под стики.
--
-- ЧТО ДОБАВЛЯЕМ. По одному листовому товару на профиль движка, коды взяты
-- из самих профилей inspectorx-vision (config/products/*.yaml), чтобы товар
-- витрины и эталон движка были одним и тем же товаром:
--   tobacco.yaml      hs_code 2402209000  «Сигареты, пачка»
--   electronics.yaml  hs_code 8517620009  «Wi-Fi роутер, коробка»
-- плюс смартфон 8517130000 — второй товар вертикали electronics: спрос на
-- проверку упаковки телефона очевиднее, чем на роутер, а профиль тот же (85).
--
-- КОНВЕНЦИИ (соблюдены как у соседних сидов):
--  * id — детерминированные (md5 от 'inspectorx-photo:<ключ>', раскладка как в
--    scripts/generate_v1_content_migration.mjs); пространство имён своё, эти
--    товары не из снапшота v1;
--  * name_ru — формат «код | официальное описание ТН ВЭД»: витрина режет всё до
--    «|» (officialFromRaw, src/data/real.ts:89);
--  * parent_id не заполняем — в public.products он null у ВСЕХ 265 строк прода,
--    иерархия живёт в hierarchy_path (задел под дерево не используется);
--  * catalog.product_types (HS6) + catalog.country_codes ('UZ','tnved') —
--    обязательны: product_type_id на проде заполнен у всех товаров без
--    исключения, а photo_checklist() умеет матчить применимость и через тип;
--  * search_aliases — иначе товар не найти: поиск (src/data/real.ts:294) бьёт
--    ilike по alias и по name_ru, RPC там нет. Без алиаса «Сигареты» запрос
--    «сигареты» не находил бы вообще ничего (сегодня — ровно так).
--
-- Миграция идемпотентна: on conflict do nothing на каждом insert, тип берётся
-- подзапросом по hs_code (а не по id) — если тип уже заведён другой миграцией,
-- используется существующий.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. catalog.product_types — канонические типы HS6 (ADR-0004)
-- ----------------------------------------------------------------------------
insert into catalog.product_types (id, kind, hs_code, name_ru, name_uz, name_en) values
  ('de352e39-3739-4358-a8bd-2f24727c3618', 'good', '240220',
   'Сигареты, содержащие табак', 'Tarkibida tamaki boʻlgan sigaretalar',
   'Cigarettes containing tobacco'),
  ('5ef6cdad-44e8-7b00-c4d8-6d624cba7b36', 'good', '851762',
   'Аппаратура для передачи или приёма данных (роутеры, коммутаторы)',
   'Maʼlumot uzatish va qabul qilish apparaturasi (routerlar, kommutatorlar)',
   'Apparatus for transmission or reception of data (routers, switches)'),
  ('0daa0bf7-7f91-8913-2024-8e652529cadf', 'good', '851713',
   'Смартфоны', 'Smartfonlar', 'Smartphones')
on conflict (hs_code) do nothing;

-- ----------------------------------------------------------------------------
-- 2. public.products — листовые товары ТН ВЭД-10
-- ----------------------------------------------------------------------------

-- Табак: эталонный товар профиля tobacco (2402 20 900 0 — сигареты с фильтром,
-- прочие). Именно этот код зашит в inspectorx-vision/config/products/tobacco.yaml.
insert into public.products
  (id, hs_code, name_ru, name_uz, name_en, hierarchy_path, complexity_index, product_type_id)
values (
  '5d175374-7588-3926-f912-f9ff79202aae',
  '2402209000',
  '2402 20 900 0 | сигареты, содержащие табак, прочие (пачка с фильтром)',
  '2402 20 900 0 | tarkibida tamaki boʻlgan sigaretalar, boshqalari (filtrli quti)',
  '2402 20 900 0 | cigarettes containing tobacco, other (filter pack)',
  '{"category_name":"24 | Табак и промышленные заменители табака; продукция, содержащая или не содержащая никотин, предназначенная для вдыхания без горения; прочая продукция, содержащая никотин и предназначенная для поступления никотина в организм человека","levels":["2402 | Сигары, сигары с обрезанными концами, сигариллы и сигареты, из табака или его заменителей","2402 2 | сигареты, содержащие табак:","2402 20 | сигареты, содержащие табак","2402 20 900 0 | прочие"]}'::jsonb,
  9,
  (select id from catalog.product_types where hs_code = '240220')
) on conflict (hs_code) do nothing;

-- Электроника, эталон профиля electronics (config/products/electronics.yaml).
insert into public.products
  (id, hs_code, name_ru, name_uz, name_en, hierarchy_path, complexity_index, product_type_id)
values (
  '4eadae66-6ba9-659d-484c-f40a7a6ad378',
  '8517620009',
  '8517 62 000 9 | аппаратура для передачи или приёма голоса, изображений или других данных, прочая (Wi-Fi роутер)',
  '8517 62 000 9 | ovoz, tasvir yoki boshqa maʼlumotlarni uzatish va qabul qilish apparaturasi, boshqalari (Wi-Fi router)',
  '8517 62 000 9 | apparatus for transmission or reception of voice, images or other data, other (Wi-Fi router)',
  '{"category_name":"85 | Электрические машины и оборудование, их части; звукозаписывающая и звуковоспроизводящая аппаратура, аппаратура для записи и воспроизведения телевизионного изображения и звука, их части и принадлежности","levels":["8517 | Телефонные аппараты, включая смартфоны и прочие телефоны для сотовых сетей связи или других беспроводных сетей связи; прочая аппаратура для передачи или приёма голоса, изображений или других данных","8517 6 | прочая аппаратура для передачи или приёма голоса, изображений или других данных:","8517 62 | машины для приёма, преобразования и передачи или восстановления голоса, изображений или других данных, включая коммутационные устройства и маршрутизаторы","8517 62 000 9 | прочие"]}'::jsonb,
  6,
  (select id from catalog.product_types where hs_code = '851762')
) on conflict (hs_code) do nothing;

-- Электроника, потребительский спрос: смартфон (тот же профиль 85).
insert into public.products
  (id, hs_code, name_ru, name_uz, name_en, hierarchy_path, complexity_index, product_type_id)
values (
  'cbdc0fb5-8164-1bb7-fc44-2c52c95bea3e',
  '8517130000',
  '8517 13 000 0 | смартфоны',
  '8517 13 000 0 | smartfonlar',
  '8517 13 000 0 | smartphones',
  '{"category_name":"85 | Электрические машины и оборудование, их части; звукозаписывающая и звуковоспроизводящая аппаратура, аппаратура для записи и воспроизведения телевизионного изображения и звука, их части и принадлежности","levels":["8517 | Телефонные аппараты, включая смартфоны и прочие телефоны для сотовых сетей связи или других беспроводных сетей связи; прочая аппаратура для передачи или приёма голоса, изображений или других данных","8517 1 | телефонные аппараты, включая смартфоны и прочие телефоны для сотовых сетей связи или других беспроводных сетей связи:","8517 13 000 0 | смартфоны"]}'::jsonb,
  6,
  (select id from catalog.product_types where hs_code = '851713')
) on conflict (hs_code) do nothing;

-- ----------------------------------------------------------------------------
-- 3. catalog.country_codes — национальный слой ТН ВЭД UZ (ADR-0004)
--    Только 'tnved': ИКПУ у public.products своей колонки не имеет, и витрина
--    прячет чипы систем, по которым у товара нет собственного кода
--    (fetchCountryCodes, src/data/real.ts) — выдумывать код ИКПУ не станем.
-- ----------------------------------------------------------------------------
insert into catalog.country_codes (country, system, code, name, product_type_id) values
  ('UZ', 'tnved', '2402209000', 'сигареты, содержащие табак, прочие',
   (select id from catalog.product_types where hs_code = '240220')),
  ('UZ', 'tnved', '8517620009', 'аппаратура для передачи или приёма данных, прочая',
   (select id from catalog.product_types where hs_code = '851762')),
  ('UZ', 'tnved', '8517130000', 'смартфоны',
   (select id from catalog.product_types where hs_code = '851713'))
on conflict (country, system, code) do nothing;

-- ----------------------------------------------------------------------------
-- 4. search_aliases — то, чем товар реально находится в поиске.
--    is_default=true задаёт человеческое имя в выдаче (displayName, toHit).
--    РОВНО ОДИН default на товар, и он русский: defaultAliases()
--    (src/data/real.ts:265) собирает Map без фильтра по языку — второй
--    is_default просто перетирает первый, и в выдаче вместо «Сигареты»
--    оказывается «cigarettes» (проверено скриншотом). У товаров v1 default
--    тоже ровно один; три языковых default'а есть только у услуг.
-- ----------------------------------------------------------------------------
insert into public.search_aliases (id, product_id, alias, lang, is_default) values
  ('221cf0d2-0043-e947-5af7-07d606cce9d6', '5d175374-7588-3926-f912-f9ff79202aae', 'Сигареты', 'ru', true),
  ('86fad749-0186-3f22-f7a9-cda32b6d10b1', '5d175374-7588-3926-f912-f9ff79202aae', 'сигареты с фильтром', 'ru', false),
  ('96d61324-8fa4-a6f5-7abd-e44a543f73bf', '5d175374-7588-3926-f912-f9ff79202aae', 'пачка сигарет', 'ru', false),
  ('97ba3c7b-6ad3-7e8e-0a41-c35b3365c061', '5d175374-7588-3926-f912-f9ff79202aae', 'табак', 'ru', false),
  ('3fc6f011-1591-b436-fa0d-0653c21fe4cf', '5d175374-7588-3926-f912-f9ff79202aae', 'sigaret', 'uz', false),
  ('c73315bb-7915-8581-3490-10eaa66319e4', '5d175374-7588-3926-f912-f9ff79202aae', 'cigarettes', 'en', false),

  ('c9f61c99-43ea-f87c-0046-77b683c289f9', '4eadae66-6ba9-659d-484c-f40a7a6ad378', 'Wi-Fi роутер', 'ru', true),
  ('d8523940-623f-cabd-db4f-e9ba88886de9', '4eadae66-6ba9-659d-484c-f40a7a6ad378', 'роутер', 'ru', false),
  ('382092ce-3fa2-f0c2-1944-55a43c78f743', '4eadae66-6ba9-659d-484c-f40a7a6ad378', 'маршрутизатор', 'ru', false),
  ('2605d261-555d-bfa7-4bf0-58b69834eb5a', '4eadae66-6ba9-659d-484c-f40a7a6ad378', 'router', 'uz', false),
  ('e1d53859-715e-0026-4664-e6a5077a8692', '4eadae66-6ba9-659d-484c-f40a7a6ad378', 'router', 'en', false),

  ('02fada2a-e03a-bb52-2224-7cf10ba131fc', 'cbdc0fb5-8164-1bb7-fc44-2c52c95bea3e', 'Смартфон', 'ru', true),
  ('0f0609ab-0d3e-bfb7-556c-cb46d8d9d5c9', 'cbdc0fb5-8164-1bb7-fc44-2c52c95bea3e', 'телефон', 'ru', false),
  ('7d19c2e8-1406-3e32-5bc4-a08a90a89cac', 'cbdc0fb5-8164-1bb7-fc44-2c52c95bea3e', 'smartfon', 'uz', false),
  ('7eabe140-000e-6832-6a33-f0eb48977370', 'cbdc0fb5-8164-1bb7-fc44-2c52c95bea3e', 'smartphone', 'en', false)
on conflict (id) do nothing;

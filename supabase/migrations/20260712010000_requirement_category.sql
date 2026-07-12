-- Тег «род требования» (UNCTAD NTM) на требовании.
-- На фронте показывается как display-only бейдж (data/taxonomy.ts → categoryOf).
-- Эта миграция ПЕРСИСТИТ его в БД для будущей фильтрации на сервере.
-- Аддитивна и обратима (колонка nullable). Применять: supabase db push.
-- Бэкофилл-эвристика по названию этапа + заголовку синхронна с фронтовой categoryOf.

create type requirement_category as enum (
  'sps', 'tbt', 'marking', 'licensing', 'fiscal', 'currency', 'customs', 'origin'
);

alter table requirements add column requirement_category requirement_category;

with cls as (
  select
    r.id,
    lower(
      coalesce(ls.name_ru, '') || ' ' ||
      coalesce(
        (select rc.title from requirement_contents rc
         where rc.requirement_id = r.id and rc.lang = 'ru' limit 1),
        ''
      )
    ) as s
  from requirements r
  left join lifecycle_stages ls on ls.id = r.lifecycle_stage_id
)
update requirements r
set requirement_category = (
  case
    when cls.s ~ 'санитар|ветеринар|фитосанитар|карантин|эпидемиолог' then 'sps'
    when cls.s ~ 'происхожд|ст-1' then 'origin'
    when cls.s ~ 'маркиров|этикет|упаковк|защита прав потребител' then 'marking'
    when cls.s ~ 'лиценз|разрешени|запрет|квот' then 'licensing'
    when cls.s ~ 'акциз|налог|пошлин|ценообраз|тариф|мрц|ставк' then 'fiscal'
    when cls.s ~ 'валют|контракт|взаиморасч|оплат|платёж|платеж|финанс' then 'currency'
    when cls.s ~ 'сертификац|технич|деклараци|соответстви|качеств|безопасн|производств|эколог|энергоэфф' then 'tbt'
    else 'customs'
  end
)::requirement_category
from cls
where cls.id = r.id;

comment on column requirements.requirement_category is
  'Род требования (UNCTAD NTM, свёрнуто в 8 категорий). Бэкофилл — эвристика по этапу; уточняется контент-редактором.';

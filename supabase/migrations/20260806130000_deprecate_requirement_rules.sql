-- Деприкация public.requirement_rules (план фотоконтроля §3, поправка 4 к ADR-0003).
--
-- Таблица пуста и непригодна для фотоконтроля: `rule` — свободный jsonb без
-- схемы, без типа проверки, без полярности, без уровня упаковки, без версии;
-- витрина её не читает. Источник правды машинных правил — YAML-пакеты
-- `config/requirements/*.yaml` в репозитории inspectorx-vision (решение
-- владельца по развилке 5, docs/PHOTOCONTROL_DECISIONS.md); шаг 'rule'
-- Build-конвейера переведён в no-op и в таблицу больше не пишет.
-- Данные не трогаем, таблицу не удаляем — только помечаем.
-- На этапе 6 плана появятся requirement_photo / requirement_photo_checks
-- (односторонняя выгрузка YAML -> БД), эта таблица к тому моменту уйдёт.

comment on table public.requirement_rules is
  'DEPRECATED 06.08.2026 (план фотоконтроля §3, поправка 4 к ADR-0003): '
  'таблица пуста, конвейер в неё больше не пишет (шаг rule — no-op). '
  'Источник правды машинных правил — YAML-пакеты inspectorx-vision; '
  'замена на этапе 6 — requirement_photo / requirement_photo_checks.';

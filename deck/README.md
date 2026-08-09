# Питч-дек InspectorX

Импорт из Claude Design (проект «InspectorX питч-дек»). 11 слайдов, 1920×1080, русский.

- `InspectorX Pitch Deck.dc.html` — сам дек, единственный файл с контентом. Слайды — inline-стилизованные `<section>` внутри `<x-import ... deck-stage>`.
- `deck-stage.js`, `image-slot.js`, `support.js` — рантайм Claude Design (сгенерированный код, не править вручную: перезапись при повторном импорте). Исключены из `oxlint` через `ignorePatterns` в `.oxlintrc.json`.

## Открыть

Нужен http — по `file://` не заработает (рантайм читает соседние файлы через `fetch`).

```bash
node .claude/deck-server.mjs
```

Дальше `http://localhost:5199/`. Навигация: ←/→, PgUp/PgDn, пробел, Home/End, цифры; `R` — в начало.

## Что не заполнено

7 слотов `<image-slot>` пустые — картинку кладут перетаскиванием в браузере (сохраняется в `.image-slots.state.json` рядом с HTML, только внутри рантайма Claude Design):

| id | слайд | что нужно |
| --- | --- | --- |
| `shot-product-card` | 03 Решение | карточка товара с чек-листом («Сигареты») |
| `shot-landing`, `shot-card`, `shot-compare` | 05 Продукт | лендинг, карточка товара, матрица сравнения стран |
| `qr-code` | 05 Продукт | QR на inspectorx.uz |
| `photo-ceo`, `photo-cto` | 10 Команда | фото основателей |

Плюс на слайде 10 два плейсхолдера `[1–2 строки бэкграунда]` — текст про опыт основателей.

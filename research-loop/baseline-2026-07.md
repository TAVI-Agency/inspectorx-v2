# Baseline research-цикла — июль 2026

> Скоринг по рубрике handoff-research-loop §4 (зафиксирована 12.07.2026).
> Сгенерировано research-loop/build_baseline.py, ночь 13.07.2026.
> citation_pass_rate — только у 4 отчётов, прошедших живой импорт 12.07;
> остальные оценены офлайн (в прод не грузились — решение ночи, см. DECISIONS).

## Метрики по отчётам

| Отчёт | kind | model | schema | N req | coverage | needs_review | unit | how_to+url | docs | санкция ₮ | все 4 поля | gate pass |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| product--cement--claude.md | product | claude | ✅ | 12 | 57% | 100% | 58% | 0% | 42% | 25% | 0% | 0/12 |
| product--electric-car--claude.md | product | claude | ✅ | 10 | 43% | 60% | 100% | 90% | 100% | 40% | 40% | 2/10 |
| product--lkm--claude.md | product | claude | ✅ | 10 | 43% | 80% | 80% | 70% | 90% | 30% | 30% | 0/10 |
| product--tyre--claude.md | product | claude | ✅ | 11 | 43% | 64% | 82% | 82% | 73% | 45% | 45% | 1/11 |
| service--ad-agency--claude.md | service | claude | ✅ | 18 | 100% | 50% | 72% | 33% | 33% | 61% | 0% | — |
| service--audit--claude.md | service | claude | ✅ | 24 | 100% | 83% | 92% | 96% | 92% | 4% | 4% | — |
| service--beauty-salon--claude.md | service | claude | ✅ | 19 | 100% | 63% | 63% | 32% | 68% | 16% | 11% | — |
| service--datacenter--claude.md | service | claude | ✅ | 20 | 100% | 75% | 50% | 90% | 90% | 30% | 25% | — |
| service--employment-agency--claude.md | service | claude | ✅ | 18 | 100% | 33% | 100% | 83% | 94% | 44% | 44% | — |
| service--hazardous-waste--claude.md | service | claude | ✅ | 17 | 100% | 65% | 100% | 94% | 76% | 47% | 24% | — |
| service--isp--claude.md | service | claude | ✅ | 16 | 100% | 75% | 75% | 88% | 100% | 69% | 56% | — |
| service--law-firm--claude.md | service | claude | ✅ | 31 | 100% | 26% | 94% | 84% | 61% | 19% | 10% | — |
| service--marketplace--claude.md | service | claude | ✅ | 18 | 100% | 56% | 100% | 39% | 44% | 6% | 6% | — |
| service--security--claude.md | service | claude | ❌ | — | — | — | — | — | — | — | — | — |

## Причины review в гейте (живой прогон 12.07)

- **product--cement--claude.md**: pass 0/12; review: needs_review_from_report=12
- **product--electric-car--claude.md**: pass 2/10; review: needs_review_from_report=6, quote_mismatch=2
- **product--lkm--claude.md**: pass 0/10; review: needs_review_from_report=8, quote_mismatch=1, act_repealed=1
- **product--tyre--claude.md**: pass 1/11; review: needs_review_from_report=7, lexuz_unreachable=2, quote_mismatch=1

## Gap-матрица: товар × секция (число требований)

| товар (model) | product | realization | import | export | transit | re_export | re_import |
|---|---|---|---|---|---|---|---|
| cement (claude) | 5 | 3 | 3 | 1 | 0 | 0 | 0 |
| electric-car (claude) | 1 | 3 | 6 | 0 | 0 | 0 | 0 |
| lkm (claude) | 3 | 4 | 3 | 0 | 0 | 0 | 0 |
| tyre (claude) | 1 | 5 | 5 | 0 | 0 | 0 | 0 |

## Gap-матрица: услуга × этап жизни бизнеса

| услуга (model) | start | premises | operations | inspections | changes | termination |
|---|---|---|---|---|---|---|
| ad-agency (claude) | 3 | 1 | 9 | 1 | 2 | 2 |
| audit (claude) | 6 | 2 | 11 | 2 | 2 | 1 |
| beauty-salon (claude) | 4 | 5 | 4 | 2 | 2 | 2 |
| datacenter (claude) | 5 | 3 | 7 | 1 | 2 | 2 |
| employment-agency (claude) | 6 | 2 | 5 | 1 | 2 | 2 |
| hazardous-waste (claude) | 5 | 3 | 6 | 1 | 1 | 1 |
| isp (claude) | 4 | 3 | 6 | 1 | 1 | 1 |
| law-firm (claude) | 7 | 4 | 12 | 3 | 3 | 2 |
| marketplace (claude) | 4 | 3 | 6 | 2 | 1 | 2 |

## cross_model_agreement (§4.6) — пары прогонов одного предмета

| предмет | пара | совпало | только A | только B | Jaccard |
|---|---|---|---|---|---|
| — | настоящих вторых прогонов нет (проверено хэшами: compass-файлы = уже импортированные отчёты) | — | — | — | n/a |

## Примечания

- Требований без ключа акт+пункт (нет lex.uz-ссылки): 24 из 224 — они не участвуют в agreement.
- Отчёты с schema_valid=0: service--security--claude.md.
- section_coverage: явных статусов секций в отчётах нет (sections_checked — бэклог промпта §5.1), поэтому coverage = доля секций рамки с ≥1 требованием.
- verified-карточек/час (§4.7): пока n/a — review-очередь не разобрана ни разу, замер невозможен; фиксируем после первого разбора очереди.

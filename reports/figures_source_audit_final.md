# FORMYLA: итог проверки рисунков каталога

Дата: 25 октября 2026 года. Ветка: `figs-audit`. Целевая ветка PR: `main`; слияние и деплой этим отчётом не разрешаются и не выполняются.

## Результат и границы проверки

- **Исходный объём**: 131 задач `fig_not_linked` и 199 задач с `fig_extracted_auto`, всего 330 разных задач в 13 каталогах.
- **Итоговый журнал**: 332 задач, включая два дополнительных исправления; у 250 задач есть проверенные рисунки, у 82 установлен подтверждённый в указанном источнике флаг отсутствия рисунка.
- **Технический аудит**: `fig_not_linked = 0`, `fig_missing = 0`, `fig_orphan = 0`.
- **Целостность**: 4036 UID исходного каталога сохранены без добавления и удаления; 979 разных действующих файлов доступны по ссылкам. Проверяются роли файлов, SHA-256 журнала, открытие растров, XML SVG и архивные контрольные суммы.
- **Визуальные материалы**: 217 проверенных PNG в 14 контактных листах `reports/figures_qa/`. Исторический набор `figures_all` сохраняется в исходных SVG.
- **Тесты**: 14 тестов и 5 вложенных проверок проходят в изолированном запуске; карточки и выдача файлов проверены через настоящий Flask blueprint без производственной БД. Полный тестовый набор всего приложения и проверка боевого деплоя не выполнялись.

Это аудит указанного набора рисунков, а не новая проверка всех условий, решений и метаданных 4036 задач. Результаты четырёх ранних поолимпиадных проходов отмечены в JSON как `earlier_pass_source_comparison`, с сохранением соответствующих коммитов; они не выдаются за новый независимый просмотр.

## Ключевые исправления

- **ММО**: восстановлены собственные рисунки 35, 85 и 86, ошибочно признанные отсутствующими; проверены годы, классы, номера и соседние чужие рисунки ([книга МЦНМО](https://mmo.mccme.ru/books/mmo-35-57.pdf)).
- **Высшая проба, 2012**: у `6f5dea4ce148` удалены оба чужих изображения; отдельно повторно проверены отрицательные флаги `a5b8ba0fcc38` и `34fa31302b5f`.
- **Математический праздник**: восстановлены график обменов, все три схемы хамелеонов и контрпример дорог; отсутствие рисунка у задачи Кощея подтверждено полными страницами 8–9 ([2025](https://olympiads.mccme.ru/matprazdnik/image/25/book.pdf), [2024](https://olympiads.mccme.ru/matprazdnik/image/24/book.pdf), [2023](https://olympiads.mccme.ru/matprazdnik/image/23/book.pdf)).
- **Турнир городов**: восстановлены собственный пространственно-временной график и обе иллюстрации доказательства о ладье; из двух решений удалены импортированные соседние задачи. В частности, рисунки задачи о коне не прикрепляются к задаче о дробных частях степеней.
- **ВсОШ**: восстановлены три вложенных квадратных корня и собственное решение `941eca2c31ba`; у задачи о 80 командах исправлен ответ на 40 команд и 165 матчей; у лодочки восстановлены исходный шаблон и оба рисунка доказательства.
- **Сириус, `4b2823ae94c3`**: в самом PDF схема перевёрнута относительно текста об удалённой нижней границе. Схема и положения чисел отражены по вертикали, сами глифы оставлены читаемыми; клетки и числа не придуманы. Ответ 11 исправлен на подтверждённые источником 10 чёрных клеток; преобразование явно записано в журнале.
- **Ломоносов**: у пяти копий задачи о часах и пяти копий задачи о скидке сохранены полные собственные доказательства, а хвосты других задач удалены.

## Архив вместо недоказанных привязок

Все 191 исходных непривязанных файлов просмотрены контактными листами и сопоставлялись с каталогом по содержанию и идентификаторам. Надёжного уникального нового соответствия не установлено; произвольных привязок нет. Три файла являются побайтовыми дублями уже используемых рисунков. Остальные 188 остаются неатрибутированными, а не объявляются неверными рисунками.

Дополнительно сохранены 215 прежних версий заменённых/исключённых файлов. Всего 406 записей и 379 уникальных объектов в `archive/olymp_figures_review/`. Исходные байты и пути сохранены; публичный каталог очищен, безвозвратного удаления из репозитория нет.

## Защита от повторения

- **GIF**: файлы учитываются аудитом, включая регистр расширения; есть отдельный тест.
- **Алгебраические графики**: голое упоминание графика функции больше не означает пропущенную иллюстрацию. Явные ссылки на рисунок и график справа/слева продолжают обнаруживаться.
- **Автоматизация**: audit workflow читает каталог и коммитит только свой отчёт. Extractor запускается вручную и отдаёт непроверенные предложения артефактом; больше не пушит каталог или изображения и не выполняет rebase с `-X theirs`.
- **Архивирование**: повторный запуск не теряет старый манифест и не считает удалённый из static исходный orphan второй «заменённой версией».

## Ограничения первоисточников

Для `phystech/4bccccb080d3` доступный исходник содержит условие и ответ, но не полное официальное решение; для `vsosh/43c3632cb850` исходник — листок условий без опубликованных решений. Эти два случая помечены в JSON соответственно `statement_and_answer_source_only` и `statement_worksheet_only`. Флаг означает отсутствие рисунка в проверенном доступном источнике, а не заявление о просмотре не найденного официального доказательства.

Ссылки «карточка» ниже ведут на рабочий адрес FORMYLA и требуют входа. Они сохраняют UID, но показывают новую версию только после отдельного разрешённого слияния PR и деплоя. До этого изменения проверяются в ветке и контактных листах.

## Сводка по олимпиадам

| Олимпиада | Исходные пропуски | Исходные auto | Журнал | С рисунками | Без рисунка |
|---|---:|---:|---:|---:|---:|
| ВсОШ | 51 | 75 | 126 | 103 | 23 |
| ММО | 13 | 11 | 26 | 18 | 8 |
| Курчатов | 3 | 15 | 18 | 17 | 1 |
| Турнир городов | 30 | 20 | 50 | 36 | 14 |
| Ломоносов | 2 | 16 | 18 | 7 | 11 |
| Формула Единства | 5 | 28 | 33 | 27 | 6 |
| Покори Воробьёвы горы! | 2 | 3 | 5 | 4 | 1 |
| Эйлер | 2 | 7 | 9 | 4 | 5 |
| Высшая проба | 11 | 3 | 14 | 7 | 7 |
| Математический праздник | 7 | 20 | 27 | 26 | 1 |
| СПбГУ | 1 | 1 | 2 | 1 | 1 |
| Физтех | 3 | 0 | 3 | 0 | 3 |
| Прочие источники | 1 | 0 | 1 | 0 | 1 |

## Поимённые результаты

UID сокращён до 12 символов для читаемости; полные UID, роли, пути файлов и SHA-256 находятся в `reports/figures_verified_<slug>.json`. «Пропуск» и «auto» обозначают исходную группу, а не итоговую ошибку.

### ВсОШ

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `e5dc9922e448` | 2025 | 9 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/e5dc9922e448) | [оригинал](https://всош.цпм.рф/upload/files/Arhive_tasks/2024-25/final/math/sol-math-9-final-24-25.pdf#page=4) |
| `03255e396c64` | 2025 | 9 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/03255e396c64) | [оригинал](https://всош.цпм.рф/upload/files/Arhive_tasks/2024-25/final/math/sol-math-9-final-24-25.pdf#page=6) |
| `09672640b70b` | 2025 | 9 | 8 | пропуск | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/09672640b70b) | [оригинал](https://всош.цпм.рф/upload/files/Arhive_tasks/2024-25/final/math/sol-math-9-final-24-25.pdf#page=10) |
| `8d16feec085e` | 2025 | 11 | 8 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/8d16feec085e) | [оригинал](https://всош.цпм.рф/upload/files/Arhive_tasks/2024-25/final/math/sol-math-11-final-24-25.pdf) |
| `9235f40ce394` | 2026 | 11 | 9 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/9235f40ce394) | [оригинал](https://olympiads.mccme.ru/vmo/2026/iii-2.pdf) |
| `4b2823ae94c3` | 2025 | 9 | 2 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/4b2823ae94c3) | [оригинал](https://global.s3.cloud.ru/olmath-files/vsosh/school-math/sirius/2025-26/gruppa-2/razbor-9-klass.pdf) |
| `b70b69d44dec` | 2025 | 9 | 8 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/b70b69d44dec) | [оригинал](https://global.s3.cloud.ru/olmath-files/vsosh/school-math/sirius/2025-26/gruppa-2/razbor-9-klass.pdf) |
| `72dd233c990c` | 2025 | 11 | 6 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/72dd233c990c) | [оригинал](https://global.s3.cloud.ru/olmath-files/vsosh/school-math/sirius/2025-26/gruppa-2/razbor-11-klass.pdf) |
| `7b1a38786d4f` | 2024 | 10 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/7b1a38786d4f) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2023-24/final/math/sol-math-10-day1-final-23-24.pdf#page=3) |
| `2e69ba18f0f5` | 2024 | 10 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/2e69ba18f0f5) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2023-24/final/math/sol-math-10-day1-final-23-24.pdf#page=6) |
| `7e9b553c5f2a` | 2024 | 11 | 1 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/7e9b553c5f2a) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/72/2023/sol-math-11-reg-23-24.pdf) |
| `f4b7a9344a50` | 2023 | 10 | 1 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/f4b7a9344a50) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2022-23/final/math/sol-math-10-day1-final-22-23.pdf#page=2) |
| `7d881371c50d` | 2023 | 10 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/7d881371c50d) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2022-23/final/math/sol-math-10-day1-final-22-23.pdf#page=5) |
| `bab49b74c156` | 2023 | 11 | 6 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/bab49b74c156) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2022-23/final/math/sol-math-11-day2-final-22-23.pdf#page=3) |
| `290fa471afe1` | 2023 | 10 | 1 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/290fa471afe1) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2022-23/reg/math/sol-math-10-tur1-reg-22-23.pdf#page=3) |
| `d0a4445e5417` | 2023 | 11 | 8 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/d0a4445e5417) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2022-23/reg/math/sol-math-11-tur2-reg-22-23.pdf#page=5) |
| `0b5af52cfa5a` | 2022 | 9 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/0b5af52cfa5a) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2021-22/final/math/sol-math-9-tur1-final-21-22.pdf#page=2) |
| `01a975dd3f39` | 2022 | 10 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/01a975dd3f39) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2021-22/final/math/sol-math-10-tur1-final-21-22.pdf#page=2) |
| `afbd00ec3376` | 2022 | 10 | 7 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/afbd00ec3376) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2021-22/final/math/sol-math-10-tur2-final-21-22.pdf#page=3) |
| `94d63fdb2527` | 2022 | 11 | 8 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/94d63fdb2527) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2021-22/final/math/sol-math-11-tur2-final-21-22.pdf#page=4) |
| `1e098b256379` | 2022 | 11 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/1e098b256379) | [оригинал](https://olympiads.mccme.ru/vmo/2023/ii-11.pdf) |
| `c9028582351e` | 2022 | 9 | 8 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/c9028582351e) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2021-22/reg/math/sol-math-9-day2-reg-21-22.pdf#page=8) |
| `09de5e9fd70a` | 2022 | 9 | 7 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/09de5e9fd70a) | [оригинал](https://всош.цпм.рф/upload/files/Arhive_tasks/2022-23/school/math/taskssol-math-4-11-msk-sch-22-23.pdf) |
| `0be99b44022f` | 2022 | 9 | 8 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/0be99b44022f) | [оригинал](https://всош.цпм.рф/upload/files/Arhive_tasks/2022-23/school/math/taskssol-math-4-11-msk-sch-22-23.pdf#page=34) |
| `b1e70dd1675e` | 2022 | 10 | 6 | пропуск | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/b1e70dd1675e) | [оригинал](https://всош.цпм.рф/upload/files/Arhive_tasks/2022-23/school/math/taskssol-math-4-11-msk-sch-22-23.pdf#page=38) |
| `753f00497bd6` | 2021 | 10 | 1 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/753f00497bd6) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/final/math/sol-math-10-day1-final-20-21.pdf#page=3) |
| `94f1564c67cd` | 2021 | 11 | 2 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/94f1564c67cd) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/final/math/sol-math-11-day1-final-20-21.pdf) |
| `801217d8dcc5` | 2021 | 10 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/801217d8dcc5) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/final/math/sol-math-10-day2-final-20-21.pdf) |
| `23164b57081d` | 2021 | 11 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/23164b57081d) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/final/math/sol-math-11-day2-final-20-21.pdf) |
| `4da12ec9c124` | 2021 | 11 | 8 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/4da12ec9c124) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/final/math/sol-math-11-day2-final-20-21.pdf) |
| `af29f4698911` | 2021 | 10 | 1 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/af29f4698911) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/mun/math/sol-math-9-11-mun-msk-20-21.pdf#page=9) |
| `e02e57870c8c` | 2020 | 11 | 2 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/e02e57870c8c) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/final/math/sol-math-11-day1-final-20-21.pdf) |
| `01ea6b114904` | 2020 | 9 | 1 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/01ea6b114904) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/mun/math/ans-math-9-mun-msk-19-20.pdf) |
| `01fc6ddb61bb` | 2020 | 9 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/01fc6ddb61bb) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/mun/math/ans-math-9-mun-msk-19-20.pdf#page=2) |
| `bf3d487ae028` | 2020 | 10 | 2 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/bf3d487ae028) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/mun/math/ans-math-10-mun-msk-19-20.pdf) |
| `a1e578e2ddeb` | 2020 | 10 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/a1e578e2ddeb) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/mun/math/ans-math-10-mun-msk-19-20.pdf#page=2) |
| `b75f714c68d5` | 2020 | 11 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/b75f714c68d5) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/mun/math/ans-math-11-mun-msk-19-20.pdf#page=1) |
| `299991d00cda` | 2020 | 11 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/299991d00cda) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/mun/math/ans-math-11-mun-msk-19-20.pdf#page=2) |
| `e0212b3ad9b3` | 2020 | 11 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/e0212b3ad9b3) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/mun/math/ans-math-11-mun-msk-19-20.pdf#page=3) |
| `63c43bace68d` | 2020 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/63c43bace68d) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/reg/math/sol-math-9-day1-reg-20-21.pdf#page=10) |
| `39a5ef515d6f` | 2020 | 11 | 9 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/39a5ef515d6f) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2019-20/region/math/ans-math-11-day2-reg-19-20.pdf) |
| `6bed2116035d` | 2020 | 9 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/6bed2116035d) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/school/math/ans-math-4-11-sch-msk-20-21.pdf) |
| `d164b4e003bb` | 2020 | 10 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/d164b4e003bb) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2020-21/school/math/ans-math-4-11-sch-msk-20-21.pdf) |
| `955922a87d75` | 2020 | 10 | 6 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/vsosh/955922a87d75) | [оригинал](https://mathus.ru/olymp/VserosMath2021S10.pdf) |
| `36c6cb542962` | 2019 | 10 | 1 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/36c6cb542962) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/final/math/72-ans-math-10-final-18-9.pdf#page=1) |
| `4394cd2cdc87` | 2019 | 10 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/4394cd2cdc87) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/final/math/72-ans-math-10-final-18-9.pdf#page=4) |
| `cab1c1aa4411` | 2019 | 11 | 1 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/cab1c1aa4411) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/final/math/72-ans-math-10-final-18-9.pdf#page=1) |
| `d62c666f1d84` | 2019 | 11 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/d62c666f1d84) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/final/math/72-ans-math-11-final-18-9.pdf#page=5) |
| `801b953596f9` | 2019 | 11 | 6 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/801b953596f9) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/final/math/72-ans-math-11-final-18-9.pdf#page=9) |
| `e3f7f4ae711f` | 2019 | 9 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/e3f7f4ae711f) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/mun/math/ans-math-9-mun-18-9.pdf) |
| `c15df00f209b` | 2019 | 9 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/c15df00f209b) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/mun/math/ans-math-9-mun-18-9.pdf) |
| `47214a301395` | 2019 | 10 | 1 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/47214a301395) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/mun/math/ans-math-10-mun-18-9.pdf) |
| `d7f832190596` | 2019 | 10 | 4 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/d7f832190596) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/mun/math/ans-math-10-mun-18-9.pdf#page=2) |
| `b1ef22440e21` | 2019 | 11 | 6 | auto | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/b1ef22440e21) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/mun/math/ans-math-11-mun-18-9.pdf) |
| `24d9b66e0977` | 2019 | 9 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/24d9b66e0977) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/region/math/ans-math-9-day1-reg-18-9.pdf#page=7) |
| `2ee1a93f140f` | 2019 | 11 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/2ee1a93f140f) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/region/math/ans-math-11-day1-reg-18-9.pdf#page=6) |
| `9a6aa764e620` | 2019 | 11 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/9a6aa764e620) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/region/math/ans-math-11-day1-reg-18-9.pdf#page=8) |
| `80e556d80f7d` | 2019 | 9 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/80e556d80f7d) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/region/math/ans-math-9-day1-reg-18-9.pdf#page=8) |
| `d291502cce1c` | 2019 | 9 | 8 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/d291502cce1c) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/region/math/ans-math-9-day2-reg-18-9.pdf#page=5) |
| `700b9fed8bd3` | 2019 | 10 | 8 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/700b9fed8bd3) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2018-19/region/math/ans-math-10-day2-reg-18-9.pdf#page=5) |
| `1c8d59942348` | 2018 | 9 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/1c8d59942348) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/final/math/72-ans-math-9-final-17-8.pdf) |
| `d33632f29296` | 2018 | 11 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/d33632f29296) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/final/math/72-ans-math-11-final-17-8.pdf) |
| `21ed18762bdc` | 2018 | 9 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/21ed18762bdc) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/mun/math/ans-math-9-mun-msk-17-8.pdf#page=1) |
| `e4ad37ca1baa` | 2018 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/e4ad37ca1baa) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/mun/math/ans-math-9-mun-msk-17-8.pdf) |
| `6ace8ba15500` | 2018 | 10 | 3 | пропуск | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/6ace8ba15500) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/mun/math/ans-math-10-mun-msk-17-8.pdf#page=2) |
| `b798a5824122` | 2018 | 10 | 5 | auto | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/b798a5824122) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/mun/math/ans-math-10-mun-msk-17-8.pdf) |
| `c08490dc8ac6` | 2018 | 11 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/c08490dc8ac6) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/mun/math/ans-math-11-mun-msk-17-8.pdf) |
| `2b02ef44e78b` | 2018 | 11 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/2b02ef44e78b) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/mun/math/ans-math-11-mun-msk-17-8.pdf) |
| `48a37f01489d` | 2018 | 9 | 9 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/48a37f01489d) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/region/math/ans-math-9-day2-reg-17-8.pdf#page=6) |
| `904f84ede872` | 2018 | 11 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/904f84ede872) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/region/math/ans-math-11-day1-reg-17-8.pdf) |
| `54158c66b505` | 2018 | 11 | 4 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/54158c66b505) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2017-18/region/math/ans-math-11-day1-reg-17-8.pdf#p5) |
| `2294f3dc8004` | 2017 | 9 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/2294f3dc8004) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/final/math/ans-math-9-tur1-final-16-7.pdf) |
| `91e5dfe12e58` | 2017 | 11 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/91e5dfe12e58) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/final/math/ans-math-11-tur1-final-16-7.pdf) |
| `b0361b4bf6ef` | 2017 | 10 | 7 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/b0361b4bf6ef) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/final/math/ans-math-10-tur2-final-16-7.pdf) |
| `307f890a2fe1` | 2017 | 10 | 1 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/307f890a2fe1) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/mun/math/ans-math-10-msk-mun-16-7.pdf) |
| `6ace6f30d915` | 2017 | 10 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/6ace6f30d915) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/mun/math/ans-math-10-msk-mun-16-7.pdf) |
| `cc056b72e0e7` | 2017 | 10 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/cc056b72e0e7) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/mun/math/ans-math-10-msk-mun-16-7.pdf) |
| `97e791d08051` | 2017 | 11 | 2 | auto | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/97e791d08051) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/mun/math/ans-math-11-msk-mun-16-7.pdf) |
| `dc5e5f94075a` | 2017 | 11 | 3 | auto | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/dc5e5f94075a) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/mun/math/ans-math-11-msk-mun-16-7.pdf) |
| `c680b5d8115e` | 2017 | 11 | 4 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/c680b5d8115e) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/mun/math/ans-math-11-msk-mun-16-7.pdf) |
| `0bd382b207ae` | 2017 | 9 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/0bd382b207ae) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/region/math/ans-math-9-day1-reg-16-7.pdf) |
| `5743d6069aa9` | 2017 | 11 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/5743d6069aa9) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/region/math/ans-math-11-day1-reg-16-7.pdf) |
| `dcfb05e7cc2c` | 2017 | 11 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/dcfb05e7cc2c) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/region/math/ans-math-11-day1-reg-16-7.pdf) |
| `95cce8e0cc41` | 2017 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/95cce8e0cc41) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/region/math/ans-math-9-day2-reg-16-7.pdf) |
| `82c5bf310691` | 2017 | 11 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/82c5bf310691) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/region/math/ans-math-11-day2-reg-16-7.pdf) |
| `217e2bd1b664` | 2017 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/217e2bd1b664) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/72/2024/sol-math-9-mun-orenb-24-25.pdf) |
| `4d38650de2f1` | 2016 | 9 | 4 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/4d38650de2f1) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/final/math/ans-math-9-day1-final-15-6.pdf) |
| `63e49114c25c` | 2016 | 9 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/63e49114c25c) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/final/math/ans-math-9-day2-final-15-6.pdf) |
| `df04d7691b13` | 2016 | 10 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/df04d7691b13) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/final/math/ans-math-10-day2-final-15-6.pdf) |
| `c90e0987b901` | 2016 | 11 | 8 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/c90e0987b901) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/final/math/ans-math-11-day2-final-15-6.pdf) |
| `f97f9b4a5c30` | 2016 | 9 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/f97f9b4a5c30) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/mun/math/ans-math-9-msk-mun-15-6.pdf) |
| `505c024b6881` | 2016 | 9 | 5 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/505c024b6881) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/mun/math/ans-math-9-msk-mun-15-6.pdf) |
| `4234fda68025` | 2016 | 10 | 1 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/4234fda68025) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/mun/math/ans-math-10-msk-mun-15-6.pdf) |
| `941eca2c31ba` | 2016 | 11 | 1 | auto | Без рисунка в источнике; восстановлены формула и решение | [карточка](https://formyla.net/olymp-catalog/vsosh/941eca2c31ba) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/mun/math/ans-math-11-msk-mun-15-6.pdf#p1) |
| `d9b4ff1c4b81` | 2016 | 11 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/d9b4ff1c4b81) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/region/math/ans-math-11-day1-reg-15-6.pdf) |
| `349e7ceff284` | 2016 | 10 | 7 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/349e7ceff284) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/region/math/ans-math-10-day2-reg-15-6.pdf) |
| `758d98df7cda` | 2015 | 11 | 1 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/758d98df7cda) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/final_tasks/math/ans-math-11-1day-final-14-5.pdf) |
| `1421cc6a58bd` | 2015 | 9 | 7 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/1421cc6a58bd) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/final_tasks/math/ans-math-9-2day-final-14-5.pdf#page=3) |
| `9685be8db87b` | 2015 | 10 | 7 | пропуск | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/vsosh/9685be8db87b) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/final_tasks/math/ans-math-10-2day-final-14-5.pdf#page=2) |
| `8df9f20cf63b` | 2015 | 11 | 7 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/8df9f20cf63b) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/final_tasks/math/ans-math-11-2day-final-14-5.pdf) |
| `5f607701f74e` | 2015 | 10 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/5f607701f74e) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/okrug_tasks/math/ans-math-10-okr-msk-14-5.pdf) |
| `8321d5b3e3e6` | 2015 | 11 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/8321d5b3e3e6) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/okrug_tasks/math/ans-math-11-okr-msk-14-5.pdf) |
| `ea68a1fe6ee1` | 2015 | 10 | 7 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/ea68a1fe6ee1) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/region/math/ans-math-10-day2-reg-15-6.pdf) |
| `6f7333d3523b` | 2015 | 9 | 8 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/6f7333d3523b) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/region/math/ans-math-9-day2-reg-15-6.pdf) |
| `03d0d1291ac4` | 2015 | 11 | 7 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/03d0d1291ac4) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2015-16/region/math/ans-math-11-day2-reg-15-6.pdf) |
| `f3a9178a3575` | 2015 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/f3a9178a3575) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/school_tasks/math/ans-math-9-sch-msk-14-5.pdf) |
| `de535b2431c6` | 2015 | 10 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/de535b2431c6) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/school_tasks/math/ans-math-10-sch-msk-14-5.pdf#page=1) |
| `6a87b980c4c0` | 2015 | 10 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/6a87b980c4c0) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/school_tasks/math/ans-math-10-sch-msk-14-5.pdf) |
| `cbf3b20ca906` | 2015 | 11 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/cbf3b20ca906) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/okrug_tasks/math/ans-math-11-okr-msk-14-5.pdf#page=1) |
| `3bc7df0e983a` | 2015 | 11 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/3bc7df0e983a) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/okrug_tasks/math/ans-math-11-okr-msk-14-5.pdf#page=1) |
| `ef9e0dca6a0f` | 2014 | 9 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/ef9e0dca6a0f) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/okrug_tasks/math/ans-math-9-okr-msk-14-5.pdf) |
| `b77db5f365b3` | 2014 | 11 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/b77db5f365b3) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/okrug_tasks/math/ans-math-11-okr-msk-14-5.pdf#page=1) |
| `e52bb0ae57bf` | 2014 | 9 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/e52bb0ae57bf) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/school_tasks/math/ans-math-9-sch-msk-14-5.pdf) |
| `0d2640f3e170` | 2014 | 10 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/0d2640f3e170) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/school_tasks/math/ans-math-10-sch-msk-14-5.pdf#page=1) |
| `21142601e060` | 2014 | 10 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/21142601e060) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2014-15/school_tasks/math/ans-math-10-sch-msk-14-5.pdf#page=2) |
| `8587db0f1452` | 2013 | 9 | 4 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/8587db0f1452) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2013-14/okrug_tasks/math/ans-math-9-okr-msk-2013-4.pdf) |
| `63cb63a33d8d` | 2013 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/63cb63a33d8d) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2013-14/okrug_tasks/math/ans-math-9-okr-msk-2013-4.pdf) |
| `b4295df1b431` | 2013 | 10 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/b4295df1b431) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2013-14/okrug_tasks/math/ans-math-10-okr-msk-2013-4.pdf) |
| `86edcad1548a` | 2012 | 10 | 7 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/86edcad1548a) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/72/2024/sol-math-11-mun-komi-24-25.pdf) |
| `5677bd255d93` | 2012 | 10 | 7 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/5677bd255d93) | [оригинал](https://olympiads.mccme.ru/vmo/2012/iii-2.pdf) |
| `599b6ca12cb1` | 2012 | 11 | 7 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/599b6ca12cb1) | [оригинал](https://olympiads.mccme.ru/vmo/2012/iii-2.pdf) |
| `ed87499579ff` | 2011 | 11 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/ed87499579ff) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2010-2011/region_tasks/new-cut/math/ans-math-11-day2-reg-2010-1.pdf) |
| `745b45e3b335` | 2010 | 10 | 3 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/745b45e3b335) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2016-17/mun/math/ans-math-10-msk-mun-16-7.pdf#page=1) |
| `43c3632cb850` | 2010 | 10 | 4 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vsosh/43c3632cb850) | [оригинал](https://fizmat.space/maths/files/9-gavrikova/9_6_%D0%A0%D0%B0%D1%81%D0%BA%D1%80%D0%B0%D1%81%D0%BA%D0%B8.pdf) |
| `f468da430855` | 2010 | 9 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/f468da430855) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2009-2010/region_tasks/new-cut/math/ans-math-9-day1-reg-2009-10.pdf) |
| `25178ec4ec9f` | 2010 | 11 | 6 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vsosh/25178ec4ec9f) | [оригинал](https://vos.olimpiada.ru/upload/files/Arhive_tasks/2009-2010/region_tasks/new-cut/math/ans-math-11-day2-reg-2009-10.pdf) |

### ММО

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `a4b44f34936a` | 2025 | 11 | 4 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/a4b44f34936a) | [оригинал](https://www.problems.ru/view_problem_details_new.php?id=67463) |
| `528ae1153051` | 2024 | 8 | 1 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/528ae1153051) | [оригинал](https://www.problems.ru/view_problem_details_new.php?id=67300) |
| `fab83cb2b7eb` | 2024 | 11 | 1 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/fab83cb2b7eb) | [оригинал](https://mmo.mccme.ru/2024/11-sol2.pdf) |
| `53d5ea485ff4` | 2024 | 11 | 5 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/53d5ea485ff4) | [оригинал](https://mmo.mccme.ru/2024/11-sol2.pdf) |
| `0e3922eab151` | 2021 | 8 | 5 | auto | Проверены: условие 3, решение 0 | [карточка](https://formyla.net/olymp-catalog/mmo/0e3922eab151) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66583) |
| `7a23b4c5067f` | 2021 | 8 | 2 | auto | Проверены: условие 2, решение 0 | [карточка](https://formyla.net/olymp-catalog/mmo/7a23b4c5067f) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66580) |
| `d7a898b00030` | 2021 | 9 | 4 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/d7a898b00030) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66588) |
| `1dd6382b1ad4` | 2021 | 9 | 2 | auto | Проверены: условие 3, решение 0 | [карточка](https://formyla.net/olymp-catalog/mmo/1dd6382b1ad4) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66586) |
| `7886ad56d374` | 2021 | 9 | 3 | auto | Проверены: условие 2, решение 0 | [карточка](https://formyla.net/olymp-catalog/mmo/7886ad56d374) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66587) |
| `cd30a419389f` | 2021 | 11 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/cd30a419389f) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66602) |
| `5e3f96a873a6` | 2021 | 11 | 3 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/5e3f96a873a6) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66588) |
| `f3e9ba8f58bc` | 2021 | 11 | 4 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/f3e9ba8f58bc) | [оригинал](https://www.problems.ru/view_problem_details_new.php?id=66596) |
| `bd23bc3dff44` | 2015 | 8 | 1 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/bd23bc3dff44) | [оригинал](https://problems.ru/view_problem_details_new.php?id=65186) |
| `2a0f07ee9013` | 2013 | 9 | 1 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/2a0f07ee9013) | [оригинал](https://problems.ru/view_problem_details_new.php?id=32891) |
| `4aaf063c6f43` | 2009 | 9 | 1 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/4aaf063c6f43) | [оригинал](https://www.problems.ru/view_problem_details_new.php?id=111911) |
| `1febe148dca6` | 2003 | 8 | 3 | пропуск | Проверены: условие 0, решение 6 | [карточка](https://formyla.net/olymp-catalog/mmo/1febe148dca6) | [оригинал](https://problems.ru/view_problem_details_new.php?id=105146) |
| `bd6753da41f7` | 2003 | 10 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/bd6753da41f7) | [оригинал](https://problems.ru/view_problem_details_new.php?id=105160) |
| `5dfea28ed89b` | 1993 | 8 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/mmo/5dfea28ed89b) | [оригинал](https://mmo.mccme.ru/books/mmo-93-05.pdf) |
| `02f4f435e4c4` | 1993 | 8 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/02f4f435e4c4) | [оригинал](https://problems.ru/view_problem_details_new.php?id=105097) |
| `0f5a31d72e49` | 1993 | 8 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/mmo/0f5a31d72e49) | [оригинал](https://problems.ru/view_problem_details_new.php?id=105074) |
| `51f2f2892c84` | 1940 | 8 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/51f2f2892c84) | [оригинал](https://mmo.mccme.ru/books/mmo-35-57.pdf#page=163) |
| `e0d014681ab8` | 1954 | 8 | 5 | дополнительно | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/e0d014681ab8) | [оригинал](https://mmo.mccme.ru/books/mmo-35-57.pdf#page=271) |
| `40a954636298` | 1954 | 10 | 1 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/40a954636298) | [оригинал](https://mmo.mccme.ru/books/mmo-35-57.pdf#page=274) |
| `e1fa55a6bb8e` | 1940 | 10 | 1 | auto | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/mmo/e1fa55a6bb8e) | [оригинал](https://mmo.mccme.ru/books/mmo-35-57.pdf#page=164) |
| `e40574eb3cc5` | 1949 | 7 | 4 | дополнительно | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/mmo/e40574eb3cc5) | [оригинал](https://mmo.mccme.ru/books/mmo-35-57.pdf#page=208) |
| `cfd87cdf3f99` | 1955 | 8 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/mmo/cfd87cdf3f99) | [оригинал](https://mmo.mccme.ru/books/mmo-35-57.pdf#page=276) |

### Курчатов

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `8c0395d7edbd` | 2025 | 6 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/8c0395d7edbd) | [оригинал](https://old.olimpiadakurchatov.ru/upload/files/2025/final_tasks/Kurchatov_Math_2025.pdf) |
| `5056e0c907ab` | 2025 | 7 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/5056e0c907ab) | [оригинал](https://old.olimpiadakurchatov.ru/upload/files/2025/final_tasks/Kurchatov_Math_2025.pdf) |
| `8722e7a2298e` | 2024 | 6 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/kurchatov/8722e7a2298e) | [оригинал](https://mathus.ru/olymp/Kurchatov2024Math6.pdf) |
| `923b7622fabe` | 2024 | 7 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/kurchatov/923b7622fabe) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/389/2023/389-sol-math-7-final-23-24.pdf) |
| `35c0c50e92a5` | 2024 | 7 | 1 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/35c0c50e92a5) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/389/2023/389-taskssol-math-6-7-otbor-23-24.pdf) |
| `6a2a94fe7c19` | 2024 | 8 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/6a2a94fe7c19) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/389/2023/389-taskssol-math-8-9-otbor-23-24.pdf) |
| `03379bb366c7` | 2024 | 10 | 4 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/03379bb366c7) | [оригинал](https://old.olimpiadakurchatov.ru/upload/files/kurch_olimp_online_2024_modif.pdf) |
| `0718d763d44a` | 2023 | 7 | 4 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/0718d763d44a) | [оригинал](https://old.olimpiadakurchatov.ru/upload/files/Kurchatov_Math_2023.pdf) |
| `07d05ca3040f` | 2020 | 8 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/07d05ca3040f) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/389/2019/389-ans-math-8-final-19-0.pdf#p5) |
| `0ec9930c918b` | 2019 | 6 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/0ec9930c918b) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/389/2018/389-ans-math-6-final-18-9.pdf) |
| `8ff11ab6a12f` | 2019 | 7 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/8ff11ab6a12f) | [оригинал](https://old.olimpiadakurchatov.ru/2019/final/kurchatov-2019-final-math-7-sol.pdf) |
| `5f7b65f9849b` | 2019 | 7 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/5f7b65f9849b) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/389/2018/389-ans-math-7-final-18-9.pdf) |
| `2bb0b5445b21` | 2018 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/2bb0b5445b21) | [оригинал](https://old.olimpiadakurchatov.ru/2018/final/kurchatov-2018-math-9-sol.pdf) |
| `28cb158ded5d` | 2017 | 6 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/28cb158ded5d) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/389/2016/7122068-ans-math-6-final-16-7.pdf) |
| `d1e808245adb` | 2017 | 7 | 5 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/d1e808245adb) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/389/2016/7122068-ans-math-7-final-16-7.pdf) |
| `421e4c0777fc` | 2017 | 7 | 5 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/421e4c0777fc) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/389/2016/7122068-ans-math-7-final-16-7.pdf) |
| `5a15f1ff9a80` | 2014 | 10 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/kurchatov/5a15f1ff9a80) | [оригинал](https://old.olimpiadakurchatov.ru/2014/math-final.pdf) |
| `62ca1424930b` | 2014 | 10 | 4 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/kurchatov/62ca1424930b) | [оригинал](https://old.olimpiadakurchatov.ru/2014/math-final.pdf) |

### Турнир городов

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `b0ed5d15ca1c` | 2025 | 11 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/turgor/b0ed5d15ca1c) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/5/2024/5-sol-math-10-11-sl_ves-24-25.pdf#p1) |
| `6c4122d59d99` | 2025 | 11 | 3 | пропуск | Проверены: условие 1, решение 4 | [карточка](https://formyla.net/olymp-catalog/turgor/6c4122d59d99) | [оригинал](https://turgor.ru/problems/46/vs-46-sol-all.pdf#page=12) |
| `aaa74fc4b723` | 2025 | 10 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/aaa74fc4b723) | [оригинал](https://turgor.ru/problems/47/os-47-baz-sol.pdf#page=6) |
| `e95b8d115ed6` | 2025 | 11 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/e95b8d115ed6) | [оригинал](https://turgor.ru/problems/47/os-47-baz-sol.pdf#page=6) |
| `27fc7bd6014e` | 2024 | 8 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/27fc7bd6014e) | [оригинал](https://turgor.ru/problems/46/vs-46-sol-all.pdf#page=2) |
| `5644b3d5fe33` | 2024 | 9 | 3 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/turgor/5644b3d5fe33) | [оригинал](https://turgor.ru/problems/45/vs-45-baz-avt.pdf#page=1) |
| `934de4f006b5` | 2024 | 8 | 4 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/934de4f006b5) | [оригинал](https://turgor.ru/problems/46/vs-46-sol-all.pdf#page=13) |
| `2bfc90cd2f5e` | 2024 | 8 | 7 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/2bfc90cd2f5e) | [оригинал](https://turgor.ru/problems/46/vs-46-sol-all.pdf#page=18) |
| `1c6385806b5e` | 2024 | 8 | 5 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/turgor/1c6385806b5e) | [оригинал](https://turgor.ru/problems/45/vs-45-sol-fin.pdf#page=7) |
| `74208be6a62e` | 2024 | 9 | 4 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/74208be6a62e) | [оригинал](https://turgor.ru/problems/46/vs-46-sol-all.pdf#page=13) |
| `4ebb513d160c` | 2024 | 8 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/4ebb513d160c) | [оригинал](https://turgor.ru/problems/46/os-46-baz-sol.pdf#page=2) |
| `1a8c062aa141` | 2024 | 9 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/1a8c062aa141) | [оригинал](https://turgor.ru/problems/46/os-46-sl-sol.pdf#page=1) |
| `758d25cabcd0` | 2023 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/758d25cabcd0) | [оригинал](https://turgor.ru/problems/44/vs-44-baz-sol.pdf#p5) |
| `970b557d5a38` | 2023 | 9 | 2 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/970b557d5a38) | [оригинал](https://turgor.ru/problems/44/vs-44-sl-sol.pdf#page=1) |
| `75f03859826a` | 2023 | 9 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/turgor/75f03859826a) | [оригинал](https://turgor.ru/problems/44/vs-44-sl-sol.pdf#p4) |
| `1e31acf870a3` | 2023 | 11 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/1e31acf870a3) | [оригинал](https://turgor.ru/problems/44/vs-44-sl-sol.pdf#p7) |
| `96d34af452e8` | 2023 | 8 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/96d34af452e8) | [оригинал](https://turgor.ru/problems/45/os-45-baz-sol.pdf#page=2) |
| `79425f2aa0bc` | 2023 | 9 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/79425f2aa0bc) | [оригинал](https://turgor.ru/problems/45/os-45-baz-sol.pdf#page=2) |
| `e5b66ff4f860` | 2023 | 10 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/e5b66ff4f860) | [оригинал](https://turgor.ru/problems/45/os-45-baz-sol.pdf#page=6) |
| `5100a403c470` | 2023 | 11 | 5 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/5100a403c470) | [оригинал](https://turgor.ru/problems/45/os-45-baz-sol.pdf#page=6) |
| `5e4e2a672bfd` | 2023 | 8 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/5e4e2a672bfd) | [оригинал](https://turgor.ru/problems/45/os-45-sl-sol.pdf#page=2) |
| `5c80575acd45` | 2023 | 9 | 1 | пропуск | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/turgor/5c80575acd45) | [оригинал](https://turgor.ru/problems/45/os-45-sl-sol.pdf#page=1) |
| `d6b096d75273` | 2022 | 9 | 1 | auto | Проверены: условие 0, решение 1; исправлен ложный флаг | [карточка](https://formyla.net/olymp-catalog/turgor/d6b096d75273) | [оригинал](https://turgor.ru/problems/43/vs-43-sol-fin.pdf#p1) |
| `8c85067b8de2` | 2022 | 9 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/8c85067b8de2) | [оригинал](https://turgor.ru/problems/43/vs-43-sol-fin.pdf#p2) |
| `d3df353d6de8` | 2022 | 9 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/d3df353d6de8) | [оригинал](https://turgor.ru/problems/43/vs-43-sol-fin.pdf#page=6) |
| `f9800a1b8da2` | 2022 | 10 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/f9800a1b8da2) | [оригинал](https://turgor.ru/problems/44/vs-44-sl-sol.pdf#page=6) |
| `ff4147f2f5c5` | 2022 | 10 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/ff4147f2f5c5) | [оригинал](https://turgor.ru/problems/43/vs-43-sol-fin.pdf#page=10) |
| `9af8c1c0fd1d` | 2022 | 11 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/9af8c1c0fd1d) | [оригинал](https://turgor.ru/problems/43/vs-43-sol-fin.pdf#page=10) |
| `f5e2ec30655c` | 2022 | 9 | 4 | auto | Проверены: условие 0, решение 2; исправлен ложный флаг | [карточка](https://formyla.net/olymp-catalog/turgor/f5e2ec30655c) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/5/2022/5-sol-math-8-9-sl_os-22-23.pdf#p4) |
| `c07cf2e182c2` | 2021 | 11 | 5 | auto | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/turgor/c07cf2e182c2) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2020/18808026-sol-math-10-11-baz_vs-20-21.pdf#p5) |
| `a2e285944d7c` | 2021 | 11 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/a2e285944d7c) | [оригинал](https://problems.ru/view_problem_details_new.php?id=67045) |
| `42d9fdf62946` | 2021 | 9 | 4 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/turgor/42d9fdf62946) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2021/5-sol-math-8-9-sl_os-21-22.pdf#p2) |
| `fa3f14f11c6c` | 2021 | 9 | 2 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/turgor/fa3f14f11c6c) | [оригинал](https://turgor.ru/problems/43/os-43-sl-avt.pdf#page=1) |
| `ece8ec74e46a` | 2020 | 9 | 3 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/ece8ec74e46a) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2020/18808026-sol-math-8-9-baz_os-20-21.pdf#page=1) |
| `33cd65d2bcae` | 2019 | 9 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/33cd65d2bcae) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2018/5-ans-math-8-9-baz_ves-18-9.pdf#p2) |
| `e41866e7b1dc` | 2019 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/e41866e7b1dc) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2018/5-ans-math-8-9-baz_ves-18-9.pdf#p5) |
| `c26ce89b4ac3` | 2019 | 11 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/c26ce89b4ac3) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2018/5-ans-math-10-11-baz_ves-18-9.pdf#p4) |
| `b37cd988051a` | 2019 | 9 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/b37cd988051a) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2019/5-ans-math-8-9-baz_os-19-0.pdf#p5) |
| `a6e2b989d058` | 2018 | 8 | 3 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/turgor/a6e2b989d058) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66690) |
| `8f74590457ca` | 2018 | 9 | 1 | пропуск | Проверены: условие 0, решение 2 | [карточка](https://formyla.net/olymp-catalog/turgor/8f74590457ca) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66692) |
| `72b47c7a53c9` | 2018 | 9 | 3 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/turgor/72b47c7a53c9) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66690) |
| `babe9dec53f4` | 2018 | 9 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/babe9dec53f4) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2018/5-ans-math-8-9-baz_os-18-9.pdf#p3) |
| `58584401ae66` | 2018 | 9 | 4 | auto | Проверены: условие 0, решение 4 | [карточка](https://formyla.net/olymp-catalog/turgor/58584401ae66) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2018/5-ans-math-8-9-sl_os-18-9.pdf#p4) |
| `3f5fbb1b268e` | 2018 | 11 | 4 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/3f5fbb1b268e) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/5/2018/5-ans-math-10-11-sl_os-18-9.pdf#page=2) |
| `755db93b08f5` | 2017 | 9 | 2 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/755db93b08f5) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66100) |
| `e0ac4057617a` | 2016 | 8 | 2 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/e0ac4057617a) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66100) |
| `0303947e5ac5` | 2014 | 8 | 4 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/0303947e5ac5) | [оригинал](https://problems.ru/view_problem_details_new.php?id=65152) |
| `cad05312dbd4` | 2011 | 11 | 2 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/cad05312dbd4) | [оригинал](https://problems.ru/view_problem_details_new.php?id=116389) |
| `c5ede6df44f0` | 2010 | 10 | 2 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/turgor/c5ede6df44f0) | [оригинал](https://problems.ru/view_problem_details_new.php?id=116412) |
| `b905d54014fa` | 2010 | 9 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/turgor/b905d54014fa) | [оригинал](https://problems.ru/view_problem_details_new.php?id=116046) |

### Ломоносов

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `bb5f1d611314` | 2025 | 5 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/lomonosov/bb5f1d611314) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/348/2024/348-sol-math-5-6-final-24-25.pdf) |
| `e31b3b8ea232` | 2024 | 6 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/lomonosov/e31b3b8ea232) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/348/2023/348-sol-math-5-6-final-23-24.pdf) |
| `e6a03f3e2f36` | 2023 | 9 | 2 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/lomonosov/e6a03f3e2f36) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/348/2023/348-sol-math-10-final-23-24.pdf) |
| `76e54a078827` | 2023 | 9 | 7 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/lomonosov/76e54a078827) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/348/2023/348-sol-math-9-final-23-24.pdf) |
| `9a3a4b2895f3` | 2023 | 9 | 7 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/lomonosov/9a3a4b2895f3) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/348/2023/348-sol-math-10-final-23-24.pdf) |
| `da00b71d2757` | 2019 | 9 | 5 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/lomonosov/da00b71d2757) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2018/14287916-tasksans-math-9-final-18-19.pdf#p6) |
| `b11d6f56a0b5` | 2017 | 8 | 1 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/lomonosov/b11d6f56a0b5) | [оригинал](https://mathus.ru/olymp/lom2017m7-8.pdf) |
| `b03ded1a19fe` | 2011 | 7 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/b03ded1a19fe) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p1) |
| `2ee4dc895398` | 2011 | 7 | 4 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/2ee4dc895398) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p5) |
| `cb1733f02241` | 2011 | 8 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/cb1733f02241) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p1) |
| `7a4df776908a` | 2011 | 9 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/7a4df776908a) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p5) |
| `118391aee793` | 2010 | 7 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/118391aee793) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p1) |
| `587ef5fb49bf` | 2010 | 7 | 5 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/587ef5fb49bf) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p5) |
| `fdaf030be51c` | 2010 | 7 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/fdaf030be51c) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p1) |
| `84d9f8184641` | 2010 | 7 | 4 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/84d9f8184641) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p5) |
| `0659896ca029` | 2010 | 8 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/0659896ca029) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p1) |
| `db9319eee977` | 2010 | 9 | 1 | auto | Без рисунка в источнике; удалён чужой хвост | [карточка](https://formyla.net/olymp-catalog/lomonosov/db9319eee977) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-9-final-10-1.pdf#p5) |
| `fb5596b215cd` | 2010 | 7 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/lomonosov/fb5596b215cd) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/348/2010/5_16969-ans-math-7-otbor-10-1.pdf) |

### Формула Единства

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `b276c97b94ad` | 2025 | 6 | 5 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/formula-unity/b276c97b94ad) | [оригинал](https://www.formulo.org/wp-content/uploads/2026/04/fdi_tm_25_26_math_f_sol_ru-1.pdf#p6) |
| `41ebeefab89c` | 2025 | 8 | 1 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/formula-unity/41ebeefab89c) | [оригинал](https://www.formulo.org/wp-content/uploads/2026/04/fdi_tm_25_26_math_f_sol_ru-1.pdf#p13) |
| `3a016cb20968` | 2024 | 9 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/3a016cb20968) | [оригинал](https://mathus.ru/olymp/FETT2024Math9.pdf) |
| `35171e9e60d4` | 2024 | 6 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/35171e9e60d4) | [оригинал](https://mathus.ru/olymp/FETT2024Math6.pdf) |
| `4aa888d01f98` | 2024 | 8 | 2 | auto | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/formula-unity/4aa888d01f98) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2024/223-sol-math-8-final-24-25.pdf#p2) |
| `cf9d74edca29` | 2024 | 11 | 5 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/formula-unity/cf9d74edca29) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2024/223-sol-math-11-final-24-25.pdf#p6) |
| `6b8b1acdbe32` | 2024 | 5 | 2 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/formula-unity/6b8b1acdbe32) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2024/223-taskssol-math-5-otbor-24-25.pdf#p4) |
| `4efdd18b475a` | 2024 | 9 | 2 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/formula-unity/4efdd18b475a) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2024/223-taskssol-math-9-otbor-24-25.pdf#p2) |
| `beeaa45f2fe3` | 2024 | 10 | 5 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/formula-unity/beeaa45f2fe3) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2024/223-taskssol-math-10-otbor-24-25.pdf#p5) |
| `b8685cfae9fc` | 2023 | 5 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/b8685cfae9fc) | [оригинал](https://mathus.ru/olymp/FETT2023Math5.pdf) |
| `bd9d64255dc5` | 2023 | 8 | 1 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/formula-unity/bd9d64255dc5) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-sol-math-8-final-23-24.pdf#p2) |
| `bc718738f4aa` | 2023 | 6 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/bc718738f4aa) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-6-otbor-23-24.pdf#p3) |
| `87e3c005f607` | 2023 | 6 | 5 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/formula-unity/87e3c005f607) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-6-otbor-23-24.pdf#p6) |
| `1ee5ffc0810f` | 2023 | 7 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/1ee5ffc0810f) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-6-otbor-23-24.pdf#p3) |
| `0a385a71feb0` | 2023 | 7 | 5 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/0a385a71feb0) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-7-otbor-23-24.pdf#p6) |
| `243b14f0a23e` | 2023 | 8 | 5 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/243b14f0a23e) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-8-otbor-23-24.pdf#p5) |
| `9892ef0491f3` | 2023 | 9 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/9892ef0491f3) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-9-otbor-23-24.pdf#p1) |
| `38cb40b5f587` | 2023 | 9 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/formula-unity/38cb40b5f587) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-9-otbor-23-24.pdf#p3) |
| `83094f693b28` | 2023 | 10 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/83094f693b28) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2023/223-taskssol-math-10-otbor-23-24.pdf#p2) |
| `a4eeae8ddfa1` | 2022 | 5 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/a4eeae8ddfa1) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2022/223-sol-math-5-final-22-23.pdf#p1) |
| `df6511b736e6` | 2022 | 5 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/df6511b736e6) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2022/223-sol-math-5-final-22-23.pdf#p3) |
| `038228fec46c` | 2022 | 5 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/038228fec46c) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2022/223-sol-math-5-final-22-23.pdf#p4) |
| `9f4240f4a0c6` | 2022 | 8 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/9f4240f4a0c6) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2022/223-sol-math-8-final-22-23.pdf#p5) |
| `4419f88e1424` | 2022 | 9 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/formula-unity/4419f88e1424) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/223/2022/223-sol-math-9-final-22-23.pdf#p2) |
| `df9f0380c8be` | 2021 | 8 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/df9f0380c8be) | [оригинал](https://www.formulo.org/wp-content/uploads/2022/04/fdi_tm_2021_22_round2_sol-ru-1.pdf#p4) |
| `f2315b93e27d` | 2021 | 8 | 4 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/formula-unity/f2315b93e27d) | [оригинал](https://www.formulo.org/wp-content/uploads/2022/04/fdi_tm_2021_22_round2_sol-ru-1.pdf#p6) |
| `800821608c45` | 2021 | 10 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/800821608c45) | [оригинал](https://www.formulo.org/wp-content/uploads/2022/04/fdi_tm_2021_22_round2_sol-ru-1.pdf#p4) |
| `589b62774c46` | 2019 | 6 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/589b62774c46) | [оригинал](https://www.formulo.org/wp-content/uploads/2020/03/fdi_tm_2019_20_round2_sol_ru.pdf#p4) |
| `f0fc8752d744` | 2019 | 7 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/f0fc8752d744) | [оригинал](https://mathus.ru/olymp/FETT2019Math7.pdf) |
| `59af76d5aac3` | 2019 | 8 | 3 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/59af76d5aac3) | [оригинал](https://www.formulo.org/wp-content/uploads/2022/05/fdi_tm_2019_20_round2_solcrit-ru.pdf#p7) |
| `3ab466895f8c` | 2019 | 8 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/3ab466895f8c) | [оригинал](https://mathus.ru/olymp/FETT2019Math8.pdf) |
| `a1e67f50b237` | 2019 | 11 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/a1e67f50b237) | [оригинал](https://mathus.ru/olymp/FETT2019Math11.pdf) |
| `2adb13d789b5` | 2018 | 8 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/formula-unity/2adb13d789b5) | [оригинал](https://www.formulo.org/wp-content/uploads/2019/02/fditm_2018-19_p_ru_sol.pdf#p3) |

### Покори Воробьёвы горы!

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `86ad2d0f3988` | 2025 | 7 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/pvg/86ad2d0f3988) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/115/2024/115-sol-math-9-final-24-25.pdf) |
| `5dfab10fab5b` | 2025 | 8 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/pvg/5dfab10fab5b) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/115/2024/115-sol-math-9-final-24-25.pdf) |
| `80c623292505` | 2024 | 9 | 3 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/pvg/80c623292505) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/115/2023/115-sol-math-7-8-final-23-24.pdf) |
| `61e3a6774f9f` | 2018 | 11 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/pvg/61e3a6774f9f) | [оригинал](https://olymp.sdamgia.ru/problem?id=6240) |
| `45fb37ece11e` | 2015 | 8 | 2 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/pvg/45fb37ece11e) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/115/2014/4016186-ans-math-8-final-14-5.pdf#p2) |

### Эйлер

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `6dd88f764113` | 2019 | 8 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/euler/6dd88f764113) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2018/29-ans-math-day1-region-18-9.pdf) |
| `1430cdc64540` | 2018 | 8 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/euler/1430cdc64540) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2017/29-ans-math-tur1-dist_stage-17-8.pdf#p3) |
| `3252ccda8bf8` | 2017 | 8 | 2 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/euler/3252ccda8bf8) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2016/29-ans-math-day1-final-16-7.pdf#p2) |
| `813f0a5022a9` | 2016 | 8 | 4 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/euler/813f0a5022a9) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2015/29-ans-math-day2-final-15-6.pdf) |
| `be49d57578f7` | 2015 | 8 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/euler/be49d57578f7) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2014/29-ans-math-tur1-dist_stage-14-5.pdf) |
| `057517b926b2` | 2015 | 8 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/euler/057517b926b2) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2014/29-ans-math-region-14-5.pdf) |
| `92aa55659587` | 2013 | 8 | 2 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/euler/92aa55659587) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2012/29-ans-math-day1-final-12-3.pdf) |
| `2e20d31ff3db` | 2011 | 8 | 5 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/euler/2e20d31ff3db) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2010/29-ans-math-tur1-dist_stage-10-1.pdf) |
| `3f247492c141` | 2011 | 8 | 1 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/euler/3f247492c141) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/29/2010/29-ans-math-region-10-1.pdf) |

### Высшая проба

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `4c977558e041` | 2025 | 7 | 3 | auto | Проверены: условие 2, решение 0 | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/4c977558e041) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/149/2024/149-sol-math-7-final-24-25.pdf#p4) |
| `ec3833ee1116` | 2025 | 9 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/ec3833ee1116) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/149/2024/149-sol-math-9-final-24-25.pdf#p5) |
| `c4a4cb467dda` | 2016 | 9 | 1 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/c4a4cb467dda) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/149/2015/5550814-ans-math-9-final-15-16.pdf#p1) |
| `a84252dd12d4` | 2016 | 11 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/a84252dd12d4) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/149/2015/5550814-ans-math-11-final-15-16.pdf#p3) |
| `c06d63e8be9b` | 2016 | 11 | 5 | пропуск | Проверены: условие 0, решение 5 | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/c06d63e8be9b) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/149/2015/5550814-ans-math-11-final-15-16.pdf#p5) |
| `457800e6f2eb` | 2015 | 7 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/457800e6f2eb) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/149/2014/4016079-ans-math-7-final-14-15.pdf#p3) |
| `7affe0d6c1a1` | 2015 | 8 | 2 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/7affe0d6c1a1) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/149/2014/4016079-ans-math-8-final-14-15.pdf#p2) |
| `56ea60b1b73f` | 2015 | 9 | 4 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/56ea60b1b73f) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/149/2014/4016079-ans-math-9-final-14-15.pdf#p4) |
| `9ccc357c86ef` | 2015 | 10 | 4 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/9ccc357c86ef) | [оригинал](https://olymp.hse.ru/data/2015/03/17/1092955838/11 математика.pdf#p4) |
| `7242c2f09bc2` | 2015 | 10 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/7242c2f09bc2) | [оригинал](https://olymp.hse.ru/data/2015/03/17/1092955784/10 математика.pdf#p3) |
| `ed97241160f6` | 2013 | 8 | 3 | пропуск | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/ed97241160f6) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/149/2012/3036834-ans-math-8-final-12-3.pdf#p3) |
| `6f5dea4ce148` | 2012 | 9 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/6f5dea4ce148) | [оригинал](https://www.hse.ru/data/2012/03/21/1264799965/9.pdf) |
| `a5b8ba0fcc38` | 2012 | 10 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/a5b8ba0fcc38) | [оригинал](https://www.hse.ru/data/2012/03/22/1264590401/10.pdf) |
| `34fa31302b5f` | 2012 | 11 | 3 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/vysshaya-proba/34fa31302b5f) | [оригинал](https://www.hse.ru/data/2012/03/30/1265308868/11_new.pdf) |

### Математический праздник

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `94bf7d4d1df7` | 2025 | 6 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/94bf7d4d1df7) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/25/book.pdf) |
| `c4f28638e9f3` | 2025 | 6 | 3 | пропуск | Проверены: условие 0, решение 1; исправлен ложный флаг | [карточка](https://formyla.net/olymp-catalog/matprazdnik/c4f28638e9f3) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/25/book.pdf) |
| `6694549b39bd` | 2025 | 7 | 5 | пропуск | Проверены: условие 0, решение 1; исправлен ложный флаг | [карточка](https://formyla.net/olymp-catalog/matprazdnik/6694549b39bd) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/25/book.pdf) |
| `a6d936ae06c3` | 2024 | 6 | 1 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/a6d936ae06c3) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/24/book.pdf) |
| `dbdc1d0a6920` | 2024 | 6 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/dbdc1d0a6920) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/24/book.pdf) |
| `ec458d12e4ad` | 2024 | 6 | 5 | auto | Проверены: условие 0, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/ec458d12e4ad) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/24/book.pdf) |
| `9ef1d3da3c5d` | 2024 | 6 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/9ef1d3da3c5d) | [оригинал](https://olympiads.mccme.ru/matprazdnik/prob_24.html) |
| `fc8db88393be` | 2024 | 7 | 5 | auto | Проверены: условие 0, решение 3; исправлен ложный флаг | [карточка](https://formyla.net/olymp-catalog/matprazdnik/fc8db88393be) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/24/book.pdf) |
| `6a301096b602` | 2024 | 7 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/6a301096b602) | [оригинал](https://olympiads.mccme.ru/matprazdnik/prob_24.html) |
| `fea193700e53` | 2023 | 6 | 6 | auto | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/matprazdnik/fea193700e53) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/23/book.pdf) |
| `87cd37f61374` | 2023 | 7 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/87cd37f61374) | [оригинал](https://olympiads.mccme.ru/matprazdnik/prob_23.html) |
| `02b99a22f0b9` | 2022 | 6 | 4 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/02b99a22f0b9) | [оригинал](https://olympiads.mccme.ru/matprazdnik/prob_22.html) |
| `036da4bb1e6c` | 2020 | 6 | 4 | auto | Проверены: условие 3, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/036da4bb1e6c) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/20/book.pdf) |
| `a22f91604449` | 2020 | 6 | 6 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/a22f91604449) | [оригинал](https://problems.ru/view_problem_details_new.php?id=66524) |
| `4970357d28b6` | 2020 | 7 | 4 | auto | Проверены: условие 2, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/4970357d28b6) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/20/book.pdf) |
| `6d092b77c64d` | 2020 | 7 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/6d092b77c64d) | [оригинал](https://olympiads.mccme.ru/matprazdnik/prob_20.html) |
| `74d90c4bb8df` | 2019 | 6 | 6 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/74d90c4bb8df) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/19/book.pdf) |
| `66a58c70dab0` | 2019 | 6 | 4 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/66a58c70dab0) | [оригинал](https://olympiads.mccme.ru/matprazdnik/prob_19.html) |
| `76727d0a27d4` | 2018 | 6 | 3 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/76727d0a27d4) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/18/book.pdf) |
| `ee509d35b518` | 2017 | 6 | 1 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/ee509d35b518) | [оригинал](https://problems.ru/view_problem_details_new.php?id=65972) |
| `da98f75594f3` | 2017 | 7 | 5 | пропуск | Проверены: условие 1, решение 1 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/da98f75594f3) | [оригинал](https://problems.ru/view_problem_details_new.php?id=65980) |
| `1475e2aaee9e` | 2016 | 6 | 2 | пропуск | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/1475e2aaee9e) | [оригинал](https://problems.ru/view_problem_details_new.php?id=65597) |
| `1ca705184983` | 2016 | 6 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/1ca705184983) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/16/book.pdf) |
| `c8e053f9daa1` | 2016 | 7 | 2 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/c8e053f9daa1) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/16/book.pdf) |
| `00541deba611` | 2015 | 6 | 2 | auto | Проверены: условие 2, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/00541deba611) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/15/book.pdf) |
| `ec94d4d2be3d` | 2014 | 6 | 5 | auto | Проверены: условие 1, решение 0 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/ec94d4d2be3d) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/14/book.pdf) |
| `0a8cfc33c902` | 2013 | 6 | 4 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/matprazdnik/0a8cfc33c902) | [оригинал](https://olympiads.mccme.ru/matprazdnik/image/13/book.pdf) |

### СПбГУ

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `b41820c427a4` | 2023 | 11 | 5 | auto | Проверены: условие 0, решение 1 | [карточка](https://formyla.net/olymp-catalog/spbgu/b41820c427a4) | [оригинал](https://tasks.olimpiada.ru/upload/files/tasks/443/2022/443-sol-math-10-11-final-22-23.pdf) |
| `926fba4807d0` | 2022 | 11 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/spbgu/926fba4807d0) | [оригинал](https://math-olymp.sdamgia.ru/problem?id=8239) |

### Физтех

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `dc6ae28f3682` | 2018 | 10 | 2 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/phystech/dc6ae28f3682) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/395/2017/8643504-ans-math-10-final-17-18.pdf#p2) |
| `4bccccb080d3` | 2018 | 9 | 1 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/phystech/4bccccb080d3) | [оригинал](https://mathus.ru/olymp/fizteh-online2018m9.pdf) |
| `4aa7c609614d` | 2015 | 10 | 5 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/phystech/4aa7c609614d) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/395/2014/4016476-ans-math-10-final-14-5.pdf) |

### Прочие источники

| UID | Год | Класс | № | Группа | Действие | Карточка | Первоисточник |
|---|---:|---:|---|---|---|---|---|
| `8cc58fbf5809` | 2016 | 9 | 4 | пропуск | Без рисунка в источнике | [карточка](https://formyla.net/olymp-catalog/other/8cc58fbf5809) | [оригинал](https://rsr-olymp.ru/upload/files/tasks/395/2015/5550804-ans-math-9-final-15-16.pdf) |

## Повторная проверка

```sh
python scripts/olymp_catalog_figs_audit.py --csv reports/olymp_figs_audit.csv
python scripts/olymp_figs_validate.py
python scripts/olymp_figs_quarantine.py  # dry-run, без записи
python scripts/olymp_figs_contact_sheet.py
python -m pytest --noconftest -q tests/test_olymp_figs_source_audit.py tests/test_catalog_preservation.py
git diff --check
```

Тесты работают без производственной БД. Для них нужны pytest, Pillow, Flask, Flask-Login и Markdown. Ручное восстановление архивного объекта описано в `archive/olymp_figures_review/README.md`.

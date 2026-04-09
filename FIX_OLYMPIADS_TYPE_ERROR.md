# Исправление TypeError в /olympiads

## Проблема
`TypeError: '<' not supported between instances of 'int' and 'str'` при сериализации в JSON

## Решение

### В app.py, функция olympiads() (строка ~648)

Перед `return render_template(...)` добавить проверку и конвертацию типов:

```python
# Конвертируем все grade в int для корректной сериализации
for slug, years in olympiad_data.items():
    for year, rounds in years.items():
        for rnd, val in rounds.items():
            # val = [round_title, [grades]]
            if len(val) > 1 and isinstance(val[1], list):
                val[1] = [int(g) if isinstance(g, str) else g for g in val[1]]

return render_template('olympiads.html', 
                      olympiad_data=olympiad_data,
                      olympiads_info=OLYMPIADS_INFO)
```

## Готово!
Это исправит смешанные типы int/str в списках классов.

# FORMYLA 20-parallel rebuild runner

1. Положи API-вызов модели в `worker.py` в функцию `call_model`.
2. Запусти: `python orchestrator.py --workers 20 --queue-dir ../ --out-dir results`.
3. Проверь результаты: `python merge_results.py --base ../full_dataset_v2_with_methods_latex_final.json --results-dir results --out final.json`.
4. Валидируй: `python validator.py final.json`.

Очередь уже разбита на 20 файлов `formyla_worker_XX_jobs.json`.

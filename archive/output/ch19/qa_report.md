# CH19 QA report (детерминированный, без LLM/vision)


| код проблемы | количество | до 5 примеров task_uid |
|---|---|---|
| AUX_EXPECTED_BUT_MISSING | 3 | GEN-L123-w2_78_s4-e1a676bdcb62bb97, 98cdb758e6bec2caed50bb49a29e9c1d47a0c0c3587f13e80101b2bcf7be8bee, GEN-L123-w2_21_s3-f0c4974b13a3b0b1 |
| AUX_SVG_MISSING | 1 | GEN-fill_0440 |

## Сводка по задачам (done)

| task_uid | style | has_aux | aux_ops | base_ops | codes |
|---|---|---|---|---|---|
| GEN-L123-w2_78_s4-e1a676bdcb62bb97 | constructive | False | 0 | 12 | AUX_EXPECTED_BUT_MISSING |
| GEN-fill_0440 | constructive | True | 1 | 8 | AUX_SVG_MISSING |
| 98cdb758e6bec2caed50bb49a29e9c1d47a0c0c3587f13e80101b2bcf7be8bee | constructive | False | 0 | 4 | AUX_EXPECTED_BUT_MISSING |
| GEN-L123-w2_21_s3-f0c4974b13a3b0b1 | constructive | False | 0 | 10 | AUX_EXPECTED_BUT_MISSING |
| GEN-L123-w2_83_s5-6c86c5e3df65748d | angle_chase | False | 0 | 15 | OK |

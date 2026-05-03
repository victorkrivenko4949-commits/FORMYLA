# Маппинг (combo_id, problem_num) -> путь к файлу картинки (относительно static/)
# combo_id — это id пробника из olympiads.py
# problem_num — это номер задачи внутри пробника (поле "num")
#
# Используется в app.py для привязки картинок к задачам олимпиад.

IMAGE_MAP = {
    # Ломоносов 2024, 5 класс (combo_id=216), задачи 1 и 4
    (216, 1): "problem_images/lomonosov_2024_5_1.png",
    (216, 4): "problem_images/lomonosov_2024_5_4.png",

    # Ломоносов 2024, 6 класс (combo_id=217), задачи 1 и 4
    (217, 1): "problem_images/lomonosov_2024_6_1.png",
    (217, 4): "problem_images/lomonosov_2024_6_4.png",

    # Ломоносов 2024, 7 класс (combo_id=218), задача 5
    (218, 5): "problem_images/lomonosov_2024_7_5.png",

    # Ломоносов 2024, 8 класс (combo_id=219), задача 5
    (219, 5): "problem_images/lomonosov_2024_8_5.png",

    # Ломоносов 2019, 9 класс (combo_id=189), задача 5
    (189, 5): "problem_images/lomonosov_2019_9_5.png",

    # Ломоносов 2020, 7 класс (combo_id=192), задача 2
    (192, 2): "problem_images/lomonosov_2020_7_2.png",

    # Ломоносов 2020, 8 класс (combo_id=193), задача 2
    (193, 2): "problem_images/lomonosov_2020_8_2.png",

    # Ломоносов 2020, 9 класс (combo_id=194), задача 1
    (194, 1): "problem_images/lomonosov_2020_9_1.png",

    # Ломоносов 2022, 5 класс (combo_id=202), задача 2
    (202, 2): "problem_images/lomonosov_2022_5_2.png",

    # Ломоносов 2022, 6 класс (combo_id=203), задача 2
    (203, 2): "problem_images/lomonosov_2022_6_2.png",

    # Formula Unity 2020, 7 класс (combo_id=44), задача 4
    (44, 4): "problem_images/formula_unity_2020_7_4.png",

    # Formula Unity 2020, 7 класс дубликат (combo_id=724), задача 4
    (724, 4): "problem_images/formula_unity_2020_7_4.png",

    # Formula Unity 2020, 8 класс (combo_id=725), задача 4
    (725, 4): "problem_images/formula_unity_2020_8_4.png",

    # Formula Unity 2022, 6 класс (combo_id=748), задача 4
    (748, 4): "problem_images/formula_unity_2022_6_4.png",

    # Formula Unity 2022, 7 класс (combo_id=749), задача 1
    (749, 1): "problem_images/formula_unity_2022_7_1.png",

    # Курчатов 2023, 7 класс (combo_id=125), задача 4
    (125, 4): "problem_images/kurchatov_2023_7_4.png",

    # PVG 2017, 5 класс (combo_id=278), задача 5
    (278, 5): "problem_images/pvg_2017_5_5.png",

    # PVG 2017, 6 класс (combo_id=279), задача 5
    (279, 5): "problem_images/pvg_2017_6_5.png",

    # PVG 2017, 9 класс (combo_id=282), задача 4
    (282, 4): "problem_images/pvg_2017_9_4.png",

    # Турнир городов 2017, 9 класс (combo_id=396), задача 2
    (396, 2): "problem_images/turgor_2017_9_2.png",

    # СПбГУ 2023, 6 класс (combo_id=342), задача 3
    (342, 3): "problem_images/spbgu_2023_6_3.png",

    # СПбГУ 2023, 7 класс (combo_id=344), задача 3
    (344, 3): "problem_images/spbgu_2023_7_3.png",

    # Высшая проба 2018, 10 класс (combo_id=595), задача 4
    (595, 4): "problem_images/vysshaya_proba_2018_10_4.png",
}

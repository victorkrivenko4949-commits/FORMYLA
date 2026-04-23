TOPIC_KEYWORDS_BY_GRADE = {
    6: {
        'algebra': ['дроби', 'нод', 'нок'],
        'geometry': ['геометрия', 'периметры'],
        'combinatorics': ['комбинаторика'],
        'number_theory': ['делимость', 'остатки'],
        'kl_movement': ['логика', 'рыцари', 'инварианты', 'разрезания', 'графы'],
    },
}

def get_keywords_for_grade_topic(grade, topic):
    return TOPIC_KEYWORDS_BY_GRADE.get(grade, {}).get(topic, [])

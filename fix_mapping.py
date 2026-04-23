import os
path = 'services/adaptive_topic_mapping.py'
code = (
    "TOPIC_KEYWORDS_BY_GRADE = {\n"
    "    6: {\n"
    "        'algebra': ['\u0434\u0440\u043e\u0431\u0438', '\u043d\u043e\u0434', '\u043d\u043e\u043a'],\n"
    "        'geometry': ['\u0433\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u044f', '\u043f\u0435\u0440\u0438\u043c\u0435\u0442\u0440\u044b'],\n"
    "        'combinatorics': ['\u043a\u043e\u043c\u0431\u0438\u043d\u0430\u0442\u043e\u0440\u0438\u043a\u0430'],\n"
    "        'number_theory': ['\u0434\u0435\u043b\u0438\u043c\u043e\u0441\u0442\u044c', '\u043e\u0441\u0442\u0430\u0442\u043a\u0438'],\n"
    "        'kl_movement': ['\u043b\u043e\u0433\u0438\u043a\u0430', '\u0440\u044b\u0446\u0430\u0440\u0438', '\u0438\u043d\u0432\u0430\u0440\u0438\u0430\u043d\u0442\u044b', '\u0440\u0430\u0437\u0440\u0435\u0437\u0430\u043d\u0438\u044f', '\u0433\u0440\u0430\u0444\u044b'],\n"
    "    },\n"
    "}\n"
    "\n"
    "def get_keywords_for_grade_topic(grade, topic):\n"
    "    return TOPIC_KEYWORDS_BY_GRADE.get(grade, {}).get(topic, [])\n"
)
with open(path, 'w', encoding='utf-8') as f:
    f.write(code)
print('Written', len(code), 'bytes')

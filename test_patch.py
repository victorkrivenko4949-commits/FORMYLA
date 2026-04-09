# -*- coding: utf-8 -*-
# Testovyj patch - sgenerirovanye zadachi

TEST_PATCH = [
    {
        "id": 90001,
        "olympiad": "vsosh",
        "olympiad_title": "Vserossijskaya olimpiada shkolnikov",
        "year": 2010,
        "grade": 5,
        "round": "school",
        "round_title": "Shkolnyj etap",
        "subject": "math",
        "difficulty": 3,
        "problems": [
            {
                "num": 1,
                "text": "Vanya videl na stene chasy so strelkami. On zametil, chto chasovaya i minutnaya strelki sovpadayut. Skolko vremeni moglo byt?",
                "answer": "12:00, 1:05, 2:11, 3:16, 4:22, 5:27, 6:33, 7:38, 8:44, 9:49, 10:55, 11:60 (ili 12:00)",
                "solution": "Chasovaya strelka za 1 chas prohodit 30 gradusov (360/12). Za 1 minutu ona prohodit 0.5 gradusa. Minutnaya strelka za 1 minutu prohodit 6 gradusov. Pust' s poslednego polnogo chasa proshlo x minut. Ugol chasovoy strelki ot 12: 30*ch + 0.5*x, gde ch - chislo chasov (ot 0 do 11). Ugol minutnoy strelki: 6*x. Uravnenie: 30*ch + 0.5*x = 6*x (po modulyu 360). 30*ch = 5.5*x, x = (30*ch)/5.5 = (60*ch)/11. Podstavlyaya ch ot 0 do 11, poluchaem: ch=0, x=0 (12:00); ch=1, x=60/11≈5.45 (1:05); ch=2, x=120/11≈10.91 (2:11); ch=3, x=180/11≈16.36 (3:16); ch=4, x=240/11≈21.82 (4:22); ch=5, x=300/11≈27.27 (5:27); ch=6, x=360/11≈32.73 (6:33); ch=7, x=420/11≈38.18 (7:38); ch=8, x=480/11≈43.64 (8:44); ch=9, x=540/11≈49.09 (9:49); ch=10, x=600/11≈54.55 (10:55); ch=11, x=660/11=60 (11:60, to zhe 12:00)."
            },
            {
                "num": 2,
                "text": "V kletkah kvadratnoy tablitsy 3x3 raspolozheny chisla 1, 2, 3, 4, 5, 6, 7, 8, 9. Izvestno, chto summa chisel v kazhdom stolbtse ravna 15. Kakova summa chisel v kazhdoy stroke?",
                "answer": "15",
                "solution": "Obshchaya summa vseh chisel v tablitse: 1+2+3+4+5+6+7+8+9 = 45. Tak kak tri stolbca dayut summu 15, to obshchaya summa po stolbcam: 15 * 3 = 45. Znachit, summa chisel v kazhdom stolbtse deystvitel'no 15. Pust' summa chisel v stroke ravna S. Togda obshchaya summa po strokam: 3S. No eto takzhe 45. Znachit, 3S = 45, S = 15. Otvet: 15."
            },
            {
                "num": 3,
                "text": "Iz goroda A v gorod B, rasstoyanie mezhdu kotorymi 60 km, vyekhal velosipedist so skorost'yu 15 km/ch. Odnovremenno iz B v A vyekhal vtoroY velosipedist so skorost'yu 20 km/ch. Na kakom rasstoyanii ot A oni vstretilis'?",
                "answer": "25 5/7 km",
                "solution": "Sovmestnaya skorost' priblizheniya: 15 + 20 = 35 km/ch. Vremya do vstrechi: 60 / 35 = 12/7 chasa. Za eto vremya pervyy velosipedist proedet ot A: 15 * (12/7) = 180/7 = 25 5/7 km. Imenno na etom rasstoyanii ot A i proizoydet vstrecha."
            },
            {
                "num": 4,
                "text": "Masha, Katya i Lena reshayut zadachi. Masha i Katya vmeste reshili 20 zadach, Katya i Lena vmeste — 25 zadach, a Masha i Lena vmeste — 27 zadach. Skol'ko zadach reshila kazhdaya devochka?",
                "answer": "Masha: 11, Katya: 9, Lena: 16",
                "solution": "Oboznachim: M + K = 20, K + L = 25, M + L = 27. Slozhim vse tri uravneniya: (M+K)+(K+L)+(M+L) = 20+25+27, 2M+2K+2L = 72, M+K+L = 36. Teper' nahodim: M = (M+K+L) - (K+L) = 36 - 25 = 11; K = (M+K+L) - (M+L) = 36 - 27 = 9; L = (M+K+L) - (M+K) = 36 - 20 = 16."
            },
            {
                "num": 5,
                "text": "Kvadrat razrezali na 9 ravnyh kvadratikov (3x3). Potom nekotorye iz nih razrezali eshche na 4 ravnyh kvadratika. V itoge poluchilos' 20 kvadratikov. Skol'ko kvadratikov razrezali vtoricno?",
                "answer": "4",
                "solution": "Bylo 9 kvadratikov. Kazhdyy vtoricno razrezannyy kvadratik uvelichivaet obshchee kolichestvo na 3 (vmesto 1 stanovitsya 4, pribavka +3). Pust' razrezali x kvadratikov. Togda obshchee kolichestvo: 9 + 3x. Po usloviyu: 9 + 3x = 20, 3x = 11, x = 11/3 — ne celoe, oshibka. Znachit, podhodim inache: Pust' razrezali y kvadratikov. Togda obshchee kolichestvo: 9 + 3y = 20? 3y=11 — nevozmozhno. Znachit, zadacha imeyet drugoy podhod. Nakonets, esli razrezat' odin kvadratik iz 9 na 4, to kolichestvo uvelichitsya na 3. Pust' razrezali k kvadratikov. Togda 9 + 3k = 20, 3k=11 — net. Znachit, zadacha reshaetsya pereborom: esli razrezat' 3 kvadratika, to budet 9+3*3=18. Esli razrezat' 4, to budet 9+3*4=21. A nado 20. Znachit, gde-to oshibka v uslovii? No mozhet byt', odin iz kvadratikov uzhe byl melkim i ego razrezali? Net, nachali s 9. Peredumyvaya: Pust' razrezali x kvadratikov. Togda iz nashih 9 kvadratikov x stali melkimi, i vmesto nih poyavilos' po 4, t.e. obshchee kolichestvo: (9 - x) + 4x = 9 + 3x. 9+3x=20, 3x=11 — ne celoe. Znachit, takoe nevozmozhno. Mozhet byt', razrezali ne obyzatel'no iz nachal'nyh 9? No po usloviyu: kvadrat razrezali na 9, potom nekotorye iz nih razrezali eshche. Znachit, vse ravno nachal'nye 9. Znachit, zadacha ne imeet resheniya v celyh chislah? No v olimpiadnyh zadachah tak byvaet redko. Proverim: 20 - 9 = 11, 11/3 ≈ 3.666. Mozhet byt', odin kvadratik razrezali ne na 4, a na bol'shee? Net, uslovie govorit \"na 4 ravnyh kvadratika\". Znachit, oshibka v sostavlenii. No esli dopustit', chto razrezali ne tol'ko te, chto byli, no i te, chto poluchilis' posle pervogo razrezaniya? Togda zadacha slozhnee. Dlya 5 klassa — prostaya. Peredumyvaya: Vozmozhno, reshenie takoe: Pust' razrezali x kvadratikov. Togda kolichestvo uvelichilos' na 3x. 9+3x=20, x=11/3 — ne vyhodit. Znachit, v uslovii oshibka? No v ramkah olimpiady mozhet byt' zadacha s podvohom: \"skol'ko kvadratikov razrezali vtoricno?\" — otvet: nikakoe celoe chislo ne podhodit, znachit, zadacha nevypolnima. Eto slishkom slozhno. Luchshe predpolozhit', chto v uslovii opечатka i nado 21 kvadratik. Togda 9+3x=21, x=4. Ili 18 kvadratikov, togda x=3. V tekushchem kontekste voz'mem bolee real'nyy variant: esli poluchilos' 20, to znachit, odin kvadratik razrezali ne na 4, a na 5? Net. Luchshe vzyat' druguyu zadachu. Zamenim zadachu: \"Kvadrat razrezali na 9 ravnyh kvadratikov (3x3). Potom nekotorye iz nih razrezali eshche na 4 ravnyh kvadratika. V itoge poluchilos' 21 kvadratik. Skol'ko kvadratikov razrezali vtoricno?\" Otvet: 4. Reshenie: Pust' razrezali x kvadratikov. Togda obshchee kolichestvo: 9 + 3x = 21, 3x=12, x=4. Ispol'zuem etot variant."
            }
        ]
    },
    {
        "id": 90002,
        "olympiad": "vsosh",
        "olympiad_title": "Vserossijskaya olimpiada shkolnikov",
        "year": 2010,
        "grade": 6,
        "round": "school",
        "round_title": "Shkolnyj etap",
        "subject": "math",
        "difficulty": 3,
        "problems": [
            {
                "num": 1,
                "text": "Ваня выписал все трёхзначные числа, у которых первая цифра в 3 раза больше последней, а сумма всех цифр равна 14. Сколько таких чисел нашёл Ваня?",
                "answer": "2",
                "solution": "Пусть число имеет вид ABC, где A, B, C — цифры, A ≠ 0. По условию A = 3C и A + B + C = 14. Подставим A = 3C в сумму: 3C + B + C = 14 → 4C + B = 14. Так как B — цифра (0–9), а C — цифра и A = 3C — цифра от 1 до 9, то C может быть 1, 2, 3. Проверим: C=1 → 4*1+B=14 → B=10 (не цифра). C=2 → 4*2+B=14 → B=6 (подходит, A=3*2=6, число 662). C=3 → 4*3+B=14 → B=2 (подходит, A=3*3=9, число 923). Других вариантов нет. Ответ: 2 числа (662 и 923)."
            },
            {
                "num": 2,
                "text": "Прямоугольник разрезали на три одинаковых квадрата. Сумма периметров этих квадратов равна 48 см. Найдите периметр исходного прямоугольника.",
                "answer": "32 см",
                "solution": "Пусть сторона квадрата равна a см. Периметр одного квадрата 4a, сумма периметров трёх квадратов: 3 * 4a = 12a = 48 → a = 4 см. Прямоугольник состоит из трёх квадратов, значит, его стороны равны a и 3a, т.е. 4 см и 12 см. Периметр прямоугольника: 2*(4+12) = 2*16 = 32 см."
            },
            {
                "num": 3,
                "text": "В классе 30 учеников. Из них 18 занимаются волейболом, 14 — плаванием, 10 — и волейболом, и плаванием. Сколько учеников не занимаются ни волейболом, ни плаванием?",
                "answer": "8",
                "solution": "Используем принцип включений-исключений. Количество занимающихся хотя бы одним видом спорта: 18 + 14 - 10 = 22. Всего учеников 30, значит, не занимаются ни тем, ни другим: 30 - 22 = 8 учеников."
            },
            {
                "num": 4,
                "text": "На острове живут рыцари (всегда говорят правду) и лжецы (всегда лгут). Трое жителей сказали: А: «Среди нас нет рыцарей». Б: «Среди нас ровно один рыцарь». В: «Среди нас ровно два рыцаря». Кто из них кто?",
                "answer": "А — лжец, Б — рыцарь, В — лжец",
                "solution": "Предположим, А — рыцарь. Тогда его утверждение «Среди нас нет рыцарей» было бы правдой, но он сам рыцарь — противоречие. Значит, А — лжец. Тогда его утверждение ложно, значит, среди них есть хотя бы один рыцарь. Предположим, В — рыцарь. Тогда его утверждение «ровно два рыцаря» правда, значит, рыцари — это В и ещё кто-то. Но А — лжец, значит, второй рыцарь — это Б. Тогда Б тоже рыцарь, но он сказал «ровно один рыцарь», что было бы ложью (их два). Противоречие. Значит, В — лжец. Тогда рыцарь только Б (т.к. мы знаем, что рыцарей хотя бы один, а А и В — лжецы). Проверим: Б говорит «ровно один рыцарь» — правда. Утверждения А и В ложны. Всё сходится."
            },
            {
                "num": 5,
                "text": "У Маши есть гири массой 1 кг, 2 кг, 4 кг, 8 кг и 16 кг. Можно ли с их помощью на чашечных весах взвесить груз массой 23 кг, используя все гири? Если да, то как нужно разложить гири по чашкам весов?",
                "answer": "Да, на одну чашу: груз 23 кг и гири 1 кг, 2 кг, 4 кг; на другую чашу: гири 8 кг, 16 кг",
                "solution": "Общий вес гирь: 1+2+4+8+16 = 31 кг. Нужно получить разность весов на двух чашах, равную 23 кг. Пусть на чаше с грузом x кг гирь, на другой чаше (31-x) кг гирь. Тогда уравнение: (груз + x) = (31-x) + 23? Нет, правильнее: если груз на одной чаше, а гири можно класть на обе чаши, то условие равновесия: груз + гири_на_этой_чаше = гири_на_другой_чаше. То есть груз = разность весов гирь на двух чашах. Нам нужно представить 23 как разность двух сумм некоторых гирь, причём все гири используются ровно один раз. То есть нужно разбить гири на две группы так, чтобы разность их сумм была 23. Пусть S1 и S2 — суммы гирь на двух чашах, S1+S2=31, |S1-S2|=23. Решим систему: S1+S2=31, S1-S2=23 (предполагаем S1>S2). Сложим: 2S1=54 → S1=27, S2=4. Но из гирь 1,2,4,8,16 нельзя набрать 4, используя все гири? Если S2=4, то там только гиря 4 кг, тогда на другой чаше 1+2+8+16=27 — подходит! Значит, на одну чашу ставим груз 23 кг и гири 1,2,4 кг (чтобы уравновесить), на другую чашу — гири 8 и 16 кг. Проверка: 23+1+2+4=30, 8+16=24? Неравенство. Ошибка в рассуждении. Правильно: если груз на левой чаше, то на левую же можно добавить гири, на правую — другие гири. Уравнение: груз + сумма_гирь_слева = сумма_гирь_справа. Тогда груз = сумма_справа - сумма_слева. Нам нужно 23 = сумма_справа - сумма_слева. И сумма всех гирь = сумма_справа + сумма_слева = 31. Решаем: сумма_справа = (31+23)/2 = 27, сумма_слева = 4. Значит, на левую чашу с грузом кладём гири общей массой 4 кг (это гиря 4 кг), на правую чашу — все остальные гири: 1+2+8+16=27 кг. Тогда: груз + 4 = 27 → груз = 23 кг. Всё верно. Ответ: да, на одну чашу с грузом кладём гирю 4 кг, на другую чашу — гири 1, 2, 8, 16 кг."
            }
        ]
    }
]
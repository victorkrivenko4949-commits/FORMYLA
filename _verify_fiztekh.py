#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Верификация задач Физтеха: скачать PDF с olymp.mipt.ru,
распарсить, сравнить с olympiads.py, найти расхождения.

Запуск (5 потоков по умолчанию):
    python _verify_fiztekh.py [--workers 5] [--download] [--parse] [--compare]
    
Этапы:
    1. --download: скачать PDF (5 потоков)
    2. --parse: распарсить PDF -> извлечь текст
    3. --compare: сравнить с olympiads.py -> отчёт о расхождениях
    
По умолчанию делает всё по порядку.
"""

import hashlib
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ── Пути ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data" / "olympiads" / "fiztekh"
PDF_DIR = DATA_DIR / "pdf"
PARSED_DIR = DATA_DIR / "parsed"
REPORT_DIR = PROJECT_ROOT / "pipeline" / "output"

for d in [DATA_DIR, PDF_DIR, PARSED_DIR, REPORT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# ── Все 136 PDF URL из /olympiad/samples ──────────────────────────────────────
PDF_URLS = [
    "https://olymp.mipt.ru/uploads/media/default/0001/01/a2c0226b3c073a4f57bcb455e042b77b368b3cc5/Fiztekh_2022_Fizika_11_klass_1-4_varianty.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/6cf551bcee953fa98421c7e449da3a760936176b/ReshVar_11-01_11-02_11-03_11-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/7bc13f90390925162d142908d8468ead626b216b/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85_2022_%D0%A4%D0%B8%D0%B7%D0%B8%D0%BA%D0%B0_11_%D0%BA%D0%BB%D0%B0%D1%81%D1%81_5_8_%D0%B2%D0%B0%D1%80%D0%B8%D0%B0%D0%BD%D1%82%D1%8B.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/6b9af0a8dd1f19dd20eabfb89138eaa1325cb6cd/ReshVar_11-05_11-06_11-07_11-08.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/16662a5fd2d04f1f861551d1658a4de2d825496c/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85_2022_%D0%A4%D0%B8%D0%B7%D0%B8%D0%BA%D0%B0_10_%D0%BA%D0%BB%D0%B0%D1%81%D1%81_1_4_%D0%B2%D0%B0%D1%80%D0%B8%D0%B0%D0%BD%D1%82%D1%8B.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/eeb3819efe6ce4fd459a4559d4bcf62d419f6eed/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D0%B5%2010%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81,%20%D0%B1%D0%B8%D0%BB%D0%B5%D1%82%D1%8B%201-2.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/4b2b51669ff082f4ff884399cb4ae50554b33176/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D0%B5%2010%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81,%20%D0%B1%D0%B8%D0%BB%D0%B5%D1%82%D1%8B%203-4.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/74b93e84a601bbdb48f2eb2267fa9dd02e9b411c/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85_2022_%D0%A4%D0%B8%D0%B7%D0%B8%D0%BA%D0%B0_9_%D0%BA%D0%BB%D0%B0%D1%81%D1%81_1_4_%D0%B2%D0%B0%D1%80%D0%B8%D0%B0%D0%BD%D1%82%D1%8B.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/6fcadd063b7159fa766f35a71e551b6de23a22c0/%D0%9C%20Reshenie_9_klass_bilety_1-4_final.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/07118cb8a8b77d746e3055ebfb3b1a33f9577814/%D0%9C%20Razball11-01_11-02_11-03_11-04_2022_final.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/41c2b6d78d8fa973db4640346c5a33de9b08f742/%D0%A0%D0%B0%D0%B7%D0%B1%D0%B0%D0%BB%D0%BB11-05,11-06,11-07,11-08_2022%20%D1%84%D0%B8%D0%BD%D0%B0%D0%BB.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/c43dbd7559b7d2fbdd8f9134ade1ecc4e1fd8f43/%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%2010%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81,%20%D0%B2%D0%B0%D1%801-2.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/3c4ee653920d028958b7a9f339089604df0786ff/%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%2010%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81,%20%D0%B2%D0%B0%D1%80%203-4.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/a25faa020ebc683192d1ce4397dc29cf53057eed/%D0%9C%20Kriterii_9_klass_bilety_1-2_final.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/cfc29a6a07f8b119d3d19c1c2da980a5aa0f3aa7/%D0%9C%20Kriterii_9_klass_bilety_3-4_final.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/0a902259b7b7a4134baf18cf46f9f1a66a9c2f55/11%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%B2%D0%B5%D1%81%D1%82.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/7419064167043d4169bda266a28dce561d8f6193/11%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%B8%D1%81%D1%82.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/073105dc12833c5c4f328c728b017fa0e3dd2590/10%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%B2%D0%B5%D1%81%D1%82.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/5a989f725ddb642e5f6a62546869d8d790fb122c/10%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%B8%D1%81%D1%82.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/442d8b6a251638710ec9e9b8badb63a2eb603542/9%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%B2%D0%B5%D1%81%D1%82.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/5430016c53f801558d2e990b8e78879506670160/9%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%B8%D1%81%D1%82.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/55bc6cbafce5c5caae80ecaec50ab41ebb4dfe11/Phystech2022%20Solutions%201-4.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/cb6bbc46b42fa63c4215d2d9d64de3b6b988f5a4/Phystech2022%20Solutions%205-8.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/455badeccf8ff3377eb74537d9529b30b495c8ec/Phystech2022%20Solutions%209-10.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/641fa4ed8e36b9d52c95de5623a6241630b79e0c/Phystech2022%20Solutions%2011-12.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/727138182728aab40c95ce8b0914dfa48bed0183/Phystech2022%20Solutions%2013-14.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/d583e79790a43728ac19a8590b88827f34c9e75b/Phystech2022%20Solutions%2015-16.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/97a5a40a9ac229f7dcae7e74e85b81908defe246/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85-22%D0%9C%D0%B0%D1%82%D0%B5%D0%BC.%20%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%201-4.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/0a8b82c4a726f2c82221fee4924947a47629937b/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85-22%D0%9C%D0%B0%D1%82%D0%B5%D0%BC.%20%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%205-8.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/b5a6a598f2cbe91a68ee417b07ae04b9b8b15671/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85-22%D0%9C%D0%B0%D1%82%D0%B5%D0%BC.%20%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%209-10.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/27621e524334263c995ec6dd7e62d22a95600357/MIPT_2022%20Instruction%2011-12.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/61b19ac6dbbc5104fb1813bd0f1120a4d7a28538/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85-22%D0%9C%D0%B0%D1%82%D0%B5%D0%BC.%20%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%2013-14.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/9a2cecb3e36961501d0054ffc15b13c8fd8784ef/MIPT_2022%20Instruction%2015-16.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/55f599ede0580aad36bdf3236d1cd1a283248c6d/%D0%A4-11.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ccc4bc209870850ff55524efd11c5a0f0fec4b8f/%D0%9E%D1%82%D0%B2%D0%B5%D1%82%D1%8B%20%D0%A411-01-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/d8cff9fda30a6b46c3b525f540d4b027b2770565/%D0%9E%D1%82%D0%B2%D0%B5%D1%82%D1%8B%20%D0%A411-05-08.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/0efb85fb4697e1c9214035d0c2ffcc0fab6489eb/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%2011-01%20-11-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/3c2ecbff06d4abe2ca87242a705615c891dc721e/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%2011-05%20-%2011-08.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/aaf2b68c8ba06e08dbfcaa69ea0cb9bd14b0e2bb/%D0%A0%D0%B0%D0%B7%D0%B1%D0%B0%D0%BB%D0%BB%D0%BE%D0%B2%D0%BA%D0%B0%2011-01%20-%2011-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/095d1d28f2b792428edb1b2346901c02818942ae/%D0%A0%D0%B0%D0%B7%D0%B1%D0%B0%D0%BB%D0%BB%D0%BE%D0%B2%D0%BA%D0%B0%2011-05%20-%2011-08.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/b3cc713c60f6344d833a7d4fe3924eaa4ea5f3db/%D0%A4-10.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/820420d3a6271d486c13319d3e904ff00df207f6/%D0%9E%D1%82%D0%B2%D0%B5%D1%82%D1%8B%D0%A4%D0%B8%D0%B7%D0%B8%D0%BA%D0%B010-01,10-02%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%852021.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/df2f07f3008b0f0956f338f6cb2ca9b8069cfaf8/%D0%9E%D0%BB%D0%B8%D0%BC%D0%BF%D0%B8%D0%B0%D0%B4%D0%B0%20%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85,%20%D0%BE%D1%82%D0%B2%D0%B5%D1%82%D1%8B%2010-03%20%D0%B8%2010-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/fecdba715f8491bed3c43ead0992f511913f84bd/%D0%A0%D0%B5%D1%88%D0%92%D0%B0%D1%8010-01,10-02.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/dd9c1d2a010bec4c4787514abd63f2150145d5e4/%D0%A0%D0%B5%D1%88%D0%92%D0%B0%D1%8010-03,10-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/92b2c4453367aa77b275ec4b931644c2e6177458/%D0%A0%D0%B0%D0%B7%D0%B1%D0%B0%D0%BB%D0%BB10-01,10-02.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/d8acd65feab415cadc616471e4cbf480916c17ef/%D0%A0%D0%B0%D0%B7%D0%B1%D0%B0%D0%BB%D0%BB10-03,10-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/765559b2bc06385a2822f0cc68e80fe31c7558be/%D0%A4-9.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/4e4769913c0c4edabc6061de785e76792d12353b/%D0%9E%D0%BB%D0%B8%D0%BC%D0%BF%D0%B8%D0%B0%D0%B4%D0%B0%20%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85%202021%20%D0%BE%D1%82%D0%B2%D0%B5%D1%82%D1%8B%2009-01%20%D0%B8%2009-02.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/88329753b10fdb9e39f94f0fdeb12cd29356da03/%D0%9E%D0%BB%D0%B8%D0%BC%D0%BF%D0%B8%D0%B0%D0%B4%D0%B0%20%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85,%20%D0%BE%D1%82%D0%B2%D0%B5%D1%82%D1%8B%2009-03%20%D0%B8%2009-04%20(1).pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/fda0e1370a41274bdb74f74c5ec93ba1a8532183/%D0%A0%D0%B5%D1%88%D0%92%D0%B0%D1%8009-01,09-02.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/27a3aa07b2a8b6b82fb68de2796adc0e313c8e69/%D0%A0%D0%B5%D1%88%D0%92%D0%B0%D1%8009-03,09-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/931dd906c0c2330d7013bc41baf5e0d3e5fe07e3/%D0%A0%D0%B0%D0%B7%D0%B1%D0%B0%D0%BB%D0%BB09-01,09-02.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/5ec67e6403eb2e2a8e8493b4f18c735991ed2570/%D0%A0%D0%B0%D0%B7%D0%B1%D0%B0%D0%BB%D0%BB09-03,09-04.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/fcc5633cca8491465d240a31b180c229562d658c/%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%BE%D0%BF%D1%80%D0%B5%D0%B4%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%BF%D0%BE%D0%B1%D0%B5%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%D0%B9%20%D0%B8%20%D0%BF%D1%80%D0%B8%D0%B7%D1%91%D1%80%D0%BE%D0%B2%20%D0%BF%D0%BE%20%D1%84%D0%B8%D0%B7%D0%B8%D0%BA%D0%B5%20(1).pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ef66a5f643be41d0838776dffe79f0f14de88e05/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%852021-9%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20Solutions.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/dcab6857036fc0878252d36e57561520d995c730/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%852021%D0%9C%D0%B0%D1%82%D0%B5%D0%BC%D0%B0%D1%82%D0%B8%D0%BA%D0%B0%D0%98%D0%BD%D0%A1%D0%A2%D0%A0%D0%A3%D0%9A%D0%A6%D0%98%D0%AF9.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ef85f5deeac8f16139040a39bf7e39184d406e35/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%852021-10%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20Solutions.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/c5ec494cb5a6b100553c8a4f6c180b896586d87f/MIPT_2021-10%20Instruction.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/c7d688275b107b010c9d2ca55c6b1e1bc631d4e0/11Solutions.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/1dedbd0a5a5913c54150f295f48e494e45c2a1ec/%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%852021%D0%9C%D0%B0%D1%82%D0%B5%D0%BC%D0%B0%D1%82%D0%B8%D0%BA%D0%B0%D0%98%D0%BD%D0%A1%D0%A2%D0%A0%D0%A3%D0%9A%D0%A6%D0%98%D0%AF11.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/dd120e561977db5e0c47104adffef22d52a899fd/%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%BE%D0%BF%D1%80%D0%B5%D0%B4%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%BF%D0%BE%D0%B1%D0%B5%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%D0%B9%20%D0%B8%20%D0%BF%D1%80%D0%B8%D0%B7%D0%B5%D1%80%D0%BE%D0%B2%20%D0%BF%D0%BE%20%D0%BC%D0%B0%D1%82%D0%B5%D0%BC%D0%B0%D1%82%D0%B8%D0%BA%D0%B5.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/aa8a3d55783468069bd64a7fe2e907590dcd6951/9%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85%2021%20%D0%B7%D0%B0%D0%BA%D0%BB%20%D0%B1%D0%B8%D0%BE%D0%BB%D0%BE%D0%B3%D0%B8%D1%8F%20%D0%B7%D0%B0%D0%B4%D0%B0%D0%BD%D0%B8%D1%8F%20+%20%D0%BE%D1%82%D0%B2%D0%B5%D1%82%D1%8B.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/2a03f7804e4c351b94c22b0ab49611b48496c023/10%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85%2021%20%D0%B7%D0%B0%D0%BA%D0%BB%20%D0%B1%D0%B8%D0%BE%D0%BB%D0%BE%D0%B3%D0%B8%D1%8F%20%D0%B7%D0%B0%D0%B4%D0%B0%D0%BD%D0%B8%D1%8F%20+%20%D0%BE%D1%82%D0%B2%D0%B5%D1%82%D1%8B.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/12e976df2568d36dfa7dfeeb3b79068200f204f2/11%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81%20%D0%A4%D0%B8%D0%B7%D1%82%D0%B5%D1%85%2021%20%D0%B7%D0%B0%D0%BA%D0%BB%20%D0%B1%D0%B8%D0%BE%D0%BB%D0%BE%D0%B3%D0%B8%D1%8F%20%D0%B7%D0%B0%D0%B4%D0%B0%D0%BD%D0%B8%D1%8F%20+%20%D0%BE%D1%82%D0%B2%D0%B5%D1%82%D1%8B.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/d1dd84fdc0c1e9a190de299285c0bc17785a721b/%D0%9A%D0%A0%D0%98%D0%A2%D0%95%D0%A0%D0%98%D0%98%20%D0%BE%D0%BF%D1%80%D0%B5%D0%B4%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%BF%D0%BE%D0%B1%D0%B5%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%D0%B9%20%D0%B8%20%D0%BF%D1%80%D0%B8%D0%B7%D1%91%D1%80%D0%BE%D0%B2%20(3).pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/9b86b29c311652312a5123061268ae1fef8cf69b/%D0%92%D0%B0%D1%80%D0%B8%D0%B0%D0%BD%D1%82%D1%8B%2009-1-4%20%D0%B23.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/32ee869df0341288f5dccf735f4ba17e601836b3/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%BE%D1%86%D0%B5%D0%BD%D0%B8%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F%20%D0%A4%209%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/0e1062e6a0b01edf277b3aca25a00ea45c90fc66/%D0%92%D0%B0%D1%80%D0%B8%D0%B0%D0%BD%D1%82%D1%8B%2010-1-4%20%D0%B23.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/1b5f1ebd23476b764692d470b3e994a280fd8462/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%BE%D1%86%D0%B5%D0%BD%D0%B8%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F%20%D0%A4%2010%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/79dea811b60bb50f6bfbb103a86c815099ebb347/%D0%92%D0%B0%D1%80%D0%B8%D0%B0%D0%BD%D1%82%D1%8B%2011-1-8%20%D0%B23.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/39e9f624df297a21e0c800dc939f8fa977e198d6/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%BE%D1%86%D0%B5%D0%BD%D0%B8%D0%B2%D0%B0%D0%BD%D0%B8%D1%8F%2011%20%D0%BA%D0%BB%D0%B0%D1%81%D1%81.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ea3914afdab045ff66519627a3be70c7ad8d47de/%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%BE%D0%BF%D1%80%D0%B5%D0%B4%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%BF%D0%BE%D0%B1%D0%B5%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%D0%B9%20%D0%B8%20%D0%BF%D1%80%D0%B8%D0%B7%D1%91%D1%80%D0%BE%D0%B2%20%D0%A4.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/e4c9b83ad72956782708cbb3a8a2dbddf2e0e2e4/%D0%9C9.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/9d1b99611b927210755291d721dc4d45c6607e6a/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%9C9-1-2.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/5f76b2bd49bdc397457a70b2e4cc011da22f9e9f/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%9C9-9-10.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/f5b5e333e999d47ac8236ae4394f1dfaad1a4ce0/%D0%9C10.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/814ded29c7628dfaf02d5a04a227fa2a08153ccf/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%9C10-3-4.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/c4c4bb230c860c220a14b3cba1903b1c98d3492e/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%9C10-11-12.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/bc8d7fe9298eb2fa58c511bfb163811ba9d6de76/%D0%9C11.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/a34136344917ec64e53651dc260a150c961decaa/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%2011-5-8.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/88d077ca7f051165c5abf7e36334adbdffa22126/%D0%A0%D0%B5%D1%88%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%B8%20%D0%BA%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%9C11-13-16.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/8c145d08a25dc3d7f221e77cf76dff697f555b4f/%D0%9A%D1%80%D0%B8%D1%82%D0%B5%D1%80%D0%B8%D0%B8%20%D0%BE%D0%BF%D1%80%D0%B5%D0%B4%D0%B5%D0%BB%D0%B5%D0%BD%D0%B8%D1%8F%20%D0%BF%D0%BE%D0%B1%D0%B5%D0%B4%D0%B8%D1%82%D0%B5%D0%BB%D0%B5%D0%B9%20%D0%B8%20%D0%BF%D1%80%D0%B8%D0%B7%D0%B5%D1%80%D0%BE%D0%B2%20%D0%9C.pdf",
    # Hash-only PDFs (66 files) - no meaningful filename
    "https://olymp.mipt.ru/uploads/media/default/0001/01/a01a18ff0bb0aed6f0b52b1e872a4acaa4d739c3.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/39a369226bf7b66fde6fffd8a947d9186bf507a3.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/d7157784085ca695225c6c9118a23a874cc037fb.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/c6771911e2b11108626b137fb646ec634aaadf63.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/aecd5e230051d619f6df0c3dd3938c248576abc9.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/baa971caa756294f676fa6c7104ca3fb8e9904ff.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/4639ab7f502714ebbf6eebc76985f780f0816bd4.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ac26f82f4d2f109a7f4e313e2541f9d339142d16.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/838903d8463483bbce0202bf59fd280aa2bf8618.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/75569e4124dba6f48c5b47772a6e8d53d589efbd.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/405d2e1ca9e361a95768d84aa71a5c459a7a83a0.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/9c009ec53acd2eded3034e1ba88a31e960fa0a1a.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/cdaae38911338dd4e314982ef071554bdd95fa34.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/2cfe0843f10eccb97115bc9d905fa344fea9cc45.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/3aee58185e3f1299ee8ea11dba1eeecb1ca42bdc.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/42ce30a25423de59d261746dd9c1b188f712afe6.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/7064263248784519fab9b80154fa69b9a969ed85.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/c25c190f80ddb73c6822cb45a8f355d88a3ac7ba.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/b12f16eaf0deed29c4203c3b4944472562b98613.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/5042de89b5685bbcd45f98ac96bc5e1b2831a095.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/79872b3306113ef158ecdbc124485c28a0e175f9.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/c24251eb497c94f45dae84ba4b25c989ba521c76.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/565ec244de24d5c8fa6b2f52eeccf87aa5706fa9.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/e4db8ed9896bcbe777692016993e055ebbb220a8.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ddf91f22b6426a4bc9c0f80f1eafde3a09709375.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ec6d105ecaa16cff1e904d5de769cac4a63b881f.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/845f314cfe80a08c4522fb438818a9aed74e7608.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/2e56af585fc6527adeec83ba7a0714f22528a57e.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ec25ab9687bbd96c5e9ca4539518860ffc484fe5.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/804182d0672de5c1a4b33977321ae76b667df9f7.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/05fcc0e32ce49623561ce1daf6bb2124a55d2d26.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/af30a443ccf21ec9c1470ed63fda2be07cc09f5c.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/52646577bfabf82633aa2b5a63bec8bf0d5bc6b1.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/f6cdd7d600800c29a7fea9d1652e91e03f99f943.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/90d267b284e39e1f6c170d8d6614e7ecba88e3f1.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/335d67da7949f47370bb7ba2c4f78267f9048ca6.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/e931ac60390e3ae8138316972e8b0c88b04cdd62.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/e5980bde34ef0bc1987cdfcf1d2b1b6198a0ab92.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/3b6be169de5c8fb233cdcaf43678895c6cc1dded.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/35cbf31b5ce4650fe3a95ef99ab261b29d925411.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/108b2a9d8fb9c4058a9f614a5f8d141650ffb29f.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/90107fdb8bdb2ad8f06730773b8f69e0945e1f3f.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/d5ad0b044160761449a02f4d3777c1a0bdb29624.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/db28feb701b4c26a65c85f67a7d3bf098841758c.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/d3bc6b3084f7ebe58c010bca142a9e99346bae87.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/2a7b0e644196ee1f1b2be37eeed867a53d39a069.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/8b4c885ca3b467397d1c81fadb6665de5eda5006.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/12244f4e68d7935d2e57ace0e89819d40c62b5b8.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/5efe1eb2a85908933b8f8980ed307502ef442e9e.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/732e8c66b3464d29eef15ef57e1e1716516955db.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/28f242c7eda8b6eacecb1d6c0b8dc2162b1e7a02.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/ca1542cf5002724e2f037aaee6cfc542c0be32a3.pdf",
    "https://olymp.mipt.ru/uploads/media/default/0001/01/9a807b935d81b7971044f9e85199ede507c8608e.pdf",
    # Known unique URLs with unique filenames
    "https://olymp.mipt.ru/uploads/media/default/0001/01/3e5886a58c32226738dae3ee4660aebcb41cd884/%D0%91%D1%83%D0%BA%D0%BB%D0%B5%D1%82%20%D0%9E%D0%BB%D0%B8%D0%BC%D0%BF%D0%B8%D0%B0%D0%B4%D0%B0%20%D0%A4%D0%98%D0%97%D0%A2%D0%95%D0%A5%202021.pdf",
]


# ═══════════════════════════════════════════════════════════════════════════════
# Классификация PDF по имени файла
# ═══════════════════════════════════════════════════════════════════════════════

def classify_pdf(url: str) -> Dict[str, Any]:
    """Определить год, класс, предмет, тип по имени PDF-файла."""
    fname = url.split("/")[-1]
    # URL-decode
    from urllib.parse import unquote
    fname = unquote(fname)
    
    info = {
        "url": url,
        "filename": fname,
        "year": None,
        "grade": None,
        "subject": None,  # "math", "physics", "biology", "other"
        "type": None,     # "tasks", "solutions", "answers", "criteria", "instructions", "other"
        "round": None,    # "qualifying", "final"
        "confidence": 0,
    }
    
    # Extract year
    year_patterns = [
        r'20(?:0[7-9]|[1-2]\d|30)',
        r'Физтех[_ ]?20\d{2}',
        r'Fiztekh[_ ]?20\d{2}',
        r'Phystech20\d{2}',
        r'MIPT[_ ]?20\d{2}',
    ]
    for pat in year_patterns:
        m = re.search(pat, fname)
        if m:
            year_str = re.search(r'20\d{2}', m.group())
            if year_str:
                info["year"] = int(year_str.group())
                info["confidence"] += 3
                break
    
    # If no year in filename, try hash-based year (can't determine)
    
    # Extract grade
    grade_patterns = [
        (r'(?:9|09)[-_ ]?класс|9[_-]?klass|9[_-]?grade|[^1]9[_-]?\b|09[-_]', 9),
        (r'(?:10)[-_ ]?класс|10[_-]?klass|10[_-]?grade|10[-_]', 10),
        (r'(?:11)[-_ ]?класс|11[_-]?klass|11[_-]?grade|11[-_]', 11),
        (r'М9\b|M9\b|Ф-9\b|Ф9\b', 9),
        (r'М10\b|M10\b|Ф-10\b|Ф10\b', 10),
        (r'М11\b|M11\b|Ф-11\b|Ф11\b', 11),
        # Variant patterns like 09-01, 11-01 etc
        (r'\b09[-_]\d{2}\b', 9),
        (r'\b10[-_]\d{2}\b', 10),
        (r'\b11[-_]\d{2}\b', 11),
    ]
    for pat, grade in grade_patterns:
        if re.search(pat, fname):
            info["grade"] = grade
            info["confidence"] += 2
            break
    
    # If grade not found from filename patterns, check for class indicators
    if info["grade"] is None:
        if re.search(r'9\b', fname):
            info["grade"] = 9
            info["confidence"] += 1
        elif re.search(r'10\b', fname):
            info["grade"] = 10
            info["confidence"] += 1
        elif re.search(r'11\b', fname):
            info["grade"] = 11
            info["confidence"] += 1
    
    # Subject
    if re.search(r'[Фф]изик|Fizik|Fizika|Physics|phys|Ф-\d|Ф\d', fname):
        info["subject"] = "physics"
        info["confidence"] += 2
    elif re.search(r'[Мм]атем|Math|Matem|М-\d|М\d', fname):
        info["subject"] = "math"
        info["confidence"] += 2
    elif re.search(r'[Бб]иолог|Biol|Bio', fname):
        info["subject"] = "biology"
        info["confidence"] += 2
    else:
        # Check М9, М10, М11 patterns (math tasks)
        if re.search(r'[МM]\d\b', fname):
            info["subject"] = "math"
            info["confidence"] += 1
        # Check Ф-9, Ф-10, Ф-11 patterns (physics tasks)
        if re.search(r'[ФF][-]?\d{2}\b', fname):
            if info["subject"] is None:
                info["subject"] = "physics"
                info["confidence"] += 1
    
    # Type
    if re.search(r'[Рр]ешен|Solution|ReshVar|Reshen', fname):
        info["type"] = "solutions"
        info["confidence"] += 2
    elif re.search(r'[Оо]твет|Answer|Otvet', fname):
        info["type"] = "answers"
        info["confidence"] += 2
    elif re.search(r'[Кк]ритер|Razball|Разбалл|КРИТЕРИИ|criterion', fname):
        info["type"] = "criteria"
        info["confidence"] += 2
    elif re.search(r'[Ии]нструкц|Instruction|Instruk', fname):
        info["type"] = "instructions"
        info["confidence"] += 2
    elif re.search(r'[Вв]ариант|Variant|variant|zadachi|билет|bilet|ticket|task', fname):
        info["type"] = "tasks"
        info["confidence"] += 2
    elif re.search(r'вест|ист|вестник', fname):
        info["type"] = "other"
        info["confidence"] += 1
    else:
        info["type"] = "unknown"
    
    # Round detection
    if re.search(r'закл|final|заключ', fname):
        info["round"] = "final"
        info["confidence"] += 1
    elif re.search(r'отб|qualify|отбор', fname):
        info["round"] = "qualifying"
        info["confidence"] += 1
    
    return info


def get_safe_filename(url: str) -> str:
    """Создать безопасное имя файла из URL."""
    from urllib.parse import unquote
    fname = unquote(url.split("/")[-1])
    # Replace problematic characters
    fname = re.sub(r'[<>:"/\\|?*]', '_', fname)
    if len(fname) > 200:
        # Truncate but keep extension
        ext = Path(fname).suffix
        base = Path(fname).stem[:190]
        fname = base + ext
    return fname


# ═══════════════════════════════════════════════════════════════════════════════
# Этап 1: Скачивание PDF
# ═══════════════════════════════════════════════════════════════════════════════

def download_pdf(url: str, dest_dir: Path) -> Optional[Path]:
    """Скачать один PDF."""
    import requests
    
    fname = get_safe_filename(url)
    fpath = dest_dir / fname
    
    if fpath.exists() and fpath.stat().st_size > 1000:
        return fpath  # already downloaded
    
    try:
        resp = requests.get(url, timeout=60, allow_redirects=True)
        if resp.status_code == 200 and len(resp.content) > 1000:
            fpath.write_bytes(resp.content)
            return fpath
        return None
    except Exception as e:
        print(f"    [ERR] Download failed: {url[:80]}... -> {e}")
        return None


def download_all_pdfs(max_workers: int = 5) -> List[Path]:
    """Скачать все PDF в 5 потоков."""
    print(f"\n{'='*60}")
    print(f"Этап 1: Скачивание {len(PDF_URLS)} PDF (max_workers={max_workers})")
    print(f"{'='*60}")
    
    downloaded = []
    errors = 0
    skipped = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        fut_map = {pool.submit(download_pdf, url, PDF_DIR): url for url in PDF_URLS}
        done = 0
        for fut in as_completed(fut_map):
            done += 1
            url = fut_map[fut]
            try:
                result = fut.result()
                if result is None:
                    # Check if file exists already
                    fname = get_safe_filename(url)
                    fpath = PDF_DIR / fname
                    if fpath.exists() and fpath.stat().st_size > 1000:
                        skipped += 1
                    else:
                        errors += 1
                else:
                    downloaded.append(result)
            except Exception:
                errors += 1
            
            if done % 10 == 0 or done == len(PDF_URLS):
                print(f"  Progress: {done}/{len(PDF_URLS)} (OK={len(downloaded)}, skip={skipped}, err={errors})")
    
    print(f"\nРезультат: {len(downloaded)} скачано, {skipped} пропущено, {errors} ошибок")
    print(f"  Всего файлов в {PDF_DIR}: {len(list(PDF_DIR.glob('*.pdf')))}")
    return downloaded


# ═══════════════════════════════════════════════════════════════════════════════
# Этап 2: Парсинг PDF
# ═══════════════════════════════════════════════════════════════════════════════

def parse_pdf_text(fpath: Path) -> Optional[str]:
    """Извлечь текст из PDF через PyMuPDF."""
    try:
        import fitz
        doc = fitz.open(str(fpath))
        text_parts = []
        for page in doc:
            text_parts.append(page.get_text())
        doc.close()
        return "\n".join(text_parts)
    except Exception as e:
        print(f"    [ERR] Parse failed: {fpath.name}: {e}")
        return None


def parse_all_pdfs() -> Dict[str, Dict[str, Any]]:
    """Распарсить все скачанные PDF и сохранить JSON с текстом."""
    print(f"\n{'='*60}")
    print(f"Этап 2: Парсинг PDF из {PDF_DIR}")
    print(f"{'='*60}")
    
    results = {}
    pdf_files = sorted(PDF_DIR.glob("*.pdf"))
    print(f"  Найдено {len(pdf_files)} PDF файлов")
    
    for i, fpath in enumerate(pdf_files):
        text = parse_pdf_text(fpath)
        info = classify_pdf(str(fpath))
        info["filepath"] = str(fpath)
        info["filesize"] = fpath.stat().st_size
        info["text_length"] = len(text) if text else 0
        info["text_preview"] = text[:500] if text else ""
        
        results[fpath.name] = info
        if text:
            results[fpath.name]["text"] = text
        
        if (i + 1) % 10 == 0 or (i + 1) == len(pdf_files):
            print(f"  Parsed: {i+1}/{len(pdf_files)}")
    
    # Save parsed data
    parsed_path = PARSED_DIR / "parsed_pdfs.json"
    # Save without full text to keep file smaller
    save_data = {}
    for fname, info in results.items():
        d = dict(info)
        if "text" in d:
            d["text_length"] = len(d["text"])
            # Store first 200 chars as preview
            d["text_preview"] = d["text"][:200]
            del d["text"]
        save_data[fname] = d
    
    with open(parsed_path, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=1)
    print(f"  Метаданные сохранены: {parsed_path}")
    
    # Also save full text separately for comparison
    text_path = PARSED_DIR / "parsed_texts.json"
    text_data = {}
    for fname, info in results.items():
        if "text" in info:
            text_data[fname] = info["text"]
    with open(text_path, "w", encoding="utf-8") as f:
        json.dump(text_data, f, ensure_ascii=False)
    print(f"  Тексты сохранены: {text_path} ({len(text_data)} файлов)")
    
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Этап 3: Сравнение с olympiads.py
# ═══════════════════════════════════════════════════════════════════════════════

def load_olympiads_phystech() -> List[Dict[str, Any]]:
    """Загрузить phystech-данные из olympiads.py."""
    sys.path.insert(0, str(PROJECT_ROOT))
    # Clear any cached import
    for key in list(sys.modules.keys()):
        if 'olympiads' in key:
            del sys.modules[key]
    from olympiads import OLYMPIADS_DB
    return [p for p in OLYMPIADS_DB if p.get('olympiad', '') == 'phystech']


def load_parsed_texts() -> Dict[str, str]:
    """Загрузить распаршенные тексты."""
    text_path = PARSED_DIR / "parsed_texts.json"
    if text_path.exists():
        with open(text_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def normalize_text(text: str) -> str:
    """Нормализация текста для сравнения."""
    text = re.sub(r'\s+', ' ', text)
    text = text.strip()
    return text


def find_similarity(text1: str, text2: str) -> float:
    """Простое сравнение текстов через common subsequence ratio."""
    n1, n2 = normalize_text(text1), normalize_text(text2)
    if not n1 or not n2:
        return 0.0
    # Simple approach: use set overlap of words
    words1 = set(n1.lower().split())
    words2 = set(n2.lower().split())
    if not words1 or not words2:
        return 0.0
    intersection = words1 & words2
    union = words1 | words2
    return len(intersection) / len(union)


def compare_phystech_data(max_workers: int = 5) -> Dict[str, Any]:
    """Сравнить olympiads.py phystech с оригинальными PDF."""
    print(f"\n{'='*60}")
    print(f"Этап 3: Сравнение с olympiads.py")
    print(f"{'='*60}")
    
    phystech_sets = load_olympiads_phystech()
    print(f"  Загружено {len(phystech_sets)} наборов задач Физтеха из olympiads.py")
    
    # Count total problems
    total_problems = sum(len(s.get("problems", [])) for s in phystech_sets)
    print(f"  Всего задач: {total_problems}")
    
    # Load parsed PDF texts
    parsed_texts = load_parsed_texts()
    print(f"  Загружено {len(parsed_texts)} распаршенных PDF")
    
    # Classify all PDFs
    pdf_info = {}
    for fname in parsed_texts:
        url = None
        for u in PDF_URLS:
            if get_safe_filename(u) == fname:
                url = u
                break
        if url:
            pdf_info[fname] = classify_pdf(url)
            pdf_info[fname]["text"] = parsed_texts[fname]
    
    # Group PDFs by year+grade
    pdfs_by_year_grade = {}
    for fname, info in pdf_info.items():
        y = info.get("year")
        g = info.get("grade")
        if y and g:
            key = (y, g)
            pdfs_by_year_grade.setdefault(key, []).append(info)
    
    report = {
        "total_sets": len(phystech_sets),
        "total_problems": total_problems,
        "total_pdfs": len(parsed_texts),
        "classified_pdfs": len(pdf_info),
        "year_grade_coverage": {},
        "sets_with_pdfs": [],
        "sets_without_pdfs": [],
        "potential_discrepancies": [],
    }
    
    # For each phystech set, find matching PDFs and compare
    for s in phystech_sets:
        year = s["year"]
        grade = s["grade"]
        round_val = s.get("round", "")
        round_title = s.get("round_title", "")
        problems = s.get("problems", [])
        source_url = s.get("source_url", "")
        set_id = s.get("id", "")
        
        entry = {
            "id": set_id,
            "year": year,
            "grade": grade,
            "round": round_val,
            "round_title": round_title,
            "problems_count": len(problems),
            "source_url": source_url,
            "matching_pdfs": [],
            "problems": [],
        }
        
        # Find PDFs for this year+grade
        key = (year, grade)
        matching_pdfs = pdfs_by_year_grade.get(key, [])
        
        # Also check PDFs that match by year only (if grade not in filename)
        for fname, info in pdf_info.items():
            y = info.get("year")
            if y == year and key not in pdfs_by_year_grade.get((y, info.get("grade")), []):
                if info.get("grade") is None or info.get("grade") == grade:
                    matching_pdfs.append(info)
        
        # Deduplicate
        seen = set()
        unique_pdfs = []
        for p in matching_pdfs:
            if p["filename"] not in seen:
                seen.add(p["filename"])
                unique_pdfs.append(p)
        
        entry["matching_pdfs"] = [
            {
                "filename": p["filename"],
                "subject": p.get("subject"),
                "type": p.get("type"),
                "text_length": len(p.get("text", "")),
            }
            for p in unique_pdfs
        ]
        
        if matching_pdfs:
            report["sets_with_pdfs"].append(entry)
        else:
            report["sets_without_pdfs"].append(entry)
        
        # For each problem, check if its text appears in any matching PDF
        for prob in problems:
            prob_text = prob.get("text", "")
            prob_answer = prob.get("answer", "")
            prob_solution = prob.get("solution", "")
            
            prob_entry = {
                "num": prob.get("num", "?"),
                "text_length": len(prob_text),
                "has_answer": bool(prob_answer),
                "has_solution": bool(prob_solution),
                "best_match_pdf": None,
                "match_score": 0.0,
                "issue": None,
            }
            
            # Find best matching PDF
            best_score = 0.0
            best_pdf = None
            for p in unique_pdfs:
                pdf_text = p.get("text", "")
                if pdf_text and prob_text:
                    score = find_similarity(prob_text, pdf_text[:5000])
                    if score > best_score:
                        best_score = score
                        best_pdf = p["filename"]
            
            prob_entry["best_match_pdf"] = best_pdf
            prob_entry["match_score"] = round(best_score, 3)
            
            # Flag issues
            issues = []
            if best_score < 0.1 and matching_pdfs:
                issues.append(f"Текст задачи не найден в PDF (score={best_score:.3f})")
            if not prob_answer:
                issues.append("Отсутствует ответ")
            if not prob_solution:
                issues.append("Отсутствует решение")
            if prob_solution and len(prob_solution) < 20:
                issues.append(f"Решение слишком короткое ({len(prob_solution)} символов)")
            
            if prob_solution and "solution_status" in prob:
                if prob.get("solution_status") == "stub":
                    issues.append("Решение-заглушка")
            
            prob_entry["issue"] = "; ".join(issues) if issues else None
            entry["problems"].append(prob_entry)
            
            if issues:
                report["potential_discrepancies"].append({
                    "set_id": set_id,
                    "year": year,
                    "grade": grade,
                    "round": round_val,
                    "problem_num": prob.get("num", "?"),
                    "issues": issues,
                    "match_score": round(best_score, 3),
                    "text_preview": prob_text[:100],
                })
    
    # Stats
    pdf_years = set()
    for fname, info in pdf_info.items():
        if info.get("year"):
            pdf_years.add(info["year"])
    
    set_years = set(s["year"] for s in phystech_sets)
    
    report["pdf_years"] = sorted(pdf_years)
    report["set_years"] = sorted(set_years)
    report["missing_years_in_pdf"] = sorted(set_years - pdf_years)
    report["extra_years_in_pdf"] = sorted(pdf_years - set_years)
    report["sets_without_pdfs_count"] = len(report["sets_without_pdfs"])
    report["sets_with_pdfs_count"] = len(report["sets_with_pdfs"])
    report["discrepancies_count"] = len(report["potential_discrepancies"])
    
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# Генерация отчёта
# ═══════════════════════════════════════════════════════════════════════════════

def generate_report(report: Dict[str, Any]):
    """Сформировать текстовый отчёт."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"ОТЧЁТ О ВЕРИФИКАЦИИ ФИЗТЕХА")
    lines.append(f"Дата: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("=" * 70)
    lines.append("")
    
    lines.append(f"Всего наборов задач в olympiads.py (phystech): {report['total_sets']}")
    lines.append(f"Всего задач: {report['total_problems']}")
    lines.append(f"Всего PDF скачано: {report['total_pdfs']}")
    lines.append(f"Классифицировано PDF: {report['classified_pdfs']}")
    lines.append("")
    
    lines.append(f"Годы в olympiads.py: {report['set_years']}")
    lines.append(f"Годы в PDF: {report['pdf_years']}")
    lines.append(f"Годы, которых нет в PDF: {report['missing_years_in_pdf']}")
    lines.append(f"Годы, которых нет в olympiads.py: {report['extra_years_in_pdf']}")
    lines.append("")
    
    lines.append(f"Наборов с найденными PDF: {report['sets_with_pdfs_count']}")
    lines.append(f"Наборов БЕЗ PDF: {report['sets_without_pdfs_count']}")
    lines.append(f"Потенциальных расхождений: {report['discrepancies_count']}")
    lines.append("")
    
    # Sets without PDFs
    if report["sets_without_pdfs"]:
        lines.append("-" * 70)
        lines.append(f"Наборы задач БЕЗ соответствующих PDF:")
        lines.append("-" * 70)
        for s in report["sets_without_pdfs"]:
            lines.append(f"  year={s['year']} grade={s['grade']} round={s['round']:12s} "
                        f"title={s['round_title']:20s} problems={s['problems_count']:3d} "
                        f"id={s['id']}")
            if s.get("source_url"):
                lines.append(f"    source: {s['source_url']}")
        lines.append("")
    
    # Discrepancies
    if report["potential_discrepancies"]:
        lines.append("=" * 70)
        lines.append(f"ПОТЕНЦИАЛЬНЫЕ РАСХОЖДЕНИЯ ({report['discrepancies_count']}):")
        lines.append("=" * 70)
        for d in report["potential_discrepancies"]:
            lines.append(f"  [{d['year']}] grade={d['grade']} round={d['round']:12s} "
                        f"prob#{d['problem_num']} score={d['match_score']:.3f}")
            lines.append(f"    id={d['set_id']}")
            lines.append(f"    Issues: {', '.join(d['issues'])}")
            lines.append(f"    Text: {d['text_preview'][:80]}...")
            lines.append("")
    
    # Full detail for each set with PDFs
    if report["sets_with_pdfs"]:
        lines.append("=" * 70)
        lines.append(f"ДЕТАЛЬНЫЙ РАЗБОР ({len(report['sets_with_pdfs'])} наборов):")
        lines.append("=" * 70)
        for s in report["sets_with_pdfs"]:
            lines.append(f"\n  [{s['year']}] grade={s['grade']} round={s['round']:12s} "
                        f"title={s['round_title']:20s} problems={s['problems_count']}")
            lines.append(f"    id={s['id']}")
            for pdf in s["matching_pdfs"]:
                subj = pdf.get('subject') or '?'
                ptype = pdf.get('type') or '?'
                lines.append(f"    PDF: {pdf['filename'][:60]:60s} "
                            f"subj={subj:8s} "
                            f"type={ptype:12s} "
                            f"size={pdf['text_length']}")
            
            # Problems with issues
            for prob in s["problems"]:
                if prob.get("issue"):
                    lines.append(f"    [!] Задача #{prob['num']}: {prob['issue']}")
                    lines.append(f"       PDF match: {prob['best_match_pdf'][:50] if prob['best_match_pdf'] else 'NONE'} "
                                f"(score={prob['match_score']:.3f})")
    
    report_text = "\n".join(lines)
    
    # Save report
    report_path = REPORT_DIR / "fiztekh_verification_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    print(f"\nОтчёт сохранён: {report_path}")
    
    # Also save JSON
    json_path = REPORT_DIR / "fiztekh_verification_report.json"
    # Remove full text from report for JSON
    json_report = {
        "generated_at": time.strftime('%Y-%m-%d %H:%M:%S'),
        "total_sets": report["total_sets"],
        "total_problems": report["total_problems"],
        "total_pdfs": report["total_pdfs"],
        "sets_with_pdfs_count": report["sets_with_pdfs_count"],
        "sets_without_pdfs_count": report["sets_without_pdfs_count"],
        "discrepancies_count": report["discrepancies_count"],
        "missing_years_in_pdf": report["missing_years_in_pdf"],
        "extra_years_in_pdf": report["extra_years_in_pdf"],
        "sets_without_pdfs": [
            {"year": s["year"], "grade": s["grade"], "round": s["round"], 
             "problems": s["problems_count"], "id": s["id"]}
            for s in report["sets_without_pdfs"]
        ],
        "potential_discrepancies": report["potential_discrepancies"][:100],  # Limit
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    print(f"JSON-отчёт сохранён: {json_path}")
    
    return report_path, report_text


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Верификация задач Физтеха")
    parser.add_argument("--workers", type=int, default=5, help="Количество потоков (по умолч. 5)")
    parser.add_argument("--download", action="store_true", help="Только скачать PDF")
    parser.add_argument("--parse", action="store_true", help="Только распарсить PDF")
    parser.add_argument("--compare", action="store_true", help="Только сравнить")
    parser.add_argument("--all", action="store_true", help="Сделать всё (по умолчанию)")
    args = parser.parse_args()
    
    # If no specific flags, do all
    do_all = args.all or not (args.download or args.parse or args.compare)
    
    if do_all or args.download:
        download_all_pdfs(max_workers=args.workers)
    
    if do_all or args.parse:
        parse_all_pdfs()
    
    if do_all or args.compare:
        report = compare_phystech_data(max_workers=args.workers)
        generate_report(report)
        
        print(f"\n{'='*70}")
        print(f"ИТОГО:")
        print(f"  Наборов задач: {report['total_sets']} ({report['total_problems']} задач)")
        print(f"  PDF скачано: {report['total_pdfs']}")
        print(f"  Наборов с PDF: {report['sets_with_pdfs_count']}")
        print(f"  Наборов без PDF: {report['sets_without_pdfs_count']}")
        print(f"  Расхождений: {report['discrepancies_count']}")
        print(f"{'='*70}")

if __name__ == "__main__":
    main()

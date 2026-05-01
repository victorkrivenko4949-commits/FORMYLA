# -*- coding: utf-8 -*-
"""
Stage 3: Проверка уникальности задачи (без LLM, через web-поиск).
"""
import logging
import re
from typing import List, Optional
from urllib.parse import urlparse
from .types import RewrittenTask
from .uniqueness_search import SearchResult

logger = logging.getLogger(__name__)

FORBIDDEN_DOMAINS = {
    'problems.ru', 'olimpiada.ru', 'matol.ru',
    'mccme.ru', 'math.ru', 'vos.olimpiada.ru',
    'turgor.ru', 'mathus.ru', 'ashap.info',
    'formulo.org', 'artofproblemsolving.com',
    'imomath.com', 'kvant.mccme.ru',
    'problems.olimpiada.ru', 'omoskva.ru',
    'alexlarin.net', 'matematikalegko.ru',
}

MAX_QUERIES_PER_CHECK = 3
MIN_PHRASE_WORDS = 5
MAX_PHRASE_WORDS = 10


class Stage3Uniqueness:
    """Проверяет что задача не гуглится в олимпиадных архивах."""

    def __init__(self, search_backend=None):
        """
        Args:
            search_backend: объект с методом search(query, num_results) -> list[SearchResult].
                            Если None — проверка пропускается (возвращает True).
        """
        self.search = search_backend

    def is_unique(self, rewritten: RewrittenTask) -> bool:
        """
        Проверяет уникальность задачи через веб-поиск.

        True — задачи нет в архивах (уникальна).
        False — нашли совпадение в олимпиадном домене.

        При ошибках сети/API → возвращает True (не блокируем генерацию).
        """
        if self.search is None:
            logger.warning(
                "No search backend configured, skipping uniqueness check"
            )
            return True

        phrases = self._extract_signature_phrases(rewritten.rewritten_text)
        if not phrases:
            logger.warning("Could not extract signature phrases")
            return True

        for phrase in phrases[:MAX_QUERIES_PER_CHECK]:
            query = f'"{phrase}"'
            try:
                results = self.search.search(query, num_results=5)
            except Exception as e:
                logger.warning(f"Search error for '{phrase}': {e}")
                continue

            hit = self._find_forbidden_domain_hit(results)
            if hit:
                logger.info(
                    f"Non-unique: found '{phrase}' on {hit.url}"
                )
                return False

        logger.info(
            f"Task passed uniqueness check ({len(phrases)} phrases searched)"
        )
        return True

    def _extract_signature_phrases(self, text: str) -> List[str]:
        """
        Выбирает до 3 характерных фраз из текста задачи.

        Эвристика: режем текст на предложения, в каждом
        берём «центральное» окно из 5-10 слов, пропуская
        слишком общие начала («Докажите, что», «Найдите»).
        """
        sentences = re.split(r'(?<=[.!?])\s+', text.strip())
        phrases = []

        for sent in sentences:
            words = re.findall(r'\S+', sent)
            if len(words) < MIN_PHRASE_WORDS:
                continue

            # Пропускаем общие начала
            start = 0
            common_starts = {
                'докажите', 'найдите', 'пусть', 'дано',
                'известно', 'рассмотрим', 'в', 'на', 'что',
                'для', 'если', 'при', 'определите',
            }
            while (start < len(words)
                   and words[start].lower().strip(',.') in common_starts):
                start += 1

            window_size = min(MAX_PHRASE_WORDS, len(words) - start)
            if window_size < MIN_PHRASE_WORDS:
                continue

            phrase = ' '.join(words[start:start + window_size])
            phrase = phrase.rstrip('.,;:')
            phrases.append(phrase)

        return phrases

    def _find_forbidden_domain_hit(
        self, results: List[SearchResult]
    ) -> Optional[SearchResult]:
        """Ищет результат из запрещённого домена (олимпиадный архив)."""
        for r in results:
            if not r.url:
                continue
            try:
                domain = urlparse(r.url).netloc.lower()
                domain = domain.replace('www.', '')
            except Exception:
                continue

            # Точное совпадение
            if domain in FORBIDDEN_DOMAINS:
                return r
            # Поддомен запрещённого домена
            for forbidden in FORBIDDEN_DOMAINS:
                if domain.endswith('.' + forbidden):
                    return r

        return None

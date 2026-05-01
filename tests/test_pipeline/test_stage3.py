# -*- coding: utf-8 -*-
"""
Tests for Stage 3: Uniqueness check.
"""
import pytest
from unittest.mock import MagicMock
from services.pipeline.stage3_uniqueness import Stage3Uniqueness
from services.pipeline.uniqueness_search import SearchResult
from services.pipeline.types import RewrittenTask, FoundTask


@pytest.fixture
def sample_rewritten():
    """Переписанная задача для тестов Stage 3."""
    found = FoundTask(
        olympiad="ВсОШ",
        year=2019,
        stage="regional",
        grade=9,
        problem_number=3,
        topic="неравенства",
        difficulty="medium",
        original_text="оригинал задачи для тестирования",
        confidence=0.9,
    )
    return RewrittenTask(
        original=found,
        rewritten_text=(
            "Пусть x, y, z положительные числа с суммой 2. "
            "Найдите наибольшее m такое что выполняется "
            "неравенство корней от дробей xyz в знаменателях не менее m."
        ),
        changes=["сумма 1→2", "a→x", "доб xy"],
        method_preserved="Коши",
        difficulty_same=True,
    )


class TestStage3Uniqueness:
    """Тесты для Stage3Uniqueness."""

    def test_no_backend_returns_true(self, sample_rewritten):
        """Без бэкенда поиска → считаем уникальной."""
        s3 = Stage3Uniqueness(search_backend=None)
        assert s3.is_unique(sample_rewritten) is True

    def test_no_results_is_unique(self, sample_rewritten):
        """Поиск не нашёл ничего → уникальна."""
        backend = MagicMock()
        backend.search.return_value = []
        s3 = Stage3Uniqueness(backend)
        assert s3.is_unique(sample_rewritten) is True

    def test_hit_on_problems_ru_not_unique(self, sample_rewritten):
        """Совпадение на problems.ru → не уникальна."""
        backend = MagicMock()
        backend.search.return_value = [
            SearchResult(
                url="https://problems.ru/view.php?id=42",
                title="Задача",
                snippet="...",
            )
        ]
        s3 = Stage3Uniqueness(backend)
        assert s3.is_unique(sample_rewritten) is False

    def test_hit_on_random_blog_is_unique(self, sample_rewritten):
        """Совпадение на случайном блоге → уникальна (не олимпиадный архив)."""
        backend = MagicMock()
        backend.search.return_value = [
            SearchResult(
                url="https://some-random-blog.com/post/1",
                title="Блог",
                snippet="...",
            )
        ]
        s3 = Stage3Uniqueness(backend)
        assert s3.is_unique(sample_rewritten) is True

    def test_subdomain_of_forbidden_not_unique(self, sample_rewritten):
        """Поддомен запрещённого домена → не уникальна."""
        backend = MagicMock()
        backend.search.return_value = [
            SearchResult(
                url="https://archive.problems.ru/task/999",
                title="",
                snippet="",
            )
        ]
        s3 = Stage3Uniqueness(backend)
        assert s3.is_unique(sample_rewritten) is False

    def test_search_exception_continues(self, sample_rewritten):
        """Ошибка поиска → пропускаем фразу, продолжаем."""
        backend = MagicMock()
        backend.search.side_effect = [
            Exception("rate limit"),
            [],
            [],
        ]
        s3 = Stage3Uniqueness(backend)
        assert s3.is_unique(sample_rewritten) is True

    def test_extract_phrases_skips_common_starts(self):
        """Фразы не должны начинаться с общих слов (Докажите, Найдите)."""
        s3 = Stage3Uniqueness()
        phrases = s3._extract_signature_phrases(
            "Докажите, что для любых положительных чисел x, y, z "
            "с суммой 2 выполняется неравенство корней."
        )
        assert len(phrases) >= 1
        # Первая фраза не должна начинаться с "Докажите"
        assert not phrases[0].lower().startswith("докажите")

    def test_extract_phrases_from_short_text_returns_empty(self):
        """Слишком короткий текст → пустой список фраз."""
        s3 = Stage3Uniqueness()
        phrases = s3._extract_signature_phrases("Найдите x.")
        assert phrases == []

    def test_uses_up_to_max_queries(self, sample_rewritten):
        """Не больше 3 запросов к поисковику."""
        backend = MagicMock()
        backend.search.return_value = []
        s3 = Stage3Uniqueness(backend)
        s3.is_unique(sample_rewritten)
        assert backend.search.call_count <= 3

    def test_stops_early_on_hit(self, sample_rewritten):
        """После первого hit не делаем больше запросов."""
        backend = MagicMock()
        backend.search.return_value = [
            SearchResult(
                url="https://problems.ru/x",
                title="",
                snippet="",
            )
        ]
        s3 = Stage3Uniqueness(backend)
        s3.is_unique(sample_rewritten)
        assert backend.search.call_count == 1

    def test_queries_wrapped_in_quotes(self, sample_rewritten):
        """Запросы должны быть обёрнуты в кавычки для точного поиска."""
        backend = MagicMock()
        backend.search.return_value = []
        s3 = Stage3Uniqueness(backend)
        s3.is_unique(sample_rewritten)
        for call in backend.search.call_args_list:
            query = call.args[0] if call.args else call.kwargs.get('query', '')
            assert query.startswith('"') and query.endswith('"'), (
                f"Query not wrapped in quotes: {query}"
            )

    def test_forbidden_domain_www_prefix(self, sample_rewritten):
        """www.mccme.ru → mccme.ru → запрещённый домен."""
        backend = MagicMock()
        backend.search.return_value = [
            SearchResult(
                url="https://www.mccme.ru/page",
                title="",
                snippet="",
            )
        ]
        s3 = Stage3Uniqueness(backend)
        assert s3.is_unique(sample_rewritten) is False

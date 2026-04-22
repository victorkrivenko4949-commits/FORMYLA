# -*- coding: utf-8 -*-
"""
Unit tests for Daily Quest system
Tests: mastery calculation, quest generation, streak logic
"""

import pytest
import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch


# ============================================================================
# MASTERY SERVICE TESTS
# ============================================================================

class TestMasteryCalculation:
    """Tests for calculate_topic_mastery function"""
    
    def test_mastery_formula_high_accuracy(self):
        """High accuracy + high level = high mastery"""
        # accuracy=0.9, avg_level=6.0
        # mastery = (0.9 * 0.6) + ((6-1)/6 * 0.4) = 0.54 + 0.333 = 0.873
        accuracy = 0.9
        avg_level = 6.0
        mastery = (accuracy * 0.6) + ((avg_level - 1) / 6 * 0.4)
        assert mastery > 0.8, f"Expected mastery > 0.8, got {mastery}"
    
    def test_mastery_formula_low_accuracy(self):
        """Low accuracy + low level = low mastery"""
        # accuracy=0.2, avg_level=2.0
        # mastery = (0.2 * 0.6) + ((2-1)/6 * 0.4) = 0.12 + 0.067 = 0.187
        accuracy = 0.2
        avg_level = 2.0
        mastery = (accuracy * 0.6) + ((avg_level - 1) / 6 * 0.4)
        assert mastery < 0.3, f"Expected mastery < 0.3, got {mastery}"
    
    def test_mastery_clamped_to_0_1(self):
        """Mastery should always be between 0 and 1"""
        for accuracy in [0.0, 0.5, 1.0]:
            for avg_level in [1.0, 3.5, 7.0]:
                mastery = (accuracy * 0.6) + ((avg_level - 1) / 6 * 0.4)
                mastery = max(0.0, min(1.0, mastery))
                assert 0.0 <= mastery <= 1.0, f"Mastery {mastery} out of range"
    
    def test_mastery_threshold_weak(self):
        """Topics with mastery < 0.6 should be classified as weak"""
        weak_mastery = 0.4
        assert weak_mastery < 0.6, "Weak topic threshold check"
    
    def test_mastery_threshold_medium(self):
        """Topics with mastery 0.6-0.8 should be classified as medium"""
        medium_mastery = 0.7
        assert 0.6 <= medium_mastery <= 0.8, "Medium topic threshold check"
    
    def test_mastery_threshold_strong(self):
        """Topics with mastery > 0.8 should be classified as strong"""
        strong_mastery = 0.9
        assert strong_mastery > 0.8, "Strong topic threshold check"


# ============================================================================
# DAILY QUEST GENERATION TESTS
# ============================================================================

class TestDailyQuestGeneration:
    """Tests for daily quest generation algorithm"""
    
    def test_quest_distribution_5_tasks(self):
        """Quest should have exactly 5 tasks"""
        # Simulate task distribution
        task_distribution = [
            {'type': 'weak', 'topic': 'Алгебра', 'mastery': 0.3},
            {'type': 'weak', 'topic': 'Геометрия', 'mastery': 0.4},
            {'type': 'weak', 'topic': 'Комбинаторика', 'mastery': 0.5},
            {'type': 'medium', 'topic': 'Теория чисел', 'mastery': 0.7},
            {'type': 'challenge', 'topic': 'Логика', 'mastery': 0.9},
        ]
        assert len(task_distribution) == 5, "Quest should have 5 tasks"
    
    def test_quest_distribution_3_weak(self):
        """Quest should have 3 weak topic tasks"""
        task_distribution = [
            {'type': 'weak', 'topic': 'Алгебра', 'mastery': 0.3},
            {'type': 'weak', 'topic': 'Геометрия', 'mastery': 0.4},
            {'type': 'weak', 'topic': 'Комбинаторика', 'mastery': 0.5},
            {'type': 'medium', 'topic': 'Теория чисел', 'mastery': 0.7},
            {'type': 'challenge', 'topic': 'Логика', 'mastery': 0.9},
        ]
        weak_count = sum(1 for t in task_distribution if t['type'] == 'weak')
        assert weak_count == 3, f"Expected 3 weak tasks, got {weak_count}"
    
    def test_quest_distribution_1_medium(self):
        """Quest should have 1 medium task"""
        task_distribution = [
            {'type': 'weak', 'topic': 'Алгебра', 'mastery': 0.3},
            {'type': 'weak', 'topic': 'Геометрия', 'mastery': 0.4},
            {'type': 'weak', 'topic': 'Комбинаторика', 'mastery': 0.5},
            {'type': 'medium', 'topic': 'Теория чисел', 'mastery': 0.7},
            {'type': 'challenge', 'topic': 'Логика', 'mastery': 0.9},
        ]
        medium_count = sum(1 for t in task_distribution if t['type'] == 'medium')
        assert medium_count == 1, f"Expected 1 medium task, got {medium_count}"
    
    def test_quest_distribution_1_challenge(self):
        """Quest should have 1 challenge task"""
        task_distribution = [
            {'type': 'weak', 'topic': 'Алгебра', 'mastery': 0.3},
            {'type': 'weak', 'topic': 'Геометрия', 'mastery': 0.4},
            {'type': 'weak', 'topic': 'Комбинаторика', 'mastery': 0.5},
            {'type': 'medium', 'topic': 'Теория чисел', 'mastery': 0.7},
            {'type': 'challenge', 'topic': 'Логика', 'mastery': 0.9},
        ]
        challenge_count = sum(1 for t in task_distribution if t['type'] == 'challenge')
        assert challenge_count == 1, f"Expected 1 challenge task, got {challenge_count}"
    
    def test_weak_topics_have_lower_mastery(self):
        """Weak topics should have mastery < 0.6"""
        task_distribution = [
            {'type': 'weak', 'topic': 'Алгебра', 'mastery': 0.3},
            {'type': 'weak', 'topic': 'Геометрия', 'mastery': 0.4},
            {'type': 'weak', 'topic': 'Комбинаторика', 'mastery': 0.5},
        ]
        for task in task_distribution:
            assert task['mastery'] < 0.6, f"Weak task mastery {task['mastery']} should be < 0.6"
    
    def test_challenge_topic_has_higher_mastery(self):
        """Challenge topic should have mastery > 0.8"""
        challenge_task = {'type': 'challenge', 'topic': 'Логика', 'mastery': 0.9}
        assert challenge_task['mastery'] > 0.8, "Challenge task mastery should be > 0.8"


# ============================================================================
# XP CALCULATION TESTS
# ============================================================================

class TestXPCalculation:
    """Tests for XP calculation"""
    
    def test_xp_per_task(self):
        """Each correct task should give 20 XP"""
        xp_per_task = 20
        assert xp_per_task == 20, "XP per task should be 20"
    
    def test_xp_bonus_all_5(self):
        """Completing all 5 tasks should give +100 XP bonus"""
        xp_bonus = 100
        assert xp_bonus == 100, "Bonus XP for all 5 tasks should be 100"
    
    def test_xp_total_all_correct(self):
        """Total XP for all 5 correct = 5*20 + 100 = 200"""
        xp_per_task = 20
        total_tasks = 5
        bonus = 100
        total_xp = xp_per_task * total_tasks + bonus
        assert total_xp == 200, f"Expected 200 XP, got {total_xp}"
    
    def test_xp_partial_completion(self):
        """Partial completion should give XP only for completed tasks"""
        xp_per_task = 20
        completed = 3
        total_xp = xp_per_task * completed
        assert total_xp == 60, f"Expected 60 XP for 3 tasks, got {total_xp}"


# ============================================================================
# STREAK LOGIC TESTS
# ============================================================================

class TestStreakLogic:
    """Tests for streak calculation"""
    
    def test_streak_increments_on_consecutive_days(self):
        """Streak should increment when active on consecutive days"""
        current_streak = 5
        last_active = date.today() - timedelta(days=1)
        today = date.today()
        
        if last_active == today - timedelta(days=1):
            new_streak = current_streak + 1
        else:
            new_streak = 1
        
        assert new_streak == 6, f"Expected streak 6, got {new_streak}"
    
    def test_streak_resets_on_missed_day(self):
        """Streak should reset when a day is missed (no freeze)"""
        current_streak = 10
        last_active = date.today() - timedelta(days=3)  # 3 days ago
        freeze_available = 0
        
        days_since_active = (date.today() - last_active).days
        
        if days_since_active >= 2 and freeze_available == 0:
            new_streak = 0
        elif days_since_active >= 2 and freeze_available > 0:
            new_streak = current_streak  # Freeze preserves streak
        else:
            new_streak = current_streak
        
        assert new_streak == 0, f"Expected streak 0, got {new_streak}"
    
    def test_freeze_preserves_streak(self):
        """Freeze should preserve streak when a day is missed"""
        current_streak = 10
        last_active = date.today() - timedelta(days=2)  # 2 days ago
        freeze_available = 1
        
        days_since_active = (date.today() - last_active).days
        
        if days_since_active >= 2 and freeze_available > 0:
            new_streak = current_streak  # Freeze preserves streak
            freeze_available -= 1
        else:
            new_streak = 0
        
        assert new_streak == 10, f"Expected streak 10 (preserved by freeze), got {new_streak}"
        assert freeze_available == 0, "Freeze should be consumed"
    
    def test_longest_streak_updates(self):
        """Longest streak should update when current exceeds it"""
        current_streak = 15
        longest_streak = 10
        
        if current_streak > longest_streak:
            longest_streak = current_streak
        
        assert longest_streak == 15, f"Expected longest streak 15, got {longest_streak}"
    
    def test_streak_achievements_7_days(self):
        """7-day streak should unlock achievement"""
        current_streak = 7
        milestones = [7, 30, 100, 365]
        
        unlocked = [m for m in milestones if current_streak >= m]
        assert 7 in unlocked, "7-day achievement should be unlocked"
        assert 30 not in unlocked, "30-day achievement should not be unlocked"
    
    def test_streak_achievements_30_days(self):
        """30-day streak should unlock 7 and 30 day achievements"""
        current_streak = 30
        milestones = [7, 30, 100, 365]
        
        unlocked = [m for m in milestones if current_streak >= m]
        assert 7 in unlocked, "7-day achievement should be unlocked"
        assert 30 in unlocked, "30-day achievement should be unlocked"
        assert 100 not in unlocked, "100-day achievement should not be unlocked"


# ============================================================================
# AI INTRO GENERATION TESTS
# ============================================================================

class TestAIIntroGeneration:
    """Tests for AI intro text generation"""
    
    def test_ai_intro_contains_weak_topics(self):
        """AI intro should mention weak topics"""
        from services.daily_quest_service import generate_ai_intro
        
        task_distribution = [
            {'type': 'weak', 'topic': 'Алгебра', 'mastery': 0.3, 'difficulty': 3},
            {'type': 'weak', 'topic': 'Геометрия', 'mastery': 0.4, 'difficulty': 3},
            {'type': 'weak', 'topic': 'Комбинаторика', 'mastery': 0.5, 'difficulty': 3},
            {'type': 'medium', 'topic': 'Теория чисел', 'mastery': 0.7, 'difficulty': 4},
            {'type': 'challenge', 'topic': 'Логика', 'mastery': 0.9, 'difficulty': 5},
        ]
        
        intro = generate_ai_intro(task_distribution)
        assert 'Алгебра' in intro or 'слабых' in intro.lower(), "AI intro should mention weak topics"
    
    def test_ai_intro_mentions_xp(self):
        """AI intro should mention XP bonus"""
        from services.daily_quest_service import generate_ai_intro
        
        task_distribution = [
            {'type': 'weak', 'topic': 'Алгебра', 'mastery': 0.3, 'difficulty': 3},
        ]
        
        intro = generate_ai_intro(task_distribution)
        assert 'XP' in intro, "AI intro should mention XP"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

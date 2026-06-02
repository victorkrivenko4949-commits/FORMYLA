# -*- coding: utf-8 -*-
"""
Adaptive Testing Service for FORMYLA
Implements intelligent task selection based on user performance
"""

import random
import math
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def get_olympiad_status(ability_level: float) -> Dict[str, str]:
    """
    Конвертирует числовой уровень способностей в олимпиадный статус.
    
    Args:
        ability_level: Уровень способностей (1.0-8.0)
        
    Returns:
        Dict с ключами 'status', 'color', 'next_status', 'description'
    """
    if ability_level < 2.5:
        return {
            'status': 'Базовый уровень',
            'color': '#94a3b8',  # серый
            'next_status': 'Участник школьного этапа',
            'description': 'Вы только начинаете свой путь в олимпиадной математике'
        }
    elif ability_level < 3.5:
        return {
            'status': 'Участник школьного этапа',
            'color': '#cd7f32',  # бронзовый
            'next_status': 'Уверенный муниципал',
            'description': 'Вы готовы к школьному этапу олимпиад'
        }
    elif ability_level < 4.5:
        return {
            'status': 'Уверенный муниципал',
            'color': '#c0c0c0',  # серебряный
            'next_status': 'Призер перечневых олимпиад',
            'description': 'Вы можете успешно выступать на муниципальном этапе'
        }
    elif ability_level < 5.5:
        return {
            'status': 'Призер перечневых олимпиад',
            'color': '#ffd700',  # золотой
            'next_status': 'Победитель ВсОШ',
            'description': 'Вы готовы к региональному этапу и перечневым олимпиадам'
        }
    else:
        return {
            'status': 'Победитель ВсОШ (Уровень Бога)',
            'color': '#8b5cf6',  # фиолетовый/неон
            'next_status': None,
            'description': 'Вы достигли высшего уровня олимпиадной математики!'
        }


class AdaptiveTestEngine:
    """
    Adaptive testing engine that selects problems based on user performance.
    Uses Item Response Theory (IRT) principles for optimal difficulty adjustment.
    """
    
    def __init__(self, problems_db: List[Dict[str, Any]]):
        """
        Initialize adaptive test engine.
        
        Args:
            problems_db: List of all available problems
        """
        self.problems_db = problems_db
        self.min_difficulty = 1
        self.max_difficulty = 8
        
    def estimate_user_ability(self, history: List[Dict[str, Any]]) -> float:
        """
        Estimate user's current ability level based on their history.
        
        Args:
            history: List of previous attempts with 'difficulty' and 'is_correct' keys
            
        Returns:
            Estimated ability level (1.0 - 8.0)
        """
        if not history:
            return 3.5  # Start at medium difficulty
        
        # Calculate weighted average based on recent performance
        total_weight = 0
        weighted_sum = 0
        
        for i, attempt in enumerate(history[-10:]):  # Last 10 attempts
            difficulty = attempt.get('difficulty', 3.5)
            is_correct = attempt.get('is_correct', False)
            
            # More recent attempts have higher weight
            weight = (i + 1) / len(history[-10:])
            
            # Adjust difficulty based on correctness
            if is_correct:
                # If correct, ability is at least at this difficulty
                adjusted_difficulty = difficulty + 0.5
            else:
                # If incorrect, ability is below this difficulty
                adjusted_difficulty = difficulty - 0.5
            
            weighted_sum += adjusted_difficulty * weight
            total_weight += weight
        
        estimated_ability = weighted_sum / total_weight if total_weight > 0 else 3.5
        
        # Clamp to valid range
        return max(self.min_difficulty, min(self.max_difficulty, estimated_ability))
    
    def calculate_information_value(
        self, 
        problem_difficulty: float, 
        user_ability: float
    ) -> float:
        """
        Calculate information value of a problem for the user.
        Problems near user's ability level provide most information.
        
        Args:
            problem_difficulty: Difficulty level of the problem (1-8)
            user_ability: Estimated ability of the user (1-8)
            
        Returns:
            Information value (higher is better)
        """
        # Use normal distribution - problems near ability level are most informative
        distance = abs(problem_difficulty - user_ability)
        information = math.exp(-0.5 * (distance ** 2))
        return information
    
    def select_next_problem(
        self,
        user_ability: float,
        subject: Optional[str] = None,
        grade: Optional[int] = None,
        excluded_ids: Optional[List[int]] = None,
        topic_weights: Optional[Dict[str, float]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Select the next optimal problem for the user.
        
        Args:
            user_ability: Current estimated ability level
            subject: Filter by subject (optional)
            grade: Filter by grade (optional)
            excluded_ids: List of problem IDs to exclude
            topic_weights: Dictionary of topic weights for diversity
            
        Returns:
            Selected problem or None if no suitable problem found
        """
        excluded_ids = excluded_ids or []
        topic_weights = topic_weights or {}
        
        # Filter available problems
        candidates = []
        for problem in self.problems_db:
            # Skip excluded problems
            if problem.get('id') in excluded_ids:
                continue
            
            # Apply filters
            if subject and problem.get('subject') != subject:
                continue
            
            if grade is not None:
                problem_grade = problem.get('grade')
                # Handle grade ranges like "10-11"
                if isinstance(problem_grade, str) and '-' in problem_grade:
                    grade_range = problem_grade.split('-')
                    try:
                        min_grade = int(grade_range[0])
                        max_grade = int(grade_range[1])
                        if not (min_grade <= grade <= max_grade):
                            continue
                    except (ValueError, IndexError):
                        continue
                elif isinstance(problem_grade, int):
                    if problem_grade != grade:
                        continue
            
            candidates.append(problem)
        
        if not candidates:
            logger.warning(f"No candidates found for ability={user_ability}, subject={subject}, grade={grade}")
            return None
        
        # Calculate scores for each candidate
        scored_candidates = []
        for problem in candidates:
            difficulty = float(problem.get('level', 3.5))
            
            # Base score: information value
            info_value = self.calculate_information_value(difficulty, user_ability)
            
            # Topic diversity bonus
            topic = problem.get('subtopic', '')
            topic_bonus = 1.0 - topic_weights.get(topic, 0.0) * 0.3  # Up to 30% penalty for overused topics
            
            # Combine scores
            total_score = info_value * topic_bonus
            
            scored_candidates.append((problem, total_score))
        
        # Sort by score and add some randomness to top candidates
        scored_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Select from top 5 candidates with weighted random choice
        top_candidates = scored_candidates[:5]
        weights = [score for _, score in top_candidates]
        
        if not weights or sum(weights) == 0:
            return top_candidates[0][0] if top_candidates else None
        
        selected = random.choices(top_candidates, weights=weights, k=1)[0]
        return selected[0]
    
    def generate_adaptive_test(
        self,
        num_problems: int = 10,
        subject: Optional[str] = None,
        grade: Optional[int] = None,
        initial_ability: float = 3.5,
        user_history: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate a complete adaptive test.
        
        Args:
            num_problems: Number of problems to include
            subject: Filter by subject
            grade: Filter by grade
            initial_ability: Starting ability estimate
            user_history: Previous user performance history
            
        Returns:
            List of selected problems
        """
        user_history = user_history or []
        
        # Estimate initial ability from history
        current_ability = self.estimate_user_ability(user_history) if user_history else initial_ability
        
        selected_problems = []
        excluded_ids = []
        topic_weights = {}
        
        for i in range(num_problems):
            # Select next problem
            problem = self.select_next_problem(
                user_ability=current_ability,
                subject=subject,
                grade=grade,
                excluded_ids=excluded_ids,
                topic_weights=topic_weights
            )
            
            if not problem:
                logger.warning(f"Could not find problem {i+1}/{num_problems}")
                break
            
            selected_problems.append(problem)
            excluded_ids.append(problem.get('id'))
            
            # Update topic weights for diversity
            topic = problem.get('subtopic', '')
            topic_weights[topic] = topic_weights.get(topic, 0.0) + 1.0 / num_problems
            
            # Simulate ability adjustment (in real test, this happens after user answers)
            # For test generation, we slightly vary difficulty
            if i < num_problems - 1:
                # Gradually increase difficulty slightly
                current_ability += 0.2
                current_ability = min(self.max_difficulty, current_ability)
        
        return selected_problems
    
    def update_ability_after_answer(
        self,
        current_ability: float,
        problem_difficulty: float,
        is_correct: bool,
        confidence: float = 1.0
    ) -> float:
        """
        Update user ability estimate after they answer a problem.
        
        Args:
            current_ability: Current ability estimate
            problem_difficulty: Difficulty of the answered problem
            is_correct: Whether the answer was correct
            confidence: Confidence in the correctness (0.0-1.0)
            
        Returns:
            Updated ability estimate
        """
        # Calculate adjustment magnitude based on surprise
        surprise = abs(problem_difficulty - current_ability)
        adjustment_magnitude = 0.3 + surprise * 0.2  # Larger adjustments for surprising results
        
        if is_correct:
            # Correct answer: increase ability
            adjustment = adjustment_magnitude * confidence
            new_ability = current_ability + adjustment
        else:
            # Incorrect answer: decrease ability
            adjustment = adjustment_magnitude * confidence
            new_ability = current_ability - adjustment
        
        # Clamp to valid range
        return max(self.min_difficulty, min(self.max_difficulty, new_ability))
    
    def analyze_test_results(
        self,
        problems: List[Dict[str, Any]],
        answers: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analyze test results and provide detailed feedback.
        
        Args:
            problems: List of problems in the test
            answers: List of user answers with 'is_correct' field
            
        Returns:
            Analysis dictionary with statistics and recommendations
        """
        if not problems or not answers:
            return {
                'final_ability': 3.5,
                'total_correct': 0,
                'total_problems': 0,
                'accuracy': 0.0,
                'strengths': [],
                'weaknesses': [],
                'recommended_topics': []
            }
        
        # Calculate basic statistics
        total_correct = sum(1 for a in answers if a.get('is_correct', False))
        total_problems = len(answers)
        accuracy = total_correct / total_problems if total_problems > 0 else 0.0
        
        # Calculate final ability
        history = []
        for problem, answer in zip(problems, answers):
            history.append({
                'difficulty': float(problem.get('level', 3.5)),
                'is_correct': answer.get('is_correct', False)
            })
        
        final_ability = self.estimate_user_ability(history)
        
        # Analyze by topic
        topic_performance = {}
        for problem, answer in zip(problems, answers):
            topic = problem.get('subtopic', 'unknown')
            if topic not in topic_performance:
                topic_performance[topic] = {'correct': 0, 'total': 0}
            
            topic_performance[topic]['total'] += 1
            if answer.get('is_correct', False):
                topic_performance[topic]['correct'] += 1
        
        # Identify strengths and weaknesses
        strengths = []
        weaknesses = []
        for topic, perf in topic_performance.items():
            accuracy = perf['correct'] / perf['total'] if perf['total'] > 0 else 0
            if accuracy >= 0.7 and perf['total'] >= 2:
                strengths.append(topic)
            elif accuracy < 0.5 and perf['total'] >= 2:
                weaknesses.append(topic)
        
        # Recommend topics to study
        recommended_topics = weaknesses[:3] if weaknesses else []
        
        return {
            'final_ability': round(final_ability, 2),
            'total_correct': total_correct,
            'total_problems': total_problems,
            'accuracy': round(accuracy * 100, 1),
            'strengths': strengths,
            'weaknesses': weaknesses,
            'recommended_topics': recommended_topics,
            'topic_performance': topic_performance
        }

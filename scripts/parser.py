#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mathematical Problems Parser for FORMYLA Platform
Collects problems from open mathematical databases and classifies them using AI.

Supported sources:
- problems.ru (Задачи по математике)
- mccme.ru (Московский центр непрерывного математического образования)
"""

import os
import sys
import json
import time
import logging
import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Any
from urllib.parse import urljoin, urlparse
import re

# Fix Windows console encoding
if sys.platform == 'win32':
    import codecs
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import AI client
try:
    from ai.deepseek_client import DeepSeekClient, DeepSeekAPIError
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False
    print("⚠️  DeepSeek client not available. AI classification disabled.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
OUTPUT_FILE = "data/parsed_problems.jsonl"
CHECKPOINT_FILE = "data/parser_checkpoint.json"
REQUEST_DELAY = 1.0  # seconds between requests to be polite
MAX_PROBLEMS_PER_SOURCE = 100  # limit for testing

# Subject and subtopic mapping (from app.py)
SUBJECTS = {
    "algebra": "Алгебра",
    "geometry": "Геометрия",
    "combinatorics": "Комбинаторика",
    "number_theory": "Теория чисел",
    "movement": "Задачи на движение",
    "knights_liars": "Рыцари и лжецы"
}

SUBTOPICS = {
    "algebra": ["equations", "inequalities", "sequences", "functions", "systems"],
    "geometry": ["triangles", "circles", "areas", "quadrilaterals", "coordinate"],
    "combinatorics": ["counting", "pigeonhole", "graphs", "games"],
    "number_theory": ["divisibility", "remainders", "primes", "diophantine"],
    "knights_liars": ["classic", "conditions", "island"],
    "movement": ["uniform", "encounter", "special"],
}


class CheckpointManager:
    """Manager for saving and loading parsing progress."""
    
    def __init__(self, checkpoint_file: str = CHECKPOINT_FILE):
        self.checkpoint_file = checkpoint_file
        
    def load(self) -> Dict[str, Any]:
        """Load checkpoint data."""
        if os.path.exists(self.checkpoint_file):
            try:
                with open(self.checkpoint_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logger.info(f"Loaded checkpoint: {len(data.get('processed_urls', []))} URLs processed")
                    return data
            except Exception as e:
                logger.error(f"Failed to load checkpoint: {e}")
                return {"processed_urls": [], "total_parsed": 0}
        return {"processed_urls": [], "total_parsed": 0}
    
    def save(self, data: Dict[str, Any]):
        """Save checkpoint data."""
        try:
            os.makedirs(os.path.dirname(self.checkpoint_file), exist_ok=True)
            with open(self.checkpoint_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Checkpoint saved: {data.get('total_parsed', 0)} problems")
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")


class AIClassifier:
    """AI-based problem classifier and solution simplifier using DeepSeek."""
    
    def __init__(self):
        if not AI_AVAILABLE:
            raise RuntimeError("DeepSeek client not available")
        self.client = DeepSeekClient()
    
    def simplify_solution(self, solution_text: str) -> str:
        """
        Simplify a mathematical solution using AI.
        
        Args:
            solution_text: Original solution text
            
        Returns:
            Simplified solution or original if simplification failed
        """
        if not solution_text or len(solution_text) < 50:
            return solution_text
        
        system_prompt = """Ты опытный учитель математики, который умеет объяснять сложные вещи простым языком.
Твоя задача — переписать математическое решение так, чтобы оно было понятно школьнику."""

        user_prompt = f"""Перепиши это математическое решение максимально простым, понятным и дружелюбным языком для школьника.

Требования:
1. Убери заумные термины, замени их простыми словами
2. Объясни логику по шагам (Шаг 1, Шаг 2, Шаг 3...)
3. Сделай текст коротким и чётким (максимум 500 символов)
4. Сохрани все математические формулы и вычисления

Исходное решение:
{solution_text}

Упрощённое решение:"""

        try:
            simplified = self.client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
                max_tokens=600
            )
            
            simplified = simplified.strip()
            
            if len(simplified) > 50:
                logger.info(f"✓ Solution simplified: {len(solution_text)} -> {len(simplified)} chars")
                return simplified
            else:
                logger.warning("AI returned too short solution, using original")
                return solution_text
                
        except Exception as e:
            logger.error(f"Solution simplification error: {e}")
            return solution_text
        
    def classify_problem(self, problem_text: str) -> Optional[Dict[str, str]]:
        """
        Classify a mathematical problem using AI with STRICT subtopic validation.
        
        Args:
            problem_text: Text of the problem
            
        Returns:
            Dict with 'subject' and 'subtopic' keys, or None if classification failed
        """
        # Build COMPLETE subtopics list for prompt
        subtopics_list = []
        for subj, topics in SUBTOPICS.items():
            subtopics_list.append(f"  {subj}: {', '.join(topics)}")
        
        system_prompt = f"""Ты эксперт по классификации математических задач для школьников.

СТРОГО используй ТОЛЬКО эти предметы и подтемы:

{chr(10).join(subtopics_list)}

КРИТИЧНО:
- Выбирай ТОЛЬКО из списка выше
- НЕ придумывай свои названия
- Если задача не подходит ни под одну подтему, используй первую подтему предмета
- Верни ТОЛЬКО валидный JSON без текста

Формат ответа: {{"subject": "название_предмета", "subtopic": "название_подтемы"}}"""

        user_prompt = f"""Классифицируй задачу, используя ТОЛЬКО предметы и подтемы из списка.

Задача:
{problem_text[:500]}

JSON:"""

        try:
            response = self.client.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.1,  # Low temperature for consistent classification
                max_tokens=100
            )
            
            # Extract JSON from response
            response = response.strip()
            
            # Try to find JSON in response
            json_match = re.search(r'\{[^}]+\}', response)
            if json_match:
                response = json_match.group(0)
            
            # Parse JSON
            classification = json.loads(response)
            
            # Validate
            subject = classification.get('subject')
            subtopic = classification.get('subtopic')
            
            if subject in SUBJECTS and subtopic in SUBTOPICS.get(subject, []):
                logger.info(f"✓ Classified as {subject}/{subtopic}")
                return {"subject": subject, "subtopic": subtopic}
            else:
                logger.warning(f"Invalid classification: {classification}")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse AI response as JSON: {response[:100]}")
            return None
        except DeepSeekAPIError as e:
            logger.error(f"AI API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return None


class ProblemsRuParser:
    """Parser for problems.ru website."""
    
    def __init__(self):
        self.base_url = "https://problems.ru"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def parse_problem_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single problem page.
        
        Args:
            url: URL of the problem page
            
        Returns:
            Dict with problem data or None if parsing failed
        """
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = 'koi8-r'  # problems.ru uses KOI8-R encoding
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Check if it's an error page
            error_check = soup.find('div', class_='componentboxheader')
            if error_check and 'Ошибка' in error_check.get_text():
                logger.warning(f"Problem not found at {url}")
                return None
            
            # Extract problem number from header
            header = soup.find('div', class_='componentboxheader')
            title = ""
            if header:
                title = header.get_text(strip=True)
            
            # Helper function to extract ONLY text between h3 tags, stopping at next h3
            def extract_section(start_h3):
                """Extract ONLY text between h3 tag and next h3, excluding all tables and divs."""
                if not start_h3:
                    return ""
                
                parts = []
                for sibling in start_h3.next_siblings:
                    # STOP at next h3 (this catches "Источники и прецеденты")
                    if sibling.name == 'h3':
                        break
                    
                    # SKIP tables completely (they contain metadata)
                    if sibling.name == 'table':
                        continue
                    
                    # SKIP divs with source/detail classes
                    if sibling.name == 'div':
                        classes = sibling.get('class', [])
                        if any('source' in str(c).lower() or 'detail' in str(c).lower() for c in classes):
                            break
                    
                    # Extract ONLY from <p> tags and direct text nodes
                    if sibling.name == 'p':
                        text = sibling.get_text(strip=True, separator=' ')
                        if text:
                            parts.append(text)
                    elif isinstance(sibling, str):
                        text = sibling.strip()
                        if text and text not in ['BR', '\n', '\r\n', '']:
                            parts.append(text)
                
                result = ' '.join(parts).strip()
                # Remove any remaining "Источники" text that might have slipped through
                result = re.sub(r'Источники.*$', '', result, flags=re.DOTALL)
                return result.strip()
            
            # Extract problem text (after <h3>Условие</h3>)
            condition_h3 = soup.find('h3', string=re.compile(r'Условие'))
            problem_text = extract_section(condition_h3)
            
            if not problem_text:
                logger.warning(f"No problem text found at {url}")
                return None
            
            # Extract solution (after <h3>Решение</h3>)
            solution_h3 = soup.find('h3', string=re.compile(r'Решение'))
            solution = extract_section(solution_h3)
            
            # Extract answer (after <h3>Ответ</h3>)
            answer_h3 = soup.find('h3', string=re.compile(r'Ответ'))
            answer = extract_section(answer_h3)
            
            return {
                "source": "problems.ru",
                "url": url,
                "title": title,
                "text": problem_text,
                "answer": answer,
                "solution": solution,
            }
            
        except requests.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Parsing error for {url}: {e}")
            return None
    
    def get_problem_list_urls(self, max_pages: int = 5) -> List[str]:
        """
        Get list of problem URLs from the catalog.
        
        Args:
            max_pages: Maximum number of catalog pages to parse
            
        Returns:
            List of problem URLs
        """
        problem_urls = []
        visited_subjects = set()
        
        # Start with main subject IDs from catalog
        # 88 (Algebra 6039), 193 (Geometry 12706), 188 (Combinatorics 1024), 78 (Logic 1344)
        subject_queue = [88, 193, 188, 78, 265, 208, 214]  # Add more subjects
        
        logger.info(f"Starting deep catalog exploration...")
        
        while subject_queue and len(problem_urls) < MAX_PROBLEMS_PER_SOURCE:
            subject_id = subject_queue.pop(0)
            
            if subject_id in visited_subjects:
                continue
            
            visited_subjects.add(subject_id)
            
            try:
                subject_url = f"{self.base_url}/view_by_subject_new.php?parent={subject_id}"
                response = self.session.get(subject_url, timeout=10)
                response.encoding = 'koi8-r'
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find sub-subjects (nested categories)
                sub_links = soup.find_all('a', href=re.compile(r'view_by_subject_new\.php\?parent=\d+'))
                for link in sub_links:
                    href = link.get('href')
                    match = re.search(r'parent=(\d+)', href)
                    if match:
                        sub_id = int(match.group(1))
                        if sub_id not in visited_subjects and sub_id not in subject_queue:
                            subject_queue.append(sub_id)
                
                # Find problem links on this page
                problem_links = soup.find_all('a', href=re.compile(r'view_problem_details_new\.php\?id=\d+'))
                
                for link in problem_links:
                    href = link.get('href')
                    match = re.search(r'id=(\d+)', href)
                    if match:
                        problem_id = match.group(1)
                        problem_url = f"{self.base_url}/view_problem_details_new.php?id={problem_id}"
                        if problem_url not in problem_urls:
                            problem_urls.append(problem_url)
                            
                            if len(problem_urls) >= MAX_PROBLEMS_PER_SOURCE:
                                break
                
                logger.info(f"Subject {subject_id}: found {len(problem_links)} problems, total: {len(problem_urls)}")
                
                if len(problem_urls) >= MAX_PROBLEMS_PER_SOURCE:
                    break
                
                # Small delay between subject pages
                time.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Error exploring subject {subject_id}: {e}")
                continue
        
        logger.info(f"Explored {len(visited_subjects)} subjects, found {len(problem_urls)} problem URLs")
        return problem_urls


class MCCMEParser:
    """Parser for mccme.ru (Moscow Center for Continuous Mathematical Education)."""
    
    def __init__(self):
        self.base_url = "https://olympiads.mccme.ru"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def parse_problem_page(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Parse a single problem page from mccme.ru.
        
        Args:
            url: URL of the problem page
            
        Returns:
            Dict with problem data or None if parsing failed
        """
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract problem text (adjust selectors based on actual structure)
            problem_text = ""
            
            # Try different possible selectors
            problem_div = (soup.find('div', class_='problem') or 
                          soup.find('div', class_='task') or
                          soup.find('div', class_='problem-text'))
            
            if problem_div:
                problem_text = problem_div.get_text(strip=True, separator=' ')
            else:
                # Fallback: get main content
                main_content = soup.find('main') or soup.find('div', class_='content')
                if main_content:
                    problem_text = main_content.get_text(strip=True, separator=' ')
            
            if not problem_text:
                logger.warning(f"No problem text found at {url}")
                return None
            
            # Extract answer
            answer = ""
            answer_elem = soup.find('div', class_='answer') or soup.find('span', text=re.compile(r'Ответ:'))
            if answer_elem:
                answer = answer_elem.get_text(strip=True)
                answer = re.sub(r'^Ответ:\s*', '', answer)
            
            # Extract solution
            solution = ""
            solution_div = soup.find('div', class_='solution') or soup.find('div', class_='решение')
            if solution_div:
                solution = solution_div.get_text(strip=True, separator=' ')
            
            # Extract title
            title = ""
            title_tag = soup.find('h1') or soup.find('h2')
            if title_tag:
                title = title_tag.get_text(strip=True)
            
            return {
                "source": "mccme.ru",
                "url": url,
                "title": title,
                "text": problem_text,
                "answer": answer,
                "solution": solution,
            }
            
        except requests.RequestException as e:
            logger.error(f"Request error for {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Parsing error for {url}: {e}")
            return None
    
    def get_problem_list_urls(self, max_pages: int = 5) -> List[str]:
        """
        Get list of problem URLs from mccme.ru.
        
        Args:
            max_pages: Maximum number of pages to parse
            
        Returns:
            List of problem URLs
        """
        problem_urls = []
        
        # Parse from olympiad archives
        archive_urls = [
            f"{self.base_url}/olympiads/",
            f"{self.base_url}/problems/",
        ]
        
        for archive_url in archive_urls:
            try:
                response = self.session.get(archive_url, timeout=10)
                response.raise_for_status()
                response.encoding = 'utf-8'
                
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Find problem links (adjust based on actual structure)
                links = soup.find_all('a', href=re.compile(r'/(problem|task)/'))
                
                for link in links[:MAX_PROBLEMS_PER_SOURCE // len(archive_urls)]:
                    href = link.get('href')
                    if href:
                        full_url = urljoin(self.base_url, href)
                        if full_url not in problem_urls:
                            problem_urls.append(full_url)
                
            except Exception as e:
                logger.error(f"Error getting problem list from {archive_url}: {e}")
        
        logger.info(f"Found {len(problem_urls)} problem URLs from mccme.ru")
        return problem_urls


class MathNetParser:
    """Parser for mathnet.ru (All-Russian Mathematical Portal)."""
    
    def __init__(self):
        self.base_url = "http://www.mathnet.ru"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        
    def parse_problem_page(self, url: str) -> Optional[Dict[str, Any]]:
        """Parse a single problem from mathnet.ru."""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            response.encoding = 'utf-8'
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract problem text
            problem_text = ""
            content_div = soup.find('div', class_='content') or soup.find('div', class_='article')
            if content_div:
                problem_text = content_div.get_text(strip=True, separator=' ')
            
            if not problem_text:
                return None
            
            # Extract title
            title = ""
            title_tag = soup.find('h1')
            if title_tag:
                title = title_tag.get_text(strip=True)
            
            return {
                "source": "mathnet.ru",
                "url": url,
                "title": title,
                "text": problem_text,
                "answer": "",
                "solution": "",
            }
            
        except Exception as e:
            logger.error(f"Error parsing {url}: {e}")
            return None
    
    def get_problem_list_urls(self, max_pages: int = 5) -> List[str]:
        """Get problem URLs from mathnet.ru."""
        # This is a placeholder - actual implementation depends on site structure
        logger.info("mathnet.ru parser: placeholder implementation")
        return []


class ProblemParser:
    """Main parser orchestrator."""
    
    def __init__(self, use_ai: bool = True):
        """
        Initialize parser.
        
        Args:
            use_ai: Whether to use AI for classification
        """
        self.use_ai = use_ai and AI_AVAILABLE
        self.classifier = AIClassifier() if self.use_ai else None
        self.checkpoint_manager = CheckpointManager()
        
        # Initialize source parsers
        self.parsers = {
            "problems.ru": ProblemsRuParser(),
            "mccme.ru": MCCMEParser(),
            "mathnet.ru": MathNetParser(),
        }
        
    def classify_problem(self, problem_text: str) -> Dict[str, str]:
        """
        Classify problem using AI or fallback to default.
        
        Args:
            problem_text: Text of the problem
            
        Returns:
            Dict with 'subject' and 'subtopic'
        """
        if self.classifier:
            classification = self.classifier.classify_problem(problem_text)
            if classification:
                return classification
        
        # Fallback: default classification
        logger.warning("Using fallback classification")
        return {"subject": "algebra", "subtopic": "equations"}
    
    def parse_and_classify(self, raw_problem: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parse and classify a single problem.
        
        Args:
            raw_problem: Raw problem data from parser
            
        Returns:
            Classified problem dict or None if processing failed
        """
        if not raw_problem or not raw_problem.get('text'):
            return None
        
        # Classify using AI
        classification = self.classify_problem(raw_problem['text'])
        
        # Process solution: simplify with AI or apply fallback
        original_solution = raw_problem.get("solution", "")
        processed_solution = self._process_solution(original_solution)
        
        # Build final problem structure
        problem = {
            "source": raw_problem.get("source", "unknown"),
            "source_url": raw_problem.get("url", ""),
            "subject": classification["subject"],
            "subject_title": SUBJECTS[classification["subject"]],
            "subtopic": classification["subtopic"],
            "subtopic_title": self._get_subtopic_title(classification["subject"], classification["subtopic"]),
            "title": raw_problem.get("title", "")[:100],  # Limit title length
            "text": raw_problem["text"],
            "answer": raw_problem.get("answer", ""),
            "solution": processed_solution,
            "grade": self._estimate_grade(raw_problem["text"]),
            "difficulty": self._estimate_difficulty(raw_problem["text"]),
        }
        
        return problem
    
    def _process_solution(self, solution: str) -> str:
        """
        Process solution: simplify with AI or apply fallback.
        
        Args:
            solution: Original solution text
            
        Returns:
            Processed solution
        """
        if not solution:
            return ""
        
        # Try AI simplification
        if self.classifier:
            try:
                simplified = self.classifier.simplify_solution(solution)
                return simplified
            except Exception as e:
                logger.warning(f"AI simplification failed: {e}, using fallback")
        
        # Fallback: truncate if too long
        MAX_SOLUTION_LENGTH = 800
        if len(solution) > MAX_SOLUTION_LENGTH:
            logger.info(f"Solution too long ({len(solution)} chars), truncating to {MAX_SOLUTION_LENGTH}")
            return solution[:MAX_SOLUTION_LENGTH] + "..."
        
        return solution
    
    def _get_subtopic_title(self, subject: str, subtopic: str) -> str:
        """Get Russian title for subtopic."""
        # Import from app.py structure
        subtopic_titles = {
            "algebra": {
                "equations": "Уравнения",
                "inequalities": "Неравенства",
                "sequences": "Последовательности",
                "functions": "Функции",
                "systems": "Системы уравнений",
            },
            "geometry": {
                "triangles": "Треугольники",
                "circles": "Окружности",
                "areas": "Площади",
                "quadrilaterals": "Четырёхугольники",
                "coordinate": "Координатная геометрия",
            },
            "combinatorics": {
                "counting": "Подсчёт и перебор",
                "pigeonhole": "Принцип Дирихле",
                "graphs": "Графы и раскраски",
                "games": "Игры и стратегии",
            },
            "number_theory": {
                "divisibility": "Делимость",
                "remainders": "Остатки",
                "primes": "Простые числа",
                "diophantine": "Диофантовы уравнения",
            },
            "knights_liars": {
                "classic": "Классические задачи",
                "conditions": "Задачи с условиями",
                "island": "Задачи на острове",
            },
            "movement": {
                "uniform": "Равномерное движение",
                "encounter": "Движение навстречу и вдогонку",
                "special": "Движение по воде и эскалаторы",
            },
        }
        return subtopic_titles.get(subject, {}).get(subtopic, subtopic)
    
    def _estimate_grade(self, text: str) -> int:
        """Estimate grade level based on problem complexity."""
        # Simple heuristic: longer problems tend to be for higher grades
        length = len(text)
        if length < 200:
            return 5
        elif length < 400:
            return 7
        elif length < 600:
            return 9
        else:
            return 10
    
    def _estimate_difficulty(self, text: str) -> int:
        """Estimate difficulty level (1-10)."""
        # Simple heuristic based on text complexity
        length = len(text)
        if length < 300:
            return 3
        elif length < 500:
            return 5
        elif length < 700:
            return 7
        else:
            return 8
    
    def collect_problems(self, sources: List[str] = None, max_per_source: int = MAX_PROBLEMS_PER_SOURCE) -> int:
        """
        Collect problems from specified sources.
        
        Args:
            sources: List of source names to parse (None = all sources)
            max_per_source: Maximum problems to collect per source
            
        Returns:
            Number of problems collected
        """
        if sources is None:
            sources = list(self.parsers.keys())
        
        # Load checkpoint
        checkpoint = self.checkpoint_manager.load()
        processed_urls = set(checkpoint.get('processed_urls', []))
        total_parsed = checkpoint.get('total_parsed', 0)
        
        # Ensure output directory exists
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        
        # Open output file in append mode
        output_mode = 'a' if os.path.exists(OUTPUT_FILE) else 'w'
        
        logger.info(f"Starting collection from sources: {sources}")
        logger.info(f"Already processed: {len(processed_urls)} URLs")
        
        with open(OUTPUT_FILE, output_mode, encoding='utf-8') as outfile:
            for source_name in sources:
                if source_name not in self.parsers:
                    logger.warning(f"Unknown source: {source_name}")
                    continue
                
                parser = self.parsers[source_name]
                logger.info(f"\n{'='*70}")
                logger.info(f"Processing source: {source_name}")
                logger.info(f"{'='*70}")
                
                # Get problem URLs
                problem_urls = parser.get_problem_list_urls()
                
                # Filter out already processed URLs
                new_urls = [url for url in problem_urls if url not in processed_urls]
                logger.info(f"New URLs to process: {len(new_urls)}")
                
                # Limit per source
                new_urls = new_urls[:max_per_source]
                
                # Parse each problem
                for idx, url in enumerate(new_urls, 1):
                    logger.info(f"\n[{idx}/{len(new_urls)}] Processing: {url}")
                    
                    # Parse problem
                    raw_problem = parser.parse_problem_page(url)
                    if not raw_problem:
                        logger.warning(f"Failed to parse {url}")
                        continue
                    
                    # Classify and structure
                    classified_problem = self.parse_and_classify(raw_problem)
                    if not classified_problem:
                        logger.warning(f"Failed to classify problem from {url}")
                        continue
                    
                    # Save to JSONL
                    outfile.write(json.dumps(classified_problem, ensure_ascii=False) + '\n')
                    outfile.flush()
                    
                    # Update checkpoint
                    processed_urls.add(url)
                    total_parsed += 1
                    
                    if total_parsed % 10 == 0:
                        self.checkpoint_manager.save({
                            "processed_urls": list(processed_urls),
                            "total_parsed": total_parsed
                        })
                    
                    # Be polite - delay between requests
                    time.sleep(REQUEST_DELAY)
                
                logger.info(f"Completed {source_name}: {len(new_urls)} problems processed")
        
        # Final checkpoint save
        self.checkpoint_manager.save({
            "processed_urls": list(processed_urls),
            "total_parsed": total_parsed
        })
        
        logger.info(f"\n{'='*70}")
        logger.info(f"PARSING COMPLETE")
        logger.info(f"Total problems collected: {total_parsed}")
        logger.info(f"Output file: {OUTPUT_FILE}")
        logger.info(f"{'='*70}")
        
        return total_parsed


def main():
    """Main entry point."""
    import argparse
    
    parser_cli = argparse.ArgumentParser(
        description="Parse mathematical problems from open sources"
    )
    parser_cli.add_argument(
        '--sources',
        nargs='+',
        choices=['problems.ru', 'mccme.ru', 'mathnet.ru', 'all'],
        default=['all'],
        help='Sources to parse (default: all)'
    )
    parser_cli.add_argument(
        '--max-per-source',
        type=int,
        default=MAX_PROBLEMS_PER_SOURCE,
        help=f'Maximum problems per source (default: {MAX_PROBLEMS_PER_SOURCE})'
    )
    parser_cli.add_argument(
        '--no-ai',
        action='store_true',
        help='Disable AI classification (use fallback)'
    )
    parser_cli.add_argument(
        '--test',
        action='store_true',
        help='Test mode: parse only 5 problems'
    )
    
    args = parser_cli.parse_args()
    
    # Handle 'all' sources
    if 'all' in args.sources:
        sources = ['problems.ru', 'mccme.ru', 'mathnet.ru']
    else:
        sources = args.sources
    
    # Test mode
    if args.test:
        args.max_per_source = 5
        logger.info("🧪 TEST MODE: Parsing only 5 problems per source")
    
    # Check AI availability
    if not AI_AVAILABLE:
        logger.warning("AI classification not available - using fallback")
        args.no_ai = True
    
    # Initialize parser
    try:
        problem_parser = ProblemParser(use_ai=not args.no_ai)
    except Exception as e:
        logger.error(f"Failed to initialize parser: {e}")
        sys.exit(1)
    
    # Collect problems
    try:
        total = problem_parser.collect_problems(
            sources=sources,
            max_per_source=args.max_per_source
        )
        
        print(f"\n✅ Successfully collected {total} problems")
        print(f"📁 Output: {OUTPUT_FILE}")
        print(f"\nNext steps:")
        print(f"  1. Review parsed problems in {OUTPUT_FILE}")
        print(f"  2. Run migrator to add to database: python scripts/migrator.py --source parsed")
        
    except KeyboardInterrupt:
        logger.info("\n⚠️  Parsing interrupted by user")
        print("\nProgress saved in checkpoint. Run again to continue.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Parsing failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

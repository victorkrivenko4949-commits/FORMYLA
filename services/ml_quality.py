# -*- coding: utf-8 -*-
"""
ML Dataset quality scoring for TaskSolution pairs.

Quality score (0.0 - 1.0) determines if a (photo, LaTeX) pair
is suitable for training a handwriting recognition model.
"""
import logging

logger = logging.getLogger(__name__)


def calculate_score(solution, photo_bytes=None):
    """
    Calculate quality score for a TaskSolution record.

    Scoring breakdown:
      +0.3 if was_corrected (user verified/corrected the OCR output)
      +0.3 if task has reference_solution in DB (easier to validate)
      +0.2 if photo resolution >= 800x600
      +0.2 if OCR confidence >= 0.8 OR user corrected

    Args:
        solution: TaskSolution model instance
        photo_bytes: optional raw photo bytes (for dimension check)

    Returns:
        float: quality score 0.0 - 1.0
    """
    score = 0.0

    # +0.3: user corrected OCR (means they verified the final LaTeX)
    if solution.was_corrected:
        score += 0.3

    # +0.3: task has reference solution (ground truth available)
    if solution.task and solution.task.solution:
        ref = (solution.task.solution or '').strip()
        if len(ref) > 10:  # non-trivial solution
            score += 0.3

    # +0.2: photo resolution >= 800x600
    if photo_bytes:
        try:
            from services.storage import get_photo_dimensions
            w, h = get_photo_dimensions(photo_bytes)
            if w >= 800 and h >= 600:
                score += 0.2
            elif w >= 400 and h >= 300:
                score += 0.1  # partial credit for medium resolution
        except Exception:
            pass
    elif solution.original_photo_url:
        # If we don't have bytes but have a URL, give partial credit
        score += 0.1

    # +0.2: OCR confidence or user correction
    if solution.was_corrected:
        # User corrected = high confidence in final result
        score += 0.2
    elif solution.ocr_raw_output:
        # Try to extract confidence from OCR output
        confidence = _extract_ocr_confidence(solution.ocr_raw_output)
        if confidence >= 0.8:
            score += 0.2
        elif confidence >= 0.5:
            score += 0.1

    return min(1.0, round(score, 2))


def _extract_ocr_confidence(ocr_output):
    """
    Extract confidence score from OCR output.
    Supports Mathpix JSON format and plain text with confidence markers.
    """
    if not ocr_output:
        return 0.0

    try:
        import json
        data = json.loads(ocr_output)
        # Mathpix format
        if 'confidence' in data:
            return float(data['confidence'])
        if 'confidence_rate' in data:
            return float(data['confidence_rate'])
        # GPT-4o format (custom)
        if 'ocr_confidence' in data:
            return float(data['ocr_confidence'])
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    return 0.0


def update_quality_score(solution, photo_bytes=None):
    """
    Calculate and persist quality score on a TaskSolution.

    Args:
        solution: TaskSolution model instance
        photo_bytes: optional raw photo bytes

    Returns:
        float: the calculated score
    """
    score = calculate_score(solution, photo_bytes)
    solution.quality_score = score
    logger.info(f"TaskSolution {solution.id}: quality_score={score}")
    return score

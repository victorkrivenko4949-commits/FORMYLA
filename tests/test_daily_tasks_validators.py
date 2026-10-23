# -*- coding: utf-8 -*-
"""Unit tests for daily_tasks/pipeline/validators.py — all 8 validators + helpers."""

import json
from typing import Any, Dict, List

import pytest

from daily_tasks.pipeline.validators import (
    # Dataclasses
    LatexIssue,
    LatexValidationReport,
    GeminiSpecValidation,
    GeminiPlanValidation,
    OpusTaskValidation,
    OpusGenerationValidation,
    AuditIssueValidation,
    AuditEntryValidation,
    GPTAuditValidation,
    OpusFixValidation,
    CrossValidationResult,
    PipelineValidationResult,
    # Validators
    validate_daily_task_latex,
    auto_fix_latex,
    validate_gemini_plan,
    validate_opus_generation,
    validate_gpt_audit,
    validate_opus_fix,
    cross_validate_specs_and_tasks,
    cross_validate_audit_with_specs,
    cross_validate_all,
    validate_full_pipeline,
    has_solution_leak,
    extract_json_safe,
    validate_all_task_texts_latex,
    # Private helpers (unit-tested directly)
    _extract_json_from_response,
    _is_nonempty_string,
    _is_list_of_strings,
    _find_all_latex_spans,
    # Constants
    VALID_SLOT_KINDS,
    VALID_SUBJECTS,
    VALID_DIFFICULTY_RANGE,
    VALID_VERDICTS,
    VALID_SEVERITIES,
    VALID_AUDIT_CODES,
    GEMINI_SPEC_REQUIRED_FIELDS,
    OPUS_TASK_REQUIRED_FIELDS,
    GPT_AUDIT_ENTRY_REQUIRED_FIELDS,
    AUDIT_ISSUE_REQUIRED_FIELDS,
)


# =============================================================================
#  Helpers:  _is_nonempty_string, _is_list_of_strings, _find_all_latex_spans
# =============================================================================


class TestIsNonemptyString:
    def test_nonempty_string(self) -> None:
        assert _is_nonempty_string("hello") is True
        assert _is_nonempty_string(" a ") is True

    def test_empty_or_whitespace(self) -> None:
        assert _is_nonempty_string("") is False
        assert _is_nonempty_string("   ") is False

    def test_not_string(self) -> None:
        assert _is_nonempty_string(None) is False
        assert _is_nonempty_string(123) is False
        assert _is_nonempty_string([]) is False
        assert _is_nonempty_string({}) is False


class TestIsListOfStrings:
    def test_list_of_strings(self) -> None:
        assert _is_list_of_strings(["a", "b"]) is True
        assert _is_list_of_strings([]) is True

    def test_not_list(self) -> None:
        assert _is_list_of_strings(None) is False
        assert _is_list_of_strings("abc") is False
        assert _is_list_of_strings(42) is False

    def test_mixed_types(self) -> None:
        assert _is_list_of_strings(["a", 1]) is False
        assert _is_list_of_strings(["a", None]) is False


class TestFindAllLatexSpans:
    def test_no_latex(self) -> None:
        assert _find_all_latex_spans("plain text") == []

    def test_inline_only(self) -> None:
        spans = _find_all_latex_spans("text \\(x+1\\) end")
        assert len(spans) == 1
        assert spans[0][2] == "inline"

    def test_display_only(self) -> None:
        spans = _find_all_latex_spans("text \\[x+1\\] end")
        assert len(spans) == 1
        assert spans[0][2] == "display"

    def test_multiple_spans(self) -> None:
        text = "\\(a\\) and \\[b\\] and \\(c\\)"
        spans = _find_all_latex_spans(text)
        assert len(spans) == 3
        assert [s[2] for s in spans] == ["inline", "display", "inline"]

    def test_sorted_by_position(self) -> None:
        text = "\\[b\\] \\(a\\)"
        spans = _find_all_latex_spans(text)
        assert spans[0][2] == "display"  # \\[b\\] comes first
        assert spans[1][2] == "inline"


# =============================================================================
#  LaTeX Validation
# =============================================================================


class TestValidateDailyTaskLatex:
    def test_clean_latex_passes(self) -> None:
        """Valid \\(…\\) and \\[…\\] should produce no issues."""
        text = (
            "Solve \\(x + 1 = 2\\). "
            "\\[E = mc^2\\]"
        )
        report = validate_daily_task_latex(text)
        assert len(report.issues) == 0
        assert not report.has_errors
        assert not report.has_warnings

    def test_deprecated_dollar_detected(self) -> None:
        text = "Solve $x+1=2$"
        report = validate_daily_task_latex(text)
        codes = {i.code for i in report.issues}
        assert "deprecated_dollar" in codes
        assert report.has_errors

    def test_deprecated_double_dollar_detected(self) -> None:
        text = "Solve $$x+1=2$$"
        report = validate_daily_task_latex(text)
        codes = {i.code for i in report.issues}
        assert "deprecated_dollar" in codes
        assert report.has_errors

    def test_broken_commands_detected(self) -> None:
        text = "Use \\frrac{x}{y} or \\sqr{x}"
        report = validate_daily_task_latex(text)
        codes = {i.code for i in report.issues}
        assert "broken_command" in codes
        assert report.has_errors

    def test_bare_frac_detected(self) -> None:
        text = "\\frac12"
        report = validate_daily_task_latex(text)
        codes = {i.code for i in report.issues}
        assert "bare_frac" in codes
        assert report.has_errors

    def test_bare_power_detected_as_warning(self) -> None:
        """Bare power (2^3) is 'medium' severity -> warning, not error."""
        text = "Compute \\(2^3\\)"
        report = validate_daily_task_latex(text)
        codes = {i.code for i in report.issues}
        assert "bare_power" in codes
        assert not report.has_errors  # medium severity
        assert report.has_warnings

    def test_unbalanced_braces_detected(self) -> None:
        text = "\\(x + {1\\)"
        report = validate_daily_task_latex(text)
        codes = {i.code for i in report.issues}
        assert "unbalanced_braces" in codes
        assert report.has_errors

    def test_multiple_issues(self) -> None:
        text = "Solve $\\frrac{1}{2}$"
        report = validate_daily_task_latex(text)
        codes = {i.code for i in report.issues}
        assert "deprecated_dollar" in codes
        assert "broken_command" in codes
        assert report.has_errors

    def test_empty_text(self) -> None:
        report = validate_daily_task_latex("")
        assert len(report.issues) == 0

    def test_issue_snippet_nonempty(self) -> None:
        text = "prefix $bad$ suffix"
        report = validate_daily_task_latex(text)
        for issue in report.issues:
            assert len(issue.snippet) > 0
            assert isinstance(issue.message, str)
            assert isinstance(issue.code, str)


class TestAutoFixLatex:
    def test_dollar_to_paren(self) -> None:
        result = auto_fix_latex("$x+1$")
        assert "\\(" in result
        assert "\\)" in result
        assert "$" not in result

    def test_double_dollar_to_bracket(self) -> None:
        result = auto_fix_latex("$$x+1$$")
        assert "\\[" in result
        assert "\\]" in result

    def test_broken_commands_fixed(self) -> None:
        result = auto_fix_latex("\\frrac{x}{y} and \\sqr{z}")
        assert "\\frac" in result
        assert "\\sqrt" in result
        assert "\\frrac" not in result

    def test_bare_power_fixed(self) -> None:
        result = auto_fix_latex("^a")
        assert "^{a}" in result

    def test_frac12_fixed(self) -> None:
        result = auto_fix_latex("\\frac12")
        assert "\\frac{1}{2}" in result

    def test_unicode_math_replaced(self) -> None:
        result = auto_fix_latex("x \u2260 y")  # ≠
        assert "\\neq" in result

    def test_clean_text_unchanged(self) -> None:
        text = "Hello \\(x+1\\) world"
        assert auto_fix_latex(text) == text

    def test_empty_text(self) -> None:
        assert auto_fix_latex("") == ""


# =============================================================================
#  JSON Extraction
# =============================================================================


def _make_gemini_spec(pos: int, **overrides: Any) -> Dict[str, Any]:
    """Build a valid Gemini spec dict for testing."""
    spec: Dict[str, Any] = {
        "position": pos,
        "slot_kind": "weak_main",
        "subject": "algebra",
        "topic": f"Topic{pos}",
        "subtopic": f"Subtopic{pos}",
        "difficulty_level": 3,
        "task_archetype": "equation",
        "must_use_concepts": ["concept_a"],
        "must_avoid": ["trap_x"],
        "answer_form": "number",
        "estimated_solve_minutes": 5,
        "reason_for_student": f"Reason {pos}",
    }
    spec.update(overrides)
    return spec


def _make_opus_task(pos: int, **overrides: Any) -> Dict[str, Any]:
    """Build a valid Opus task dict for testing."""
    task: Dict[str, Any] = {
        "position": pos,
        "task_text": f"Task text for position {pos} with \\(x+1\\)",
        "correct_answer": f"Answer{pos}",
        "solution": f"Solution {pos}",
        "hints": [f"Hint {pos}_1", f"Hint {pos}_2"],
    }
    task.update(overrides)
    return task


def _make_audit_entry(pos: int, verdict: str = "approved",
                      issues: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    """Build a valid GPT audit entry dict."""
    entry: Dict[str, Any] = {
        "position": pos,
        "verdict": verdict,
        "issues": issues or [],
    }
    return entry


class TestExtractJsonFromResponse:
    def test_json_code_block(self) -> None:
        raw = 'Some text\n```json\n{"specs": []}\n```\nmore'
        result = _extract_json_from_response(raw)
        assert result == {"specs": []}

    def test_code_block_without_json_marker(self) -> None:
        raw = 'Prefix\n```\n{"tasks": []}\n```\nSuffix'
        result = _extract_json_from_response(raw)
        assert result == {"tasks": []}

    def test_plain_json_brace_matching(self) -> None:
        raw = '{"a": {"b": 1}}'
        result = _extract_json_from_response(raw)
        assert result == {"a": {"b": 1}}

    def test_trailing_comma_fixed(self) -> None:
        raw = '{"a": 1,}'
        result = _extract_json_from_response(raw)
        assert result == {"a": 1}

    def test_nested_braces_with_trailing_comma(self) -> None:
        raw = '{"a": {"b": [1, 2,]}}'
        result = _extract_json_from_response(raw)
        assert result == {"a": {"b": [1, 2]}}

    def test_empty_input(self) -> None:
        assert _extract_json_from_response("") is None
        assert _extract_json_from_response("   ") is None

    def test_no_braces_returns_none(self) -> None:
        assert _extract_json_from_response("just text") is None

    def test_unmatched_braces_returns_none(self) -> None:
        assert _extract_json_from_response('{"unclosed') is None


class TestExtractJsonSafe:
    def test_valid_json(self) -> None:
        result = extract_json_safe('{"key": "val"}')
        assert result == {"key": "val"}

    def test_invalid_json_returns_none(self) -> None:
        result = extract_json_safe("not json")
        assert result is None

    def test_empty_input(self) -> None:
        assert extract_json_safe("") is None


# =============================================================================
#  Gemini Plan Validation
# =============================================================================


class TestValidateGeminiPlan:
    def test_valid_10_specs(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is True
        assert len(result.entries) == 10
        assert result.global_errors == []

    def test_invalid_json_returns_error(self) -> None:
        result = validate_gemini_plan("not json")
        assert result.valid is False
        assert len(result.global_errors) > 0

    def test_missing_specs_key(self) -> None:
        raw = json.dumps({"tasks": []})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("specs" in e for e in result.global_errors)

    def test_specs_not_list(self) -> None:
        raw = json.dumps({"specs": "not_a_list"})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("массив" in e for e in result.global_errors)

    def test_wrong_count_9_specs(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 10)]
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("9" in e for e in result.global_errors)

    def test_wrong_count_11_specs(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 12)]
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("11" in e for e in result.global_errors)

    def test_duplicate_position(self) -> None:
        specs = [_make_gemini_spec(1) for _ in range(2)]
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        dup_errors = [e for e in result.all_errors if "Дубликат" in e]
        assert len(dup_errors) > 0

    def test_position_out_of_range(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 10)]
        specs.append(_make_gemini_spec(11))
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        pos_errors = [e for e in result.all_errors if "вне диапазона" in e]
        assert len(pos_errors) > 0

    def test_invalid_slot_kind(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        specs[0]["slot_kind"] = "invalid_slot"
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("slot_kind" in e for e in result.all_errors)

    def test_invalid_subject_triggers_warning(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        specs[0]["subject"] = "invalid_subject"
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        # Subject validation is a warning, not an error
        warning_entries = [e for e in result.entries if len(e.warnings) > 0]
        assert len(warning_entries) > 0
        assert any("subject" in w for e in result.entries for w in e.warnings)

    def test_missing_required_fields(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        del specs[0]["topic"]
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("Отсутствуют поля" in e for e in result.all_errors)

    def test_duplicate_topic_subtopic(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        specs[0]["topic"] = specs[1]["topic"] = "SameTopic"
        specs[0]["subtopic"] = specs[1]["subtopic"] = "SameSubtopic"
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        warnings = [w for e in result.entries for w in e.warnings if "Дубликат" in w]
        assert len(warnings) > 0

    def test_spec_not_dict(self) -> None:
        raw = json.dumps({"specs": ["not_a_dict"]})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("объектом" in e for e in result.all_errors)

    def test_must_use_concepts_wrong_type(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        specs[0]["must_use_concepts"] = "not_a_list"
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("must_use_concepts" in e for e in result.all_errors)

    def test_difficulty_out_of_range(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        specs[0]["difficulty_level"] = 99
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("difficulty_level" in e for e in result.all_errors)

    def test_answer_form_empty_string(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        specs[0]["answer_form"] = ""
        raw = json.dumps({"specs": specs})
        result = validate_gemini_plan(raw)
        assert result.valid is False
        assert any("answer_form" in e for e in result.all_errors)


# =============================================================================
#  Opus Generation Validation
# =============================================================================


class TestValidateOpusGeneration:
    def test_valid_10_tasks(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is True
        assert len(result.entries) == 10
        assert result.global_errors == []

    def test_invalid_json(self) -> None:
        result = validate_opus_generation("not json")
        assert result.valid is False
        assert len(result.global_errors) > 0

    def test_missing_tasks_key(self) -> None:
        raw = json.dumps({"specs": []})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("tasks" in e for e in result.global_errors)

    def test_wrong_count(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 6)]  # 5 tasks
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("5" in e for e in result.global_errors)

    def test_duplicate_position(self) -> None:
        tasks = [_make_opus_task(1) for _ in range(2)]
        tasks += [_make_opus_task(i) for i in range(2, 10)]
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False
        dup_errors = [e for e in result.all_errors if "Дубликат" in e]
        assert len(dup_errors) > 0

    def test_missing_required_fields(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        del tasks[0]["task_text"]
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("Отсутствуют поля" in e for e in result.all_errors)

    def test_task_text_latex_error(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["task_text"] = "Bad $latex$ here"
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("LaTeX" in e for e in result.all_errors)

    def test_empty_task_text(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["task_text"] = ""
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("пуст" in e for e in result.all_errors)

    def test_hints_wrong_type(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["hints"] = "not_a_list"
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("массивом" in e for e in result.all_errors)

    def test_hints_too_many(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["hints"] = ["h1", "h2", "h3", "h4"]  # 4 > 3 max
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        # Too many hints is a warning, not an error
        assert any("hints" in w for e in result.entries for w in e.warnings)

    def test_hints_not_strings(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["hints"] = [1, 2]  # numbers, not strings
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("строк" in e for e in result.all_errors)

    def test_task_not_dict(self) -> None:
        raw = json.dumps({"tasks": ["not_a_dict"]})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("объектом" in e for e in result.all_errors)

    def test_tasks_not_list(self) -> None:
        raw = json.dumps({"tasks": "not_a_list"})
        result = validate_opus_generation(raw)
        assert result.valid is False
        assert any("массив" in e for e in result.global_errors)

    def test_correct_answer_empty(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["correct_answer"] = ""
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False

    def test_solution_empty(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["solution"] = ""
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        assert result.valid is False

    def test_to_dict_method(self) -> None:
        """OpusGenerationValidation.to_dict() should return serializable dict."""
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        raw = json.dumps({"tasks": tasks})
        result = validate_opus_generation(raw)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "valid" in d
        assert "entries" in d
        assert len(d["entries"]) == 10


# =============================================================================
#  GPT Audit Validation
# =============================================================================


class TestValidateGptAudit:
    def test_valid_10_audit_entries(self) -> None:
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        assert result.valid is True
        assert len(result.entries) == 10
        assert result.global_errors == []

    def test_valid_with_needs_fix(self) -> None:
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        entries[0]["verdict"] = "needs_fix"
        entries[0]["issues"] = [
            {"code": "bad_latex", "severity": "medium",
             "explanation": "bad", "fix_instruction": "fix it"}
        ]
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        assert result.valid is True

    def test_invalid_json(self) -> None:
        result = validate_gpt_audit("not json")
        assert result.valid is False
        assert len(result.global_errors) > 0

    def test_missing_audit_key(self) -> None:
        raw = json.dumps({"tasks": []})
        result = validate_gpt_audit(raw)
        assert result.valid is False
        assert any("audit" in e for e in result.global_errors)

    def test_wrong_count(self) -> None:
        # NB: validate_gpt_audit принимает 1..10 (по batch'у),
        # см. комментарий в validators.py:821-824. Чтобы спровоцировать
        # ошибку «wrong count», нужно > 10 entries.
        entries = [_make_audit_entry(i) for i in range(1, 12)]  # 11 entries
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        assert result.valid is False
        assert any("11" in e for e in result.global_errors)

    def test_duplicate_position(self) -> None:
        entries = [_make_audit_entry(1) for _ in range(2)]
        entries += [_make_audit_entry(i) for i in range(2, 10)]
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        assert result.valid is False
        dup_errors = [e for e in result.all_errors if "Дубликат" in e]
        assert len(dup_errors) > 0

    def test_invalid_verdict(self) -> None:
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        entries[0]["verdict"] = "invalid_verdict"
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        assert result.valid is False
        assert any("verdict" in e for e in result.all_errors)

    def test_approved_with_issues_triggers_warning(self) -> None:
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        entries[0]["verdict"] = "approved"
        entries[0]["issues"] = [
            {"code": "bad_latex", "severity": "low",
             "explanation": "minor", "fix_instruction": "fix"}
        ]
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        # Should still be valid (warning only)
        assert result.valid is True
        warnings = [w for e in result.entries for w in e.warnings if "approved" in w]
        assert len(warnings) > 0

    def test_missing_required_audit_fields(self) -> None:
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        del entries[0]["position"]
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        assert result.valid is False
        assert any("Отсутствуют поля" in e for e in result.all_errors)

    def test_issues_missing_required_fields(self) -> None:
        """Issue-level validation failures don't propagate to entry.valid."""
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        entries[0]["verdict"] = "needs_fix"
        entries[0]["issues"] = [{"code": "bad_latex"}]  # missing severity, explanation, fix_instruction
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        # Issue validation failures don't propagate to entry-level validity
        assert result.valid is True
        # But the issue should still have validation errors
        assert any(not iv.valid for e in result.entries for iv in e.issues_validation)

    def test_issues_not_list(self) -> None:
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        entries[0]["issues"] = "not_a_list"
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        assert result.valid is False
        assert any("массивом" in e for e in result.all_errors)

    def test_audit_not_list(self) -> None:
        raw = json.dumps({"audit": "not_a_list"})
        result = validate_gpt_audit(raw)
        assert result.valid is False

    def test_entry_not_dict(self) -> None:
        raw = json.dumps({"audit": ["not_a_dict"]})
        result = validate_gpt_audit(raw)
        assert result.valid is False

    def test_issue_not_dict(self) -> None:
        """Issue-level validation failures don't propagate to entry.valid."""
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        entries[0]["verdict"] = "needs_fix"
        entries[0]["issues"] = ["not_a_dict"]
        raw = json.dumps({"audit": entries})
        result = validate_gpt_audit(raw)
        # Issue validation failures don't propagate to entry-level validity
        assert result.valid is True


# =============================================================================
#  Opus Fix Validation
# =============================================================================


class TestValidateOpusFix:
    def test_valid_task_direct(self) -> None:
        task = _make_opus_task(5)
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        assert result.valid is True
        assert result.fixed_position == 5

    def test_valid_task_wrapped(self) -> None:
        task = _make_opus_task(3)
        raw = json.dumps({"task": task})
        result = validate_opus_fix(raw)
        assert result.valid is True
        assert result.fixed_position == 3

    def test_invalid_json(self) -> None:
        result = validate_opus_fix("not json")
        assert result.valid is False
        assert len(result.errors) > 0

    def test_not_dict(self) -> None:
        result = validate_opus_fix('"just_a_string"')
        assert result.valid is False

    def test_missing_required_fields(self) -> None:
        task = _make_opus_task(5)
        del task["task_text"]
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        assert result.valid is False
        assert any("Отсутствуют поля" in e for e in result.errors)

    def test_position_out_of_range(self) -> None:
        task = _make_opus_task(99)
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        # position out of range adds an error -> valid becomes False
        assert result.valid is False
        assert any("вне диапазона" in e for e in result.errors)

    def test_latex_error_in_task_text(self) -> None:
        task = _make_opus_task(5, task_text="Bad $latex$ here")
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        assert result.valid is False
        assert any("LaTeX" in e for e in result.errors)

    def test_empty_task_text(self) -> None:
        task = _make_opus_task(5, task_text="")
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        assert result.valid is False
        assert any("пуст" in e for e in result.errors)

    def test_empty_correct_answer(self) -> None:
        task = _make_opus_task(5, correct_answer="")
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        assert result.valid is False
        assert any("correct_answer" in e for e in result.errors)

    def test_latex_report_populated(self) -> None:
        task = _make_opus_task(5, task_text="\\(x+1\\)")
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        assert result.valid is True
        assert result.latex_report is not None
        assert not result.latex_report.has_errors

    def test_to_dict(self) -> None:
        task = _make_opus_task(5)
        raw = json.dumps(task)
        result = validate_opus_fix(raw)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert d["fixed_position"] == 5


# =============================================================================
#  Cross Validation
# =============================================================================


class TestCrossValidateSpecsAndTasks:
    def test_all_positions_match(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        result = cross_validate_specs_and_tasks(specs, tasks)
        assert result.valid is True
        assert result.errors == []
        assert result.warnings == []

    def test_missing_task_positions(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 9)]  # only 8 tasks
        result = cross_validate_specs_and_tasks(specs, tasks)
        assert result.valid is False
        assert any("Нет задачи" in e for e in result.errors)

    def test_extra_task_positions(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 9)]  # 8 specs
        tasks = [_make_opus_task(i) for i in range(1, 11)]  # 10 tasks
        result = cross_validate_specs_and_tasks(specs, tasks)
        assert result.valid is True  # extra tasks are warnings, not errors
        assert len(result.warnings) > 0

    def test_empty_inputs(self) -> None:
        result = cross_validate_specs_and_tasks([], [])
        assert result.valid is False
        assert any("пусты" in e for e in result.errors)


class TestCrossValidateAuditWithSpecs:
    def test_all_positions_audited(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        audit_entries = [_make_audit_entry(i) for i in range(1, 11)]
        result = cross_validate_audit_with_specs(audit_entries, specs)
        assert result.valid is True
        assert result.errors == []

    def test_missing_audit_entries(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        audit_entries = [_make_audit_entry(i) for i in range(1, 8)]  # 7 entries
        result = cross_validate_audit_with_specs(audit_entries, specs)
        assert result.valid is False
        assert any("Не проаудированы" in e for e in result.errors)

    def test_extra_audit_entries_warn(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 8)]  # 7 specs
        audit_entries = [_make_audit_entry(i) for i in range(1, 11)]  # 10 entries
        result = cross_validate_audit_with_specs(audit_entries, specs)
        assert result.valid is True  # extra audit entries are warnings
        assert len(result.warnings) > 0

    def test_empty_inputs(self) -> None:
        result = cross_validate_audit_with_specs([], [])
        assert result.valid is False
        assert any("пусты" in e for e in result.errors)


class TestCrossValidateAll:
    def test_all_valid(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        audit_entries = [_make_audit_entry(i) for i in range(1, 11)]
        result = cross_validate_all(specs, tasks, audit_entries)
        assert result.valid is True

    def test_spec_task_mismatch(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 9)]  # missing 2 tasks
        audit_entries = [_make_audit_entry(i) for i in range(1, 11)]
        result = cross_validate_all(specs, tasks, audit_entries)
        assert result.valid is False

    def test_audit_coverage_mismatch(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        audit_entries = [_make_audit_entry(i) for i in range(1, 6)]  # only 5 audited
        result = cross_validate_all(specs, tasks, audit_entries)
        assert result.valid is False

    def test_to_dict(self) -> None:
        result = cross_validate_all([], [], [])
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "valid" in d
        assert "errors" in d
        assert "warnings" in d


# =============================================================================
#  Full Pipeline Validation
# =============================================================================


class TestValidateFullPipeline:
    def test_valid_pipeline(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        gemini_raw = json.dumps({"specs": specs})
        opus_raw = json.dumps({"tasks": tasks})
        result = validate_full_pipeline(gemini_raw, opus_raw)
        assert result.valid is True
        assert result.gemini is not None
        assert result.opus is not None

    def test_valid_with_audit_and_fix(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        entries = [_make_audit_entry(i) for i in range(1, 11)]
        gemini_raw = json.dumps({"specs": specs})
        opus_raw = json.dumps({"tasks": tasks})
        audit_raw = json.dumps({"audit": entries})
        fix_raw = json.dumps(_make_opus_task(5))
        result = validate_full_pipeline(
            gemini_raw, opus_raw,
            gpt_audit_response=audit_raw,
            opus_fix_response=fix_raw,
        )
        assert result.valid is True
        assert result.gpt_audit is not None
        assert result.opus_fix is not None

    def test_failing_gemini(self) -> None:
        result = validate_full_pipeline("bad json", "{}")
        assert result.valid is False
        assert result.gemini is not None
        assert not result.gemini.valid

    def test_failing_opus(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        gemini_raw = json.dumps({"specs": specs})
        result = validate_full_pipeline(gemini_raw, "bad json")
        assert result.valid is False
        assert result.opus is not None
        assert not result.opus.valid

    def test_cross_validation_included(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 9)]  # missing 2
        gemini_raw = json.dumps({"specs": specs})
        opus_raw = json.dumps({"tasks": tasks})
        result = validate_full_pipeline(gemini_raw, opus_raw)
        assert result.cross is not None
        assert not result.cross.valid

    def test_to_dict(self) -> None:
        specs = [_make_gemini_spec(i) for i in range(1, 11)]
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        gemini_raw = json.dumps({"specs": specs})
        opus_raw = json.dumps({"tasks": tasks})
        result = validate_full_pipeline(gemini_raw, opus_raw)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "gemini" in d
        assert "opus" in d
        assert "cross" in d


# =============================================================================
#  Solution Leak Detection
# =============================================================================


class TestHasSolutionLeak:
    def test_answer_present_in_text(self) -> None:
        leaked, snippet = has_solution_leak(
            "Find the value of x where x = 42.5",
            "42.5"
        )
        assert leaked is True
        assert "42.5" in snippet

    def test_answer_not_present(self) -> None:
        leaked, _ = has_solution_leak(
            "Find the value of x",
            "42"
        )
        assert leaked is False

    def test_case_insensitive(self) -> None:
        leaked, _ = has_solution_leak(
            "Answer is ABC",
            "abc"
        )
        assert leaked is True

    def test_short_answer_skipped(self) -> None:
        """Answers with length <= 2 should be skipped to avoid false positives."""
        leaked, _ = has_solution_leak(
            "Find x where x = a",
            "a"
        )
        assert leaked is False

    def test_empty_text(self) -> None:
        leaked, _ = has_solution_leak("", "42")
        assert leaked is False

    def test_empty_answer(self) -> None:
        leaked, _ = has_solution_leak("Some text", "")
        assert leaked is False

    def test_snippet_context(self) -> None:
        text = "x" * 50 + "SECRET" + "y" * 50
        leaked, snippet = has_solution_leak(text, "SECRET")
        assert leaked is True
        assert len(snippet) <= 20 + 6 + 20  # 20 context each side + answer length


# =============================================================================
#  validate_all_task_texts_latex
# =============================================================================


class TestValidateAllTaskTextsLatex:
    def test_all_clean(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        reports = validate_all_task_texts_latex(tasks)
        assert len(reports) == 10
        for pos in range(1, 11):
            assert pos in reports
            assert not reports[pos].has_errors

    def test_mixed_quality(self) -> None:
        tasks = [_make_opus_task(i) for i in range(1, 11)]
        tasks[0]["task_text"] = "Bad $latex$"  # error
        tasks[1]["task_text"] = "\\(2^3\\)"  # warning (bare power)
        reports = validate_all_task_texts_latex(tasks)
        assert reports[1].has_errors  # deprecated_dollar
        assert reports[2].has_warnings  # bare_power
        assert not reports[3].has_errors  # clean

    def test_empty_input(self) -> None:
        reports = validate_all_task_texts_latex([])
        assert reports == {}

    def test_skips_non_dict_tasks(self) -> None:
        tasks = [{"position": 1, "task_text": "\\(x\\)"}, "not_a_dict"]
        reports = validate_all_task_texts_latex(tasks)
        assert len(reports) == 1


# =============================================================================
#  Dataclass — to_dict coverage
# =============================================================================


class TestDataclassToDict:
    """Ensure all dataclass to_dict() methods work correctly."""

    def test_latex_issue_to_dict(self) -> None:
        issue = LatexIssue(code="deprecated_dollar", severity="high",
                           message="test", snippet="abc")
        d = issue.to_dict()
        assert d["code"] == "deprecated_dollar"

    def test_latex_report_to_dict(self) -> None:
        report = LatexValidationReport()
        d = report.to_dict()
        assert d["has_errors"] is False

    def test_gemini_spec_to_dict(self) -> None:
        spec = GeminiSpecValidation(position=1, valid=True)
        d = spec.to_dict()
        assert d["position"] == 1

    def test_gemini_plan_to_dict(self) -> None:
        plan = GeminiPlanValidation(valid=True)
        d = plan.to_dict()
        assert d["valid"] is True

    def test_opus_task_to_dict(self) -> None:
        task = OpusTaskValidation(position=2, valid=True)
        d = task.to_dict()
        assert d["position"] == 2

    def test_opus_generation_to_dict(self) -> None:
        gen = OpusGenerationValidation(valid=True)
        d = gen.to_dict()
        assert d["valid"] is True

    def test_audit_issue_to_dict(self) -> None:
        iss = AuditIssueValidation(valid=True)
        d = iss.to_dict()
        assert d["valid"] is True

    def test_audit_entry_to_dict(self) -> None:
        entry = AuditEntryValidation(position=3, valid=True)
        d = entry.to_dict()
        assert d["position"] == 3

    def test_gpt_audit_to_dict(self) -> None:
        audit = GPTAuditValidation(valid=True)
        d = audit.to_dict()
        assert d["valid"] is True

    def test_opus_fix_to_dict(self) -> None:
        fix = OpusFixValidation(valid=True)
        d = fix.to_dict()
        assert d["valid"] is True

    def test_cross_validation_to_dict(self) -> None:
        cv = CrossValidationResult(valid=True)
        d = cv.to_dict()
        assert d["valid"] is True

    def test_pipeline_validation_to_dict(self) -> None:
        gemini_val = GeminiPlanValidation(valid=True)
        opus_val = OpusGenerationValidation(valid=True)
        pv = PipelineValidationResult(valid=True, gemini=gemini_val, opus=opus_val)
        d = pv.to_dict()
        assert d["valid"] is True
        assert d["gemini"]["valid"] is True
        assert d["opus"]["valid"] is True


# =============================================================================
#  Constants
# =============================================================================


class TestConstants:
    def test_valid_slot_kinds(self) -> None:
        assert "weak_base" in VALID_SLOT_KINDS
        assert "weak_main" in VALID_SLOT_KINDS
        assert "weak_challenge" in VALID_SLOT_KINDS
        assert "strong_review" in VALID_SLOT_KINDS
        assert "strong_challenge" in VALID_SLOT_KINDS

    def test_valid_subjects(self) -> None:
        assert "algebra" in VALID_SUBJECTS
        assert "geometry" in VALID_SUBJECTS
        assert "number_theory" in VALID_SUBJECTS
        assert "combinatorics" in VALID_SUBJECTS
        assert "logic" in VALID_SUBJECTS

    def test_difficulty_range(self) -> None:
        assert VALID_DIFFICULTY_RANGE == (1, 5)

    def test_valid_verdicts(self) -> None:
        assert "approved" in VALID_VERDICTS
        assert "needs_fix" in VALID_VERDICTS

    def test_valid_severities(self) -> None:
        assert "low" in VALID_SEVERITIES
        assert "medium" in VALID_SEVERITIES
        assert "high" in VALID_SEVERITIES

    def test_valid_audit_codes(self) -> None:
        expected = {
            "bad_latex", "too_easy", "too_hard", "impossible_task",
            "wrong_answer", "spec_mismatch", "duplicate_archetype",
            "low_solution_quality",
        }
        assert VALID_AUDIT_CODES == expected

    def test_gemini_spec_required_fields(self) -> None:
        required = {
            "position", "slot_kind", "subject", "topic", "subtopic",
            "difficulty_level", "task_archetype", "must_use_concepts",
            "must_avoid", "answer_form", "estimated_solve_minutes",
            "reason_for_student",
        }
        assert GEMINI_SPEC_REQUIRED_FIELDS == required

    def test_opus_task_required_fields(self) -> None:
        assert OPUS_TASK_REQUIRED_FIELDS == {
            "position", "task_text", "correct_answer", "solution", "hints",
        }

    def test_gpt_audit_entry_required_fields(self) -> None:
        assert GPT_AUDIT_ENTRY_REQUIRED_FIELDS == {
            "position", "verdict", "issues",
        }

    def test_audit_issue_required_fields(self) -> None:
        # Canonical (см. daily_tasks/pipeline/prompts/gpt_audit.md и
        # daily_tasks/pipeline/validators.py:316) — поле называется
        # 'description', а не 'explanation'.
        assert AUDIT_ISSUE_REQUIRED_FIELDS == {
            "code", "severity", "description", "fix_instruction",
        }

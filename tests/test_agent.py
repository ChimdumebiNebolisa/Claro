"""Tests for agent module: system prompt and WriteTokenParser."""
import pytest

from agent import build_system_prompt, WriteTokenParser


def test_build_system_prompt_includes_assignment():
    """System prompt includes the assignment text."""
    assignment = "Question 1: What is 2+2?\n\nQuestion 2: What is 3+3?"
    prompt = build_system_prompt(assignment)
    assert "Question 1: What is 2+2?" in prompt
    assert "Question 2: What is 3+3?" in prompt


def test_build_system_prompt_includes_writing_rules():
    """System prompt includes key writing rules for answer readiness."""
    prompt = build_system_prompt("Question 1: Foo")
    assert "Tell me your final answer first" in prompt
    assert "Let me write that for question" in prompt


def test_write_token_parser_write_start():
    """WriteTokenParser emits write_start when [WRITE:N] is seen."""
    parser = WriteTokenParser()
    events = parser.feed("[WRITE:1] Hello world [END_WRITE:1]")
    event_types = [e["event"] for e in events]
    assert "write_start" in event_types
    assert "write_end" in event_types
    assert any(e.get("event") == "write_start" and e.get("question_id") == 1 for e in events)


def test_write_token_parser_write_token():
    """WriteTokenParser emits write_token with accumulated text."""
    parser = WriteTokenParser()
    events = parser.feed("[WRITE:2] The answer is 42. [END_WRITE:2]")
    token_events = [e for e in events if e.get("event") == "write_token"]
    assert len(token_events) >= 1
    assert "42" in token_events[0].get("text", "")


def test_write_token_parser_multiple_questions():
    """WriteTokenParser handles multiple [WRITE:N] ... [END_WRITE:N] in sequence."""
    parser = WriteTokenParser()
    text = "[WRITE:1] One [END_WRITE:1] [WRITE:2] Two [END_WRITE:2]"
    events = parser.feed(text)
    starts = [e for e in events if e.get("event") == "write_start"]
    ends = [e for e in events if e.get("event") == "write_end"]
    assert len(starts) == 2
    assert len(ends) == 2
    assert [e["question_id"] for e in starts] == [1, 2]

"""Tests for agent complexity planning heuristics."""

from parrrot.core.agent import Agent


def test_needs_advanced_planning_for_multi_step_request():
    text = "Open my email and summarize unread messages, then draft a reply."
    assert Agent._needs_advanced_planning(text) is True


def test_needs_advanced_planning_for_simple_request():
    text = "What time is it?"
    assert Agent._needs_advanced_planning(text) is False

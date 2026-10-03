"""Fake LLM generate_structured functions for unit testing Module 3."""
from __future__ import annotations

from typing import Any


def make_fake_generate_structured(scenario_map: dict[str, str]):
    """Returns an async callable matching GenerateStructured protocol.

    Inspects user_prompt to identify the question scenario and returns
    realistic LLM output.
    """
    async def _fake(*, system_prompt: str, user_prompt: str, model: str = "gpt-4o", temperature: float = 0.2) -> dict[str, Any]:
        scenario = "strong_technical"
        for q_id, s_name in scenario_map.items():
            if q_id in user_prompt:
                scenario = s_name
                break

        if scenario == "weak_behavioral_no_star":
            return {
                "dimension_scores": [
                    {"dimension": "accuracy", "score": 4.0, "rationale": "Vague description of resolution."},
                    {"dimension": "depth", "score": 3.0, "rationale": "No deep reflection or learning articulated."},
                    {"dimension": "clarity", "score": 3.0, "rationale": "Lacks Situation, Task, Action, Result structure (STAR)."},
                    {"dimension": "relevance", "score": 4.0, "rationale": "Only minimally addresses the prompt."},
                    {"dimension": "confidence", "score": 4.0, "rationale": "Phrasing is brief and non-descript."},
                ],
                "summary_feedback": "The answer was far too brief and lacked the STAR (Situation, Task, Action, Result) structure required for behavioral questions.",
                "strengths": ["Identified that communication took place"],
                "improvements": ["Use the STAR framework (Situation, Task, Action, Result) to structure your story"],
                "model_answer_snippet": "In my previous project, we faced a conflict over API design. I organized a meeting, presented pros/cons, and we reached consensus.",
                "skill_level_inferred": "novice",
                "suggested_follow_up": "Can you describe the specific situation and the action you took?",
            }
        elif scenario == "mediocre_situational":
            return {
                "dimension_scores": [
                    {"dimension": "accuracy", "score": 6.5, "rationale": "Correct basic steps (slow log, pg_stat_activity)."},
                    {"dimension": "depth", "score": 5.5, "rationale": "Missed deep query analysis tools like EXPLAIN ANALYZE."},
                    {"dimension": "clarity", "score": 6.5, "rationale": "Clear sequential order of troubleshooting steps."},
                    {"dimension": "relevance", "score": 7.0, "rationale": "Directly addresses database high CPU load."},
                    {"dimension": "confidence", "score": 6.0, "rationale": "Sound tone but somewhat brief."},
                ],
                "summary_feedback": "Good initial steps for handling high CPU, but could demonstrate deeper diagnostic knowledge.",
                "strengths": ["Checked slow query log and active connections"],
                "improvements": ["Mention EXPLAIN ANALYZE and connection pooling"],
                "model_answer_snippet": "I would first inspect pg_stat_activity to find blocking queries, run EXPLAIN ANALYZE on long runners, and scale poolers if saturated.",
                "skill_level_inferred": "competent",
                "suggested_follow_up": None,
            }
        else:  # strong_technical
            return {
                "dimension_scores": [
                    {"dimension": "accuracy", "score": 9.0, "rationale": "Factually precise comparison of B-tree vs Hash index."},
                    {"dimension": "depth", "score": 8.5, "rationale": "Clear understanding of range queries vs equality lookups."},
                    {"dimension": "clarity", "score": 9.0, "rationale": "Well-structured response."},
                    {"dimension": "relevance", "score": 9.5, "rationale": "Completely answers the question asked."},
                    {"dimension": "confidence", "score": 8.5, "rationale": "Decisive and clear technical explanation."},
                ],
                "summary_feedback": "Strong technical response demonstrating thorough understanding of PostgreSQL indexing internals.",
                "strengths": ["Clear explanation of range vs hash index behavior"],
                "improvements": ["Could mention write amplification/maintenance costs"],
                "model_answer_snippet": "B-tree indexes maintain a sorted tree structure supporting range and equality queries, whereas Hash indexes use hash tables suitable only for equality lookups.",
                "skill_level_inferred": "proficient",
                "suggested_follow_up": None,
            }

    return _fake


async def fake_report_generate_structured(*, system_prompt: str, user_prompt: str, model: str = "gpt-4o", temperature: float = 0.3) -> dict[str, Any]:
    return {
        "executive_summary": "The candidate demonstrated solid backend fundamentals with strong PostgreSQL knowledge, but requires practice structuring behavioral responses around the STAR framework.",
        "top_strengths": [
            "Strong PostgreSQL indexing concepts",
            "Clear technical explanations",
        ],
        "priority_gaps": [
            "Behavioral responses lack STAR structure",
            "Incident response depth can be expanded",
        ],
        "study_plan": [
            "Practice structuring past experiences using the STAR framework (Situation, Task, Action, Result).",
            "Review PostgreSQL query optimization and EXPLAIN ANALYZE tools.",
            "Review the exemplar answer for turn 2 on conflict resolution.",
        ],
    }

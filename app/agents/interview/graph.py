"""
LangGraph workflow for the Interview Agent (Module 2).

Phase 3 flow:

START
  ↓
load_skill_gap
  ↓
init_question_set
  ↓
ask_question
  ↓
await_answer
  ↓
evaluate_turn
  ↓
route
  ├── next_question → move_to_next_question → await_answer
  └── follow_up → handle_follow_up → await_answer
"""

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.agents.interview.nodes import (
    InterviewGraphState,
    ask_question,
    await_answer,
    evaluate_turn,
    handle_drill_deeper,
    handle_follow_up,
    init_question_set,
    load_skill_gap,
    move_to_next_question,
    route_after_evaluation,
)


async def load_skill_gap_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return await load_skill_gap(state)


async def init_question_set_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return await init_question_set(state)


async def ask_question_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return await ask_question(state)


async def await_answer_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return await await_answer(state)


async def evaluate_turn_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return await evaluate_turn(state)


def route_after_evaluation_node(
    state: InterviewGraphState,
) -> Literal[
    "next_question",
    "follow_up",
    "drill_deeper",
    "skip_to_harder",
]:
    return route_after_evaluation(state)


def move_to_next_question_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return move_to_next_question(state)


def handle_follow_up_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return handle_follow_up(state)


def handle_drill_deeper_node(
    state: InterviewGraphState,
) -> InterviewGraphState:
    return handle_drill_deeper(state)


def build_interview_graph():
    """Build and compile the Interview Agent LangGraph."""

    graph = StateGraph(InterviewGraphState)

    # Nodes
    graph.add_node("load_skill_gap", load_skill_gap_node)
    graph.add_node("init_question_set", init_question_set_node)
    graph.add_node("ask_question", ask_question_node)
    graph.add_node("await_answer", await_answer_node)
    graph.add_node("evaluate_turn", evaluate_turn_node)
    graph.add_node("route", route_after_evaluation_node)
    graph.add_node(
        "move_to_next_question",
        move_to_next_question_node,
    )
    graph.add_node(
        "handle_follow_up",
        handle_follow_up_node,
    )
    graph.add_node(
        "handle_drill_deeper",
        handle_drill_deeper_node,
    )

    # Initial interview flow
    graph.add_edge(START, "load_skill_gap")
    graph.add_edge("load_skill_gap", "init_question_set")
    graph.add_edge("init_question_set", "ask_question")
    graph.add_edge("ask_question", "await_answer")
    graph.add_edge("await_answer", "evaluate_turn")
    graph.add_edge("evaluate_turn", "route")

    # Routing after evaluation
    graph.add_conditional_edges(
        "route",
        route_after_evaluation_node,
        {
            "next_question": "move_to_next_question",
            "follow_up": "handle_follow_up",
            "drill_deeper": "handle_drill_deeper",
            "skip_to_harder": "move_to_next_question",
        },
    )

    # All action nodes create the next InterviewTurn.
    # Therefore they go directly to awaiting the candidate's answer.
    graph.add_edge(
        "move_to_next_question",
        "await_answer",
    )
    graph.add_edge(
        "handle_follow_up",
        "await_answer",
    )
    graph.add_edge(
        "handle_drill_deeper",
        "await_answer",
    )

    return graph.compile()


interview_graph = build_interview_graph()
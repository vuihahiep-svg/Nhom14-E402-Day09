"""
graph.py — Supervisor Orchestrator (LangGraph version)
Sprint 1: Implement AgentState, supervisor_node, route_decision, HITL và kết nối graph.

Kiến trúc:
    Input → Supervisor → [retrieval_worker | policy_tool_worker | human_review]
          :contentReference[oaicite:0]{index=0}un_graph(task) lần đầu
       - nếu gặp human_review_node, graph sẽ pause và trả về "__interrupt__"
    2) resume_graph(run_id, human_decision)
       - tiếp tục graph từ điểm interrupt bằng Command(resume=...)

Ví dụ human_decision:
    {
        "approved": True,
        "reviewer": "ops_lead",
        "notes": "Đã kiểm tra, cho phép tiếp tục retrieval"
    }

Chạy thử:
    python graph.py
"""

import asyncio
import json
import os
import time
from datetime import datetime
from typing import Any, Literal, Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


# ─────────────────────────────────────────────
# 1. Shared State — dữ liệu đi xuyên toàn graph
# ─────────────────────────────────────────────

class AgentState(TypedDict):
    # Input
    task: str

    # Supervisor decisions
    route_reason: str
    risk_high: bool
    needs_tool: bool
    hitl_triggered: bool

    # Worker outputs
    retrieved_chunks: list[dict[str, Any]]
    retrieved_sources: list[str]
    policy_result: dict[str, Any]
    mcp_tools_used: list[str]

    # Human review
    human_decision: dict[str, Any]

    # Final output
    final_answer: str
    sources: list[str]
    confidence: float

    # Trace & history
    history: list[str]
    workers_called: list[str]
    supervisor_route: str
    latency_ms: Optional[int]
    run_id: str
    started_at_ms: Optional[int]

def _compute_latency_ms(state: AgentState) -> Optional[int]:
    started_at_ms = state.get("started_at_ms")
    if started_at_ms is None:
        return None
    return int(time.time() * 1000) - started_at_ms

def make_initial_state(task: str, run_id: Optional[str] = None) -> AgentState:
    """Khởi tạo state cho một run mới."""
    resolved_run_id = run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    return {
        "task": task,
        "route_reason": "",
        "risk_high": False,
        "needs_tool": False,
        "hitl_triggered": False,
        "retrieved_chunks": [],
        "retrieved_sources": [],
        "policy_result": {},
        "mcp_tools_used": [],
        "human_decision": {},
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": resolved_run_id,
        "started_at_ms": int(time.time() * 1000),
    }


# ─────────────────────────────────────────────
# 2. Supervisor Node — quyết định route
# ─────────────────────────────────────────────

def supervisor_node(state: AgentState) -> AgentState:
    task = state["task"].lower()

    history = list(state["history"])
    history.append(f"[supervisor] received task: {state['task'][:120]}")

    route = "retrieval_worker"
    route_reason = "default route: factual lookup / retrieval"
    needs_tool = False
    risk_high = False

    policy_keywords = [
        "hoàn tiền", "refund", "flash sale", "license",
        "cấp quyền", "access", "level 3", "quy trình", "policy"
    ]
    risk_keywords = [
        "emergency", "khẩn cấp", "2am", "không rõ", "err-", "sev1", "p1"
    ]

    if any(kw in task for kw in policy_keywords):
        route = "policy_tool_worker"
        route_reason = "task contains policy/access keyword"
        needs_tool = True

    if any(kw in task for kw in risk_keywords):
        risk_high = True
        route_reason += " | risk_high flagged"

    # Nếu có error code lạ hoặc tình huống khẩn/rủi ro cao -> human review
    if risk_high and "err-" in task:
        route = "human_review"
        route_reason = "unknown error code + risk_high → human review"

    history.append(f"[supervisor] route={route} reason={route_reason}")

    return {
        **state,
        "supervisor_route": route,
        "route_reason": route_reason,
        "needs_tool": needs_tool,
        "risk_high": risk_high,
        "history": history,
    }


# ─────────────────────────────────────────────
# 3. Route Decision — conditional edge
# ─────────────────────────────────────────────

def route_decision(
    state: AgentState,
) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    """
    Trả về tên worker tiếp theo dựa vào supervisor_route trong state.
    Đây là conditional edge của LangGraph.
    """
    route = state.get("supervisor_route", "retrieval_worker")
    if route in {"retrieval_worker", "policy_tool_worker", "human_review"}:
        return route
    return "retrieval_worker"


# ─────────────────────────────────────────────
# 4. Human Review Node — HITL thật bằng interrupt
# ─────────────────────────────────────────────

def human_review_node(
    state: AgentState,
) -> Command[Literal["retrieval_worker", END]]:
    """
    Pause graph để human review.
    Khi resume bằng Command(resume=...), giá trị resume sẽ trở thành kết quả của interrupt().
    """

    pre_interrupt_history = list(state["history"])
    pre_interrupt_history.append("[human_review] HITL triggered — graph paused for approval")

    interrupt_payload = {
        "type": "human_review_required",
        "run_id": state["run_id"],
        "task": state["task"],
        "reason": state["route_reason"],
        "risk_high": state["risk_high"],
        "proposed_route_after_approval": "retrieval_worker",
        "instructions": {
            "expected_schema": {
                "approved": "bool",
                "reviewer": "str",
                "notes": "str (optional)",
            }
        },
    }

    human_decision = interrupt(interrupt_payload)

    approved = bool(human_decision.get("approved", False))
    reviewer = human_decision.get("reviewer", "unknown_reviewer")
    notes = human_decision.get("notes", "")

    updated_history = list(pre_interrupt_history)
    updated_history.append(
        f"[human_review] resumed by reviewer={reviewer} approved={approved} notes={notes}"
    )

    updated_workers = list(state["workers_called"])
    updated_workers.append("human_review")

    latency_ms = _compute_latency_ms(state)

    if approved:
        return Command(
            update={
                "hitl_triggered": True,
                "human_decision": human_decision,
                "route_reason": state["route_reason"] + " | human approved → retrieval",
                "history": updated_history,
                "workers_called": updated_workers,
                "supervisor_route": "retrieval_worker",
                "latency_ms": latency_ms,
            },
            goto="retrieval_worker",
        )

    return Command(
        update={
            "hitl_triggered": True,
            "human_decision": human_decision,
            "route_reason": state["route_reason"] + " | human rejected",
            "final_answer": (
                "Yêu cầu đã bị chặn ở bước human review. "
                "Cần reviewer xử lý thủ công trước khi tiếp tục."
            ),
            "sources": [],
            "confidence": 0.2,
            "history": updated_history,
            "workers_called": updated_workers,
            "latency_ms": latency_ms,
        },
        goto=END,
    )


# ─────────────────────────────────────────────
# 5. Workers
# ─────────────────────────────────────────────

from workers.retrieval import run as retrieval_run
from workers.policy_tool import run as policy_tool_run
from workers.synthesis import run as synthesis_run


def retrieval_worker_node(state: AgentState) -> AgentState:
    return retrieval_run(state)


async def policy_tool_worker_node(state: AgentState) -> AgentState:
    return await policy_tool_run(state)


def synthesis_worker_node(state: AgentState) -> AgentState:
    result = synthesis_run(state)

    history = list(result.get("history", []))
    latency_ms = _compute_latency_ms(result)

    result["latency_ms"] = latency_ms
    history.append(f"[graph] completed in {latency_ms}ms")
    result["history"] = history

    return result


# ─────────────────────────────────────────────
# 6. Build LangGraph
# ─────────────────────────────────────────────

def build_graph():
    """
    Xây dựng LangGraph với:
      START -> supervisor
      supervisor -(conditional)-> retrieval_worker | policy_tool_worker | human_review
      policy_tool_worker -> retrieval_worker -> synthesis_worker -> END
      retrieval_worker -> synthesis_worker -> END

    HITL được implement trong human_review_node bằng interrupt().
    """

    workflow = StateGraph(AgentState)

    workflow.add_node("supervisor", supervisor_node)
    workflow.add_node("retrieval_worker", retrieval_worker_node)
    workflow.add_node("policy_tool_worker", policy_tool_worker_node)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("synthesis_worker", synthesis_worker_node)

    workflow.add_edge(START, "supervisor")

    workflow.add_conditional_edges(
        "supervisor",
        route_decision,
        {
            "retrieval_worker": "retrieval_worker",
            "policy_tool_worker": "policy_tool_worker",
            "human_review": "human_review",
        },
    )

    workflow.add_edge("policy_tool_worker", "retrieval_worker")
    workflow.add_edge("retrieval_worker", "synthesis_worker")
    workflow.add_edge("synthesis_worker", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)


# ─────────────────────────────────────────────
# 7. Public API
# ─────────────────────────────────────────────

_graph = build_graph()


async def run_graph_async(task: str, run_id: Optional[str] = None) -> AgentState:
    """
    Chạy graph từ đầu.

    Nếu graph đụng human_review_node, kết quả trả về sẽ chứa "__interrupt__".
    Để resume, dùng resume_graph(run_id, human_decision).

    Args:
        task: Câu hỏi từ user
        run_id: thread_id cho persistence; nếu None sẽ tự sinh

    Returns:
        AgentState hoặc dict có "__interrupt__" khi bị pause
    """
    state = make_initial_state(task, run_id=run_id)
    config = {"configurable": {"thread_id": state["run_id"]}}
    result = await _graph.ainvoke(state, config=config)
    return result


def run_graph(task: str, run_id: Optional[str] = None) -> AgentState:
    """Sync wrapper cho script/CLI khi graph có async node."""
    return asyncio.run(run_graph_async(task, run_id=run_id))


async def resume_graph_async(run_id: str, human_decision: dict[str, Any]) -> AgentState:
    """
    Resume một graph đã bị interrupt ở human_review_node.

    Args:
        run_id: phải đúng thread_id / run_id trước đó
        human_decision: ví dụ {"approved": True, "reviewer": "ops_lead", "notes": "ok"}

    Returns:
        AgentState sau khi graph chạy tiếp xong
    """
    config = {"configurable": {"thread_id": run_id}}
    result = await _graph.ainvoke(Command(resume=human_decision), config=config)
    return result


def resume_graph(run_id: str, human_decision: dict[str, Any]) -> AgentState:
    """Sync wrapper cho script/CLI khi graph có async node."""
    return asyncio.run(resume_graph_async(run_id, human_decision))


def _make_json_serializable(obj):
    if isinstance(obj, dict):
        return {k: _make_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_json_serializable(v) for v in obj]
    if isinstance(obj, tuple):
        return [_make_json_serializable(v) for v in obj]

    # Với object Interrupt hoặc object lạ của LangGraph
    try:
        json.dumps(obj)
        return obj
    except TypeError:
        # ưu tiên lấy value nếu có
        if hasattr(obj, "value"):
            return {
                "__type__": obj.__class__.__name__,
                "value": _make_json_serializable(obj.value),
            }
        return {
            "__type__": obj.__class__.__name__,
            "repr": repr(obj),
        }


def save_trace(state: dict, output_dir: str = "./artifacts/traces") -> str:
    os.makedirs(output_dir, exist_ok=True)
    run_id = state.get("run_id", f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}")
    filename = f"{output_dir}/{run_id}.json"

    serializable_state = _make_json_serializable(state)

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(serializable_state, f, ensure_ascii=False, indent=2)

    return filename


# ─────────────────────────────────────────────
# 8. Manual Test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("Day 09 Lab — Supervisor-Worker Graph (LangGraph + HITL)")
    print("=" * 70)

    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
        "Cần cấp quyền Level 3 để khắc phục P1 khẩn cấp với err-db-431. Quy trình là gì?",
    ]

    for query in test_queries:
        print(f"\n▶ Query: {query}")
        result = run_graph(query)

        if "__interrupt__" in result:
            run_id = result["run_id"]
            print("  Status     : INTERRUPTED")
            print(f"  Route      : {result.get('supervisor_route')}")
            print(f"  Reason     : {result.get('route_reason')}")
            print(f"  Interrupt  : {result['__interrupt__']}")

            approve_raw = input("Approve? (y/n): ").strip().lower()
            notes = input("Notes: ").strip()

            human_decision = {
                "approved": approve_raw in {"y", "yes"},
                "reviewer": "terminal_user",
                "notes": notes,
            }

            result = resume_graph(run_id, human_decision)

        print(f"  Route      : {result.get('supervisor_route')}")
        print(f"  Reason     : {result.get('route_reason')}")
        print(f"  Workers    : {result.get('workers_called')}")
        print(f"  Answer     : {result.get('final_answer', '')[:120]}...")
        print(f"  Confidence : {result.get('confidence')}")
        print(f"  Latency    : {result.get('latency_ms')}ms")

        trace_file = save_trace(result)
        print(f"  Trace saved → {trace_file}")

    print("\n✅ graph.py test complete.")

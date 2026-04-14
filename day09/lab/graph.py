"""
graph.py — Supervisor Orchestrator
Sprint 1: Implement AgentState, supervisor_node, route_decision và kết nối graph.

Kiến trúc:
    Input → Supervisor → [retrieval_worker | policy_tool_worker | human_review] → synthesis → Output

Chạy thử:
    python graph.py
"""

import json
import os
from datetime import datetime
from typing import TypedDict, Literal, Optional

# Uncomment nếu dùng LangGraph:
# from langgraph.graph import StateGraph, END

# ─────────────────────────────────────────────
# 1. Shared State — dữ liệu đi xuyên toàn graph
# ─────────────────────────────────────────────

class AgentState(TypedDict, total=False):
    # Input
    task: str                           # Câu hỏi đầu vào từ user

    # Supervisor decisions
    route_reason: str                   # Lý do route sang worker nào
    risk_high: bool                     # True → cần HITL hoặc human_review
    needs_tool: bool                    # True → cần gọi external tool qua MCP
    hitl_triggered: bool                # True → đã pause cho human review

    # Worker outputs
    retrieved_chunks: list              # Output từ retrieval_worker
    retrieved_sources: list             # Danh sách nguồn tài liệu
    policy_result: dict                 # Output từ policy_tool_worker
    mcp_tools_used: list                # Danh sách MCP tools đã gọi
    worker_io_logs: list                # Log I/O từ workers (Sprint 2+)

    # Final output
    final_answer: str                   # Câu trả lời tổng hợp
    sources: list                       # Sources được cite
    confidence: float                   # Mức độ tin cậy (0.0 - 1.0)

    # Trace & history
    history: list                       # Lịch sử các bước đã qua
    workers_called: list                # Danh sách workers đã được gọi
    supervisor_route: str               # Worker được chọn bởi supervisor
    latency_ms: Optional[int]           # Thời gian xử lý (ms)
    run_id: str                         # ID của run này


def make_initial_state(task: str) -> AgentState:
    """Khởi tạo state cho một run mới."""
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
        "worker_io_logs": [],
        "final_answer": "",
        "sources": [],
        "confidence": 0.0,
        "history": [],
        "workers_called": [],
        "supervisor_route": "",
        "latency_ms": None,
        "run_id": f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    }


# ─────────────────────────────────────────────
# 2. Supervisor Node — quyết định route
# ─────────────────────────────────────────────

def supervisor_node(state: AgentState) -> AgentState:
    """
    Supervisor phân tích task và quyết định:
    1. Route sang worker nhánh nào (retrieval vs policy vs human_review)
    2. Có cần MCP tool không (policy branch: search_kb / ticket)
    3. Gắn cờ risk_high khi ngữ cảnh nhạy cảm (HITL / trace)

    Routing theo README (thứ tự ưu tiên):
    - P1 / escalation / ticket / SLA → retrieval_worker (ưu tiên trước policy)
    - hoàn tiền / refund / policy → policy_tool_worker
    - cấp quyền / access / emergency → policy_tool_worker
    - mã lỗi ERR-… → human_review
    - mặc định → retrieval_worker
    """
    raw_task = state["task"]
    task = raw_task.lower()
    state["history"].append(f"[supervisor] received task: {raw_task[:120]}")

    sla_signals = [
        "p1", "escalation", "escalate", "ticket", "sla", "jira",
        "nhận thông báo", "deadline",
    ]
    policy_signals = [
        "hoàn tiền", "refund", "policy", "chính sách", "flash sale",
        "đổi trả", "hoàn trả",
    ]
    access_signals = [
        "cấp quyền", "access", "level 2", "level 3", "admin access",
        "contractor", "tạm thời", "temporary",
    ]
    err_code_signal = "err-"

    has_sla = any(s in task for s in sla_signals)
    has_policy = any(s in task for s in policy_signals)
    has_access = any(s in task for s in access_signals)
    has_err_code = err_code_signal in task

    risk_keywords = ["khẩn cấp", "emergency", "2am", "không rõ"]
    risk_high = any(kw in task for kw in risk_keywords) or has_err_code

    route: Literal["retrieval_worker", "policy_tool_worker", "human_review"]
    route_reason: str
    needs_tool = False

    if has_err_code:
        route = "human_review"
        route_reason = (
            "task contains error code pattern (ERR-…); route to human_review for validation"
        )
    elif has_sla:
        route = "retrieval_worker"
        route_reason = (
            "task contains P1/SLA/ticket/escalation keywords (priority over policy routing)"
        )
    elif has_policy or has_access:
        route = "policy_tool_worker"
        needs_tool = True
        if has_policy and has_access:
            route_reason = (
                "task matches policy/refund and access-related keywords → policy_tool_worker"
            )
        elif has_policy:
            route_reason = "task contains refund/policy/flash sale keywords → policy_tool_worker"
        else:
            route_reason = "task contains access/emergency/contractor keywords → policy_tool_worker"
    else:
        route = "retrieval_worker"
        route_reason = "default: factual/FAQ retrieval → retrieval_worker"

    state["supervisor_route"] = route
    state["route_reason"] = route_reason
    state["needs_tool"] = needs_tool
    state["risk_high"] = risk_high
    state["history"].append(
        f"[supervisor] route={route} route_reason={route_reason!r} risk_high={risk_high}"
    )

    return state


# ─────────────────────────────────────────────
# 3. Route Decision — conditional edge
# ─────────────────────────────────────────────

def route_decision(state: AgentState) -> Literal["retrieval_worker", "policy_tool_worker", "human_review"]:
    """
    Trả về tên worker tiếp theo dựa vào supervisor_route trong state.
    Đây là conditional edge của graph — mỗi lần gọi ghi log kèm route_reason (DoD Sprint 1).
    """
    route = state.get("supervisor_route", "retrieval_worker")
    reason = state.get("route_reason", "")
    state.setdefault("history", []).append(
        f"[route_decision] next={route} route_reason={reason!r}"
    )
    return route  # type: ignore


# ─────────────────────────────────────────────
# 4. Human Review Node — HITL placeholder
# ─────────────────────────────────────────────

def human_review_node(state: AgentState) -> AgentState:
    """
    HITL node: pause và chờ human approval.
    Trong lab này, implement dưới dạng placeholder (in ra warning).

    TODO Sprint 3 (optional): Implement actual HITL với interrupt_before hoặc
    breakpoint nếu dùng LangGraph.
    """
    state["hitl_triggered"] = True
    state["history"].append("[human_review] HITL triggered — awaiting human input")
    state["workers_called"].append("human_review")

    # Placeholder: tự động approve để pipeline tiếp tục
    print(f"\n⚠️  HITL TRIGGERED")
    print(f"   Task: {state['task']}")
    print(f"   Reason: {state['route_reason']}")
    print(f"   Action: Auto-approving in lab mode (set hitl_triggered=True)\n")

    # Sau khi human approve, route về retrieval để lấy evidence
    state["supervisor_route"] = "retrieval_worker"
    state["route_reason"] += " | human approved → retrieval"

    return state


# ─────────────────────────────────────────────
# 5. Workers — RAG Day 08 nằm ở workers/retrieval.py (Chroma + embeddings)
# ─────────────────────────────────────────────

from workers.retrieval import run as retrieval_run
from workers.policy_tool import run as policy_tool_run
from workers.synthesis import run as synthesis_run


def retrieval_worker_node(state: AgentState) -> AgentState:
    """Gọi retrieval worker (dense retrieval / Day 08 RAG)."""
    return retrieval_run(state)  # type: ignore[return-value]


def policy_tool_worker_node(state: AgentState) -> AgentState:
    """Policy + tool worker (rule/MCP); giả định đã có retrieved_chunks từ retrieval."""
    return policy_tool_run(state)  # type: ignore[return-value]


def synthesis_worker_node(state: AgentState) -> AgentState:
    """Tổng hợp câu trả lời có citation."""
    return synthesis_run(state)  # type: ignore[return-value]


def _synthesis_placeholder(state: AgentState) -> AgentState:
    """Fallback khi không gọi được synthesis (thiếu dependency)."""
    chunks = state.get("retrieved_chunks", [])
    sources = list(state.get("retrieved_sources", []))
    state["final_answer"] = (
        f"[PLACEHOLDER] Tổng hợp từ {len(chunks)} chunk(s); cài API key để bật LLM synthesis."
    )
    state["sources"] = sources
    state["confidence"] = 0.35 if chunks else 0.1
    state.setdefault("history", []).append(
        f"[synthesis_worker] placeholder answer, confidence={state['confidence']}"
    )
    return state


# ─────────────────────────────────────────────
# 6. Build Graph
# ─────────────────────────────────────────────

def build_graph():
    """
    Xây dựng graph với supervisor-worker pattern.

    Option A (đơn giản — Python thuần): Dùng if/else, không cần LangGraph.
    Option B (nâng cao): Dùng LangGraph StateGraph với conditional edges.

    Lab này implement Option A theo mặc định.
    TODO Sprint 1: Có thể chuyển sang LangGraph nếu muốn.
    """
    # Option A: Simple Python orchestrator
    def run(state: AgentState) -> AgentState:
        import time
        start = time.time()

        # Step 1: Supervisor decides route
        state = supervisor_node(state)

        # Step 2: Route to appropriate worker
        route = route_decision(state)

        if route == "human_review":
            state = human_review_node(state)
            # Sau HITL: lấy bằng chứng từ KB (RAG Day 08) rồi tổng hợp
            state = retrieval_worker_node(state)
        elif route == "policy_tool_worker":
            # Policy cần context: retrieve (Chroma) → policy/MCP → synthesis
            state = retrieval_worker_node(state)
            state = policy_tool_worker_node(state)
        else:
            # Nhánh retrieval mặc định: SLA/FAQ/…
            state = retrieval_worker_node(state)

        # Step 3: Luôn qua synthesis
        try:
            state = synthesis_worker_node(state)
        except Exception as e:
            state.setdefault("history", []).append(f"[graph] synthesis failed: {e}; using placeholder")
            state = _synthesis_placeholder(state)

        state["latency_ms"] = int((time.time() - start) * 1000)
        state["history"].append(f"[graph] completed in {state['latency_ms']}ms")
        return state

    return run


# ─────────────────────────────────────────────
# 7. Public API
# ─────────────────────────────────────────────

_graph = build_graph()


class Graph:
    """
    Wrapper có API `.invoke()` giống LangGraph (Sprint 1 DoD).
    Ví dụ: `graph.invoke({"task": "SLA P1 là bao lâu?"})`
    """

    def invoke(self, state: dict) -> AgentState:
        if not isinstance(state, dict) or "task" not in state:
            raise ValueError("invoke() cần dict có key 'task'")
        task = str(state["task"])
        return run_graph(task)


graph = Graph()


def run_graph(task: str) -> AgentState:
    """
    Entry point: nhận câu hỏi, trả về AgentState với full trace.

    Args:
        task: Câu hỏi từ user

    Returns:
        AgentState với final_answer, trace, routing info, v.v.
    """
    state = make_initial_state(task)
    result = _graph(state)
    return result


def save_trace(state: AgentState, output_dir: str = "./artifacts/traces") -> str:
    """Lưu trace ra file JSON."""
    os.makedirs(output_dir, exist_ok=True)
    filename = f"{output_dir}/{state['run_id']}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    return filename


# ─────────────────────────────────────────────
# 8. Manual Test
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Day 09 Lab — Supervisor-Worker Graph (Sprint 1)")
    print("=" * 60)

    # Hai câu khác loại: retrieval (SLA/P1) vs policy (hoàn tiền/Flash Sale) — DoD Sprint 1
    test_queries = [
        "SLA xử lý ticket P1 là bao lâu?",
        "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
    ]

    for query in test_queries:
        print(f"\n▶ Query: {query}")
        result = graph.invoke({"task": query})
        print(f"  Route   : {result['supervisor_route']}")
        print(f"  Reason  : {result['route_reason']}")
        print(f"  Workers : {result['workers_called']}")
        ans = result.get("final_answer") or ""
        preview = (ans[:200] + "…") if len(ans) > 200 else ans
        print(f"  Answer  : {preview}")
        print(f"  Confidence: {result['confidence']}")
        print(f"  Latency : {result['latency_ms']}ms")

        trace_file = save_trace(result)
        print(f"  Trace saved → {trace_file}")

    print("\n✅ Sprint 1: graph.invoke() + 2 routes (retrieval vs policy).")

"""
workers/policy_tool.py — Policy & Tool Worker
Sprint 2+3: Kiểm tra policy dựa vào context, gọi MCP tools khi cần.

Input (từ AgentState):
    - task: câu hỏi
    - retrieved_chunks: context từ retrieval_worker
    - needs_tool: True nếu supervisor quyết định cần tool call

Output (vào AgentState):
    - policy_result: {"policy_applies", "policy_name", "exceptions_found", "source", "rule"}
    - mcp_tools_used: list of tool calls đã thực hiện
    - worker_io_log: log

Gọi độc lập để test:
    python workers/policy_tool.py
"""

import asyncio
import os
import sys
from typing import Optional, Any
from fastmcp import Client
from datetime import datetime
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

WORKER_NAME = "policy_tool_worker"


# ─────────────────────────────────────────────
# MCP Client — Sprint 3: Thay bằng real MCP call
# ─────────────────────────────────────────────

async def _call_mcp_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    server_url: str = "http://127.0.0.1:8001/mcp",
    timeout: float = 10.0,
) -> dict[str, Any]:
    """
    Gọi MCP tool qua FastMCP HTTP client.
    """
    try:
        client = Client(server_url)

        async with client:
            result = await client.call_tool(
                tool_name,
                tool_input,
                timeout=timeout,
            )

        return {
            "tool": tool_name,
            "input": tool_input,
            "output": result.data,
            "error": None,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        return {
            "tool": tool_name,
            "input": tool_input,
            "output": None,
            "error": {
                "code": "MCP_CALL_FAILED",
                "reason": str(e),
            },
            "timestamp": datetime.now().isoformat(),
        }

# ─────────────────────────────────────────────
# Policy Analysis Logic
# ─────────────────────────────────────────────

POLICY_ANALYSIS_SYSTEM_PROMPT = """
Bạn là policy analyst cho hệ thống hỗ trợ khách hàng nội bộ.

Nhiệm vụ:
- Xác định policy/version nào dùng để xét case này.
- Xác định policy có áp dụng cho case này không.
- Xác định khách hàng có được hoàn tiền hay không.
- Xác định các exception nếu có.

Lưu ý rất quan trọng:
- `policy_applies` KHÔNG có nghĩa là khách hàng được hoàn tiền.
- `policy_applies` chỉ có nghĩa là case này thuộc phạm vi đánh giá của policy đó.
- `refund_allowed` mới là kết luận cuối cùng về việc có được hoàn tiền hay không.

QUY TẮC BẮT BUỘC:
1. Nếu đơn hàng thuộc Flash Sale:
   → refund_allowed = false
   → bắt buộc thêm một exception với:
      - type = "flash_sale_exception"

2. Nếu sản phẩm là digital product / license key / subscription:
   → refund_allowed = false
   → bắt buộc thêm một exception với:
      - type = "digital_product_exception"

3. Nếu sản phẩm đã kích hoạt / đã đăng ký / đã sử dụng:
   → refund_allowed = false
   → bắt buộc thêm một exception với:
      - type = "activated_exception"

4. Nếu đơn hàng trước 01/02/2026:
   → áp dụng policy v3
   → policy v3 không có trong docs hiện tại
   → phải ghi rõ trong `policy_version_note` rằng policy v3 không có trong tài liệu hiện tại
   → không được bịa nội dung chi tiết của policy v3 nếu context không cung cấp

QUY TẮC SUY LUẬN:
- Nếu case thuộc phạm vi xét của refund policy, thì `policy_applies = true`, kể cả khi `refund_allowed = false`.
- Nếu có nhiều exception cùng lúc, phải trả về đầy đủ tất cả exception tương ứng.
- Nếu không có exception nào, `exceptions_found` phải là [].
- Không được tự tạo type khác cho 3 nhóm exception bắt buộc ở trên.
- Với 3 nhóm exception bắt buộc, chỉ được dùng đúng 3 tên sau:
  - "flash_sale_exception"
  - "digital_product_exception"
  - "activated_exception"
- Không được dùng các tên gần nghĩa như:
  - "activated_product_exception"
  - "digital_exception"
  - "subscription_exception"
  - hoặc bất kỳ biến thể nào khác

RÀNG BUỘC CHẶT CHO `exceptions_found`:
- Nếu task/context cho thấy đơn hàng thuộc Flash Sale, object exception phải có:
  {
    "type": "flash_sale_exception",
    "rule": "Đơn hàng Flash Sale không được hoàn tiền.",
    "source": "<nguồn phù hợp>"
  }

- Nếu task/context cho thấy sản phẩm là digital product / license key / subscription, object exception phải có:
  {
    "type": "digital_product_exception",
    "rule": "Sản phẩm kỹ thuật số, license key, hoặc subscription không được hoàn tiền.",
    "source": "<nguồn phù hợp>"
  }

- Nếu task/context cho thấy sản phẩm đã kích hoạt / đã đăng ký / đã sử dụng, object exception phải có:
  {
    "type": "activated_exception",
    "rule": "Sản phẩm đã kích hoạt, đã đăng ký, hoặc đã sử dụng không được hoàn tiền.",
    "source": "<nguồn phù hợp>"
  }

QUY TẮC CHỌN SOURCE:
- Ưu tiên source từ context chunks.
- Nếu exception xuất hiện rõ trong task nhưng context không nêu rõ, vẫn phải kết luận theo quy tắc bắt buộc và có thể ghi source là "task".

Schema JSON:
{
  "policy_applies": boolean,
  "refund_allowed": boolean,
  "policy_name": string,
  "exceptions_found": [
    {
      "type": string,
      "rule": string,
      "source": string
    }
  ],
  "source": [string],
  "policy_version_note": string,
  "explanation": string
}

Định nghĩa:
- `policy_applies` = true nếu case này thuộc phạm vi của policy được dùng để xét.
- `refund_allowed` = true nếu theo policy và exceptions hiện có, khách hàng được hoàn tiền.
- Nếu case đang được xét bằng refund policy thì thường `policy_applies = true`, kể cả khi `refund_allowed = false`.

YÊU CẦU OUTPUT:
- Trả về đúng 1 JSON object hợp lệ.
- Không thêm markdown.
- Không thêm giải thích ngoài JSON.
- `exceptions_found[].type` phải tuân thủ tuyệt đối các tên exception bắt buộc đã nêu ở trên.
""".strip()

def analyze_policy(
    task: str,
    chunks: list[dict[str, Any]],
    model: str = "gpt-4o-mini",
    client: OpenAI | None = None,
) -> dict[str, Any]:
    if client is None:
        client = OpenAI()

    context_blocks: list[str] = []
    source_set: set[str] = set()

    for i, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("text", "")).strip()
        source = str(chunk.get("source", "unknown")).strip() or "unknown"
        score = chunk.get("score", None)

        if source:
            source_set.add(source)

        context_blocks.append(
            f"[CHUNK {i}]\n"
            f"source: {source}\n"
            f"score: {score}\n"
            f"text: {text}\n"
        )

    context_text = "\n\n".join(context_blocks) if context_blocks else "[NO CONTEXT RETRIEVED]"

    user_prompt = f"""
Task cần phân tích:
{task}

Context policy đã retrieve:
{context_text}

Hãy phân tích task chỉ dựa trên context ở trên và trả về JSON đúng schema đã yêu cầu.
""".strip()

    try:
        response = client.chat.completions.create(
            model=model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": POLICY_ANALYSIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )

        raw_content = response.choices[0].message.content or "{}"
        parsed = json.loads(raw_content)

        result = {
            "policy_applies": bool(parsed.get("policy_applies", False)),
            "policy_name": str(parsed.get("policy_name", "unknown_policy")),
            "exceptions_found": parsed.get("exceptions_found", []),
            "source": parsed.get("source", sorted(source_set)),
            "policy_version_note": str(parsed.get("policy_version_note", "")),
            "explanation": str(parsed.get("explanation", "")),
        }

        if not isinstance(result["exceptions_found"], list):
            result["exceptions_found"] = []

        if not isinstance(result["source"], list):
            result["source"] = sorted(source_set)

        return result

    except Exception as e:
        return {
            "policy_applies": False,
            "policy_name": "analysis_failed",
            "exceptions_found": [],
            "source": sorted(source_set),
            "policy_version_note": "",
            "explanation": f"LLM policy analysis failed: {e}",
        }


# ─────────────────────────────────────────────
# Worker Entry Point
# ─────────────────────────────────────────────

async def run(state: dict) -> dict:
    """
    Worker entry point — gọi từ graph.py.

    Args:
        state: AgentState dict

    Returns:
        Updated AgentState với policy_result và mcp_tools_used
    """
    task = state.get("task", "")
    chunks = state.get("retrieved_chunks", [])
    needs_tool = state.get("needs_tool", False)

    state.setdefault("workers_called", [])
    state.setdefault("history", [])
    state.setdefault("mcp_tools_used", [])

    state["workers_called"].append(WORKER_NAME)

    worker_io = {
        "worker": WORKER_NAME,
        "input": {
            "task": task,
            "chunks_count": len(chunks),
            "needs_tool": needs_tool,
        },
        "output": None,
        "error": None,
    }

    try:
        # Step 1: Nếu chưa có chunks, gọi MCP search_kb
        if not chunks and needs_tool:
            mcp_result = await _call_mcp_tool("search_kb", {"query": task, "top_k": 3})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP search_kb")

            if mcp_result.get("output") and mcp_result["output"].get("chunks"):
                chunks = mcp_result["output"]["chunks"]
                state["retrieved_chunks"] = chunks

        # Step 2: Phân tích policy
        policy_result = analyze_policy(task, chunks)
        state["policy_result"] = policy_result

        # Step 3: Nếu cần thêm info từ MCP (e.g., ticket status), gọi get_ticket_info
        if needs_tool and any(kw in task.lower() for kw in ["ticket", "p1", "jira"]):
            mcp_result = await _call_mcp_tool("get_ticket_info", {"ticket_id": "P1-LATEST"})
            state["mcp_tools_used"].append(mcp_result)
            state["history"].append(f"[{WORKER_NAME}] called MCP get_ticket_info")

        worker_io["output"] = {
            "policy_applies": policy_result["policy_applies"],
            "exceptions_count": len(policy_result.get("exceptions_found", [])),
            "mcp_calls": len(state["mcp_tools_used"]),
        }
        state["history"].append(
            f"[{WORKER_NAME}] policy_applies={policy_result['policy_applies']}, "
            f"exceptions={len(policy_result.get('exceptions_found', []))}"
        )

    except Exception as e:
        worker_io["error"] = {"code": "POLICY_CHECK_FAILED", "reason": str(e)}
        state["policy_result"] = {"error": str(e)}
        state["history"].append(f"[{WORKER_NAME}] ERROR: {e}")

    state.setdefault("worker_io_logs", []).append(worker_io)
    return state


# ─────────────────────────────────────────────
# Test độc lập
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 50)
    print("Policy Tool Worker — Standalone Test")
    print("=" * 50)

    test_cases = [
        {
            "task": "Khách hàng Flash Sale yêu cầu hoàn tiền vì sản phẩm lỗi — được không?",
            "retrieved_chunks": [
                {"text": "Ngoại lệ: Đơn hàng Flash Sale không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.9}
            ],
        },
        {
            "task": "Khách hàng muốn hoàn tiền license key đã kích hoạt.",
            "retrieved_chunks": [
                {"text": "Sản phẩm kỹ thuật số (license key, subscription) không được hoàn tiền.", "source": "policy_refund_v4.txt", "score": 0.88}
            ],
        },
        {
            "task": "Khách hàng yêu cầu hoàn tiền trong 5 ngày, sản phẩm lỗi, chưa kích hoạt.",
            "retrieved_chunks": [
                {"text": "Yêu cầu trong 7 ngày làm việc, sản phẩm lỗi nhà sản xuất, chưa dùng.", "source": "policy_refund_v4.txt", "score": 0.85}
            ],
        },
    ]

    for tc in test_cases:
        print(f"\n▶ Task: {tc['task'][:70]}...")
        result = asyncio.run(run(tc.copy()))
        pr = result.get("policy_result", {})
        print(f"  policy_applies: {pr.get('policy_applies')}")
        if pr.get("exceptions_found"):
            for ex in pr["exceptions_found"]:
                print(f"  exception: {ex['type']} — {ex['rule'][:60]}...")
        print(f"  MCP calls: {len(result.get('mcp_tools_used', []))}")

    print("\n✅ policy_tool_worker test done.")

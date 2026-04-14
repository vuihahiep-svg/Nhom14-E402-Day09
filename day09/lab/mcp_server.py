import os
import sys
from datetime import datetime
from typing import Any

from fastmcp import FastMCP

# ─────────────────────────────────────────────
# FastMCP app
# ─────────────────────────────────────────────

mcp = FastMCP(
    name="Mock IT Ops MCP Server",
    instructions=(
        "MCP server cho lab supervisor-worker graph. "
        "Cung cấp tool tra cứu KB, ticket, access control và tạo ticket mock."
    ),
)

# ─────────────────────────────────────────────
# Mock data / schemas logic
# ─────────────────────────────────────────────

MOCK_TICKETS = {
    "P1-LATEST": {
        "ticket_id": "IT-9847",
        "priority": "P1",
        "title": "API Gateway down — toàn bộ người dùng không đăng nhập được",
        "status": "in_progress",
        "assignee": "nguyen.van.a@company.internal",
        "created_at": "2026-04-13T22:47:00",
        "sla_deadline": "2026-04-14T02:47:00",
        "escalated": True,
        "escalated_to": "senior_engineer_team",
        "notifications_sent": ["slack:#incident-p1", "email:incident@company.internal", "pagerduty:oncall"],
    },
    "IT-1234": {
        "ticket_id": "IT-1234",
        "priority": "P2",
        "title": "Feature login chậm cho một số user",
        "status": "open",
        "assignee": None,
        "created_at": "2026-04-13T09:15:00",
        "sla_deadline": "2026-04-14T09:15:00",
        "escalated": False,
    },
}

ACCESS_RULES = {
    1: {
        "required_approvers": ["Line Manager"],
        "emergency_can_bypass": False,
        "note": "Standard user access",
    },
    2: {
        "required_approvers": ["Line Manager", "IT Admin"],
        "emergency_can_bypass": True,
        "emergency_bypass_note": "Level 2 có thể cấp tạm thời với approval đồng thời của Line Manager và IT Admin on-call.",
        "note": "Elevated access",
    },
    3: {
        "required_approvers": ["Line Manager", "IT Admin", "IT Security"],
        "emergency_can_bypass": False,
        "note": "Admin access — không có emergency bypass",
    },
}


def _fallback_kb_result(message: str) -> dict[str, Any]:
    return {
        "chunks": [
            {
                "text": message,
                "source": "mock_data",
                "score": 0.5,
            }
        ],
        "sources": ["mock_data"],
        "total_found": 1,
    }


# ─────────────────────────────────────────────
# MCP tools
# ─────────────────────────────────────────────

@mcp.tool
def search_kb(query: str, top_k: int = 3) -> dict[str, Any]:
    """
    Tìm kiếm Knowledge Base nội bộ bằng semantic search.
    Ưu tiên gọi workers.retrieval.retrieve_dense; nếu chưa setup thì fallback mock.
    """
    if top_k <= 0:
        return {"error": "top_k phải > 0"}

    try:
        current_dir = os.path.dirname(__file__)
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)

        from workers.retrieval import retrieve_dense  # type: ignore

        chunks = retrieve_dense(query, top_k=top_k)
        sources = list({c["source"] for c in chunks}) if chunks else []
        return {
            "chunks": chunks,
            "sources": sources,
            "total_found": len(chunks),
        }
    except Exception as e:
        return _fallback_kb_result(
            f"[MOCK] Không thể query retrieval backend: {e}. Kết quả giả lập cho query='{query}'."
        )


@mcp.tool
def get_ticket_info(ticket_id: str) -> dict[str, Any]:
    """
    Tra cứu thông tin ticket từ hệ thống mock.
    Ví dụ: P1-LATEST, IT-1234
    """
    ticket = MOCK_TICKETS.get(ticket_id.upper())
    if ticket:
        return ticket

    return {
        "error": f"Ticket '{ticket_id}' không tìm thấy trong hệ thống.",
        "available_mock_ids": list(MOCK_TICKETS.keys()),
    }


@mcp.tool
def check_access_permission(
    access_level: int,
    requester_role: str,
    is_emergency: bool = False,
) -> dict[str, Any]:
    """
    Kiểm tra điều kiện cấp quyền theo Access Control SOP.
    """
    rule = ACCESS_RULES.get(access_level)
    if not rule:
        return {"error": f"Access level {access_level} không hợp lệ. Levels: 1, 2, 3."}

    can_grant = True
    notes: list[str] = []

    if is_emergency and rule.get("emergency_can_bypass"):
        notes.append(rule.get("emergency_bypass_note", ""))
        can_grant = True
    elif is_emergency and not rule.get("emergency_can_bypass"):
        notes.append(
            f"Level {access_level} KHÔNG có emergency bypass. Phải follow quy trình chuẩn."
        )

    return {
        "access_level": access_level,
        "requester_role": requester_role,
        "can_grant": can_grant,
        "required_approvers": rule["required_approvers"],
        "approver_count": len(rule["required_approvers"]),
        "emergency_override": is_emergency and rule.get("emergency_can_bypass", False),
        "notes": notes,
        "source": "access_control_sop.txt",
    }


@mcp.tool
def create_ticket(priority: str, title: str, description: str = "") -> dict[str, Any]:
    """
    Tạo ticket mới trong hệ thống mock.
    """
    allowed_priorities = {"P1", "P2", "P3", "P4"}
    normalized_priority = priority.upper().strip()

    if normalized_priority not in allowed_priorities:
        return {
            "error": f"priority '{priority}' không hợp lệ. Allowed: {sorted(allowed_priorities)}"
        }

    mock_id = f"IT-{9900 + hash(title) % 99}"
    ticket = {
        "ticket_id": mock_id,
        "priority": normalized_priority,
        "title": title,
        "description": description[:200],
        "status": "open",
        "created_at": datetime.now().isoformat(),
        "url": f"https://jira.company.internal/browse/{mock_id}",
        "note": "MOCK ticket — không tồn tại trong hệ thống thật",
    }
    print(f"[create_ticket] MOCK created: {mock_id} | {normalized_priority} | {title[:60]}")
    return ticket


# ─────────────────────────────────────────────
# Optional local helper (không phải MCP tool)
# ─────────────────────────────────────────────

def list_local_tools() -> list[str]:
    """
    Helper cục bộ để debug nhanh từ Python.
    FastMCP client bình thường sẽ tự discover tools qua MCP protocol.
    """
    return [
        "search_kb",
        "get_ticket_info",
        "check_access_permission",
        "create_ticket",
    ]


# ─────────────────────────────────────────────
# Entrypoint
# ─────────────────────────────────────────────

if __name__ == "__main__":
    host = os.getenv("MCP_HOST", "127.0.0.1")
    port = int(os.getenv("MCP_PORT", "8001"))

    print("=" * 60)
    print("FastMCP Server — Mock IT Ops Tools")
    print("=" * 60)
    print(f"Server name : Mock IT Ops MCP Server")
    print(f"Transport   : HTTP")
    print(f"Endpoint    : http://{host}:{port}/mcp")
    print(f"Tools       : {', '.join(list_local_tools())}")
    print()

    # HTTP transport là khuyến nghị cho deployment web/service.
    mcp.run(transport="http", host=host, port=port)
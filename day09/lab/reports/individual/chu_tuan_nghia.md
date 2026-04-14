# Báo Cáo Cá Nhân - Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Chu Tuấn Nghĩa  
**Vai trò trong nhóm:** Trace & Docs Owner  
**Ngày nộp:** 2026-04-14  
**Độ dài yêu cầu:** 500-800 từ

---

## 1. Tôi phụ trách phần nào? (100-150 từ)

**Module/file tôi chịu trách nhiệm:**
- File chính: `graph.py`, `mcp_server.py`
- Functions tôi implement: `AgentState`, `make_initial_state()`, `supervisor_node()`, `route_decision()`, `human_review_node()`, `build_graph()`, `run_graph_async()`, `run_graph()`, `resume_graph_async()`, `resume_graph()`, `save_trace()` trong `graph.py`; `search_kb()`, `get_ticket_info()`, `check_access_permission()`, `create_ticket()`, `list_local_tools()` trong `mcp_server.py`; các hàm chạy và ghi trace trong `eval_trace.py` như `run_test_questions()`, `run_grading_questions()`, `analyze_traces()`, `compare_single_vs_multi()`

Tôi là người dựng lớp orchestration của hệ thống bằng **LangGraph**, tức là biến ý tưởng supervisor-worker thành graph chạy được thật với `StateGraph`, `START/END`, conditional edges và `interrupt()` cho HITL. Song song với đó, tôi dùng thư viện **FastMCP** để dựng MCP server chạy HTTP trong `mcp_server.py`, cung cấp các tool để worker khác gọi qua protocol chuẩn thay vì hard-code logic vào graph. Công việc của tôi kết nối trực tiếp với `workers/retrieval.py`, `workers/policy_tool.py`, `workers/synthesis.py` và `eval_trace.py`: graph gọi các worker, policy worker gọi MCP server, còn `eval_trace.py` dùng `run_graph()`, `resume_graph()` và `save_trace()` để chạy test và ghi lại artifacts.

**Bằng chứng (commit hash, file có comment tên bạn, v.v.):**

Commit hash tôi dùng làm bằng chứng là `90e7d10d3400ede0522942331e310fb76eb3b28e`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150-200 từ)

**Quyết định:** Tôi chọn xây graph thật bằng LangGraph + interrupt/resume, đồng thời tách tool layer ra thành MCP server HTTP bằng FastMCP thay vì nhúng tool trực tiếp vào worker.

**Lý do:**

Có hai lựa chọn tôi cân nhắc. Cách thứ nhất là viết một pipeline Python tuần tự: supervisor trả ra route string, sau đó if/else để gọi worker và gọi thẳng các hàm tool nội bộ. Cách này làm nhanh hơn trong ngắn hạn nhưng khó chứng minh Day 09 thực sự là một hệ multi-agent có state, checkpoint và HITL. Cách thứ hai là dùng LangGraph cho orchestration và FastMCP cho tool serving. Tôi chọn cách thứ hai vì nó đúng tinh thần bài lab hơn: graph có route rõ ràng, state đi xuyên suốt, hỗ trợ `interrupt()` và `Command(resume=...)`, còn MCP server dùng được qua HTTP nên worker phía policy có thể gọi tool theo kiểu service.

Trade-off tôi chấp nhận là latency và độ phức tạp code tăng. Tài liệu so sánh Day 08 vs Day 09 cho thấy latency trung bình tăng, nhưng bù lại trace rõ hơn và khả năng debug tốt hơn nhiều. Quyết định này có hiệu quả thực tế: trong trace chạy thật, `supervisor_route`, `route_reason`, `workers_called`, `mcp_tools_used` đều hiện rõ, còn ở `mcp_server.py` tôi có thể publish `search_kb`, `get_ticket_info`, `check_access_permission`, `create_ticket` bằng decorator `@mcp.tool` và chạy server bằng `mcp.run(transport="http", host=host, port=port)`.

**Trade-off đã chấp nhận:**

- Code nhiều lớp hơn single-agent.
- Phải quản lý state contract giữa graph, worker và MCP response.
- HITL muốn chạy đúng thì caller phải xử lý vòng `interrupt -> resume`, không phải chỉ viết node là xong.

**Bằng chứng từ trace/code:**

```python
# graph.py
workflow = StateGraph(AgentState)
workflow.add_conditional_edges("supervisor", route_decision, {...})
memory = MemorySaver()
return workflow.compile(checkpointer=memory)

# human_review
human_decision = interrupt(interrupt_payload)
return Command(update={...}, goto="retrieval_worker")

# mcp_server.py
from fastmcp import FastMCP
mcp = FastMCP(name="Mock IT Ops MCP Server", ...)
mcp.run(transport="http", host=host, port=port)
```

---

## 3. Tôi đã sửa một lỗi gì? (150-200 từ)

**Lỗi:** HITL trong LangGraph không tự dừng và hỏi reviewer như tôi kỳ vọng ban đầu.

**Symptom (pipeline làm gì sai?):**

Khi task có `risk_high` và chứa `err-`, supervisor đã route đúng sang `human_review`, nhưng terminal không hiện bước hỏi `Approve? (y/n)` như mong đợi. Tức là tôi thấy logic route đã đúng, nhưng trải nghiệm HITL chưa đúng: graph không “dừng để hỏi” theo kiểu blocking CLI. Nếu chỉ nhìn bên ngoài thì rất dễ tưởng `interrupt()` bị lỗi hoặc LangGraph không pause.

**Root cause (lỗi nằm ở đâu - indexing, routing, contract, worker logic?):**

Root cause nằm ở orchestration contract giữa LangGraph và lớp gọi ngoài, không nằm ở retrieval hay worker logic. Tôi hiểu sai cách hoạt động của `interrupt()`: trong LangGraph, `interrupt()` không tự gọi `input()`; nó chỉ trả về một payload `__interrupt__`. Muốn hệ thống thực sự dừng và hỏi, tôi phải có checkpointer, phải giữ `run_id/thread_id`, và phía caller phải detect `__interrupt__`, thu thập quyết định của người dùng rồi gọi lại `resume_graph()` với `Command(resume=...)`.

**Cách sửa:**

Tôi sửa ở hai lớp. Trong `graph.py`, tôi build graph với `MemorySaver()`, thêm `run_id`, `resume_graph_async()` và `resume_graph()` để graph có thể tiếp tục đúng luồng sau khi pause. Trong `eval_trace.py` và phần manual test của `graph.py`, tôi thêm nhánh kiểm tra `if "__interrupt__" in result`, sau đó mới hỏi `Approve?`, nhận `notes`, tạo `human_decision` và gọi `resume_graph(run_id, human_decision)`.

**Bằng chứng trước/sau:**
> Dán trace/log/output trước khi sửa và sau khi sửa.

Trước khi sửa, symptom là: route đã đi vào `human_review` nhưng terminal không bật bước hỏi duyệt. Sau khi sửa, luồng đúng là:

```text
Status     : INTERRUPTED
Route      : human_review
Reason     : unknown error code + risk_high -> human review
Interrupt  : ...
Approve? (y/n):
Notes:
```

Sau khi người dùng nhập quyết định, graph tiếp tục qua `resume_graph()` và trace có thêm:

```text
[human_review] HITL triggered - graph paused for approval
[human_review] resumed by reviewer=terminal_user approved=True notes=...
```

---

## 4. Tôi tự đánh giá đóng góp của mình (100-150 từ)

**Tôi làm tốt nhất ở điểm nào?**

Tôi làm tốt nhất ở phần biến kiến trúc thành hệ thống chạy được thật. Cụ thể, tôi dựng được graph có state, route, HITL, trace và persistence; đồng thời tách được MCP server riêng bằng FastMCP HTTP để các tool không bị gắn chặt vào worker.

**Tôi làm chưa tốt hoặc còn yếu ở điểm nào?**

Tôi còn chậm ở khâu chuẩn hóa contract ngay từ đầu. Ví dụ kiểu dữ liệu của `mcp_tools_used` và cách xử lý interrupt ở các script gọi chưa đồng đều, khiến về sau phải quay lại sửa ở lớp integration.

**Nhóm phụ thuộc vào tôi ở đâu?** _(Phần nào của hệ thống bị block nếu tôi chưa xong?)_

Nếu tôi chưa xong `graph.py` và `mcp_server.py` thì toàn bộ flow Day 09 bị block: worker không có orchestration layer để chạy cùng nhau, `policy_tool_worker` không có HTTP MCP endpoint để gọi, và `eval_trace.py` cũng không thể chạy đủ pipeline.

**Phần tôi phụ thuộc vào thành viên khác:** _(Tôi cần gì từ ai để tiếp tục được?)_

Tôi phụ thuộc vào việc các worker khác giữ đúng input/output contract, đặc biệt là `retrieved_chunks`, `policy_result`, `final_answer` và format source, để graph và trace của tôi phản ánh đúng hành vi thật của toàn hệ thống.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50-100 từ)

Tôi sẽ gom toàn bộ logic HITL thành một wrapper chung dùng lại cho cả `run_test_questions()` lẫn `run_grading_questions()` trong `eval_trace.py`. Lý do là hiện tại nhánh test đã xử lý `__interrupt__`, nhưng nhánh grading vẫn chưa có cùng cơ chế này. Nếu trace gặp thêm case `human_review`, hành vi giữa hai đường chạy sẽ không nhất quán. Đây là cải tiến nhỏ nhưng giảm lỗi integration rất rõ.

---

*Lưu file này với tên: `reports/individual/[ten_ban].md`*  
*Ví dụ: `reports/individual/nguyen_van_a.md`*

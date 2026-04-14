# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Hoàng Hiệp  
**Vai trò trong nhóm:** Supervisor Owner (Sprint 1 — graph & routing)  
**Ngày nộp:** 14/04/2026  
**Độ dài yêu cầu:** 500–800 từ

---

## 1. Tôi phụ trách phần nào? (100–150 từ)

**Module/file tôi chịu trách nhiệm:**
- File chính: `day09/lab/graph.py`
- Functions: `AgentState`, `make_initial_state`, `supervisor_node`, `route_decision`, `build_graph`, lớp `Graph` và `invoke`, `run_graph`. Tôi nối orchestrator với RAG Day 08 trong `workers/retrieval.py` (ChromaDB + `SentenceTransformer`), `workers/policy_tool.py`, `workers/synthesis.py`.

**Cách công việc của tôi kết nối với phần của thành viên khác:**

Supervisor chọn `retrieval_worker`, `policy_tool_worker` hoặc `human_review` (mã `ERR-…`). Nhánh policy tôi đặt là **retrieve → policy_tool → synthesis** để luôn có bằng chứng trước khi kiểm policy. Sprint sau bám `supervisor_route` và `route_reason` này cho trace.

**Bằng chứng:**

Trace: `artifacts/traces/run_20260414_122857.json` (SLA/P1 → `retrieval_worker`), `run_20260414_122915.json` (Flash Sale/hoàn tiền → `policy_tool_worker`). Chạy `python3 graph.py` trong `day09/lab` ra dòng kết `✅ Sprint 1: graph.invoke() + 2 routes`.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì? (150–200 từ)

**Quyết định:** Routing **keyword có thứ tự ưu tiên** trong `supervisor_node`: tín hiệu P1/SLA/ticket/escalation xử lý **trước** refund/policy/access, theo README (“P1 … → retrieval_worker (ưu tiên)”).

**Lý do:** Tách khỏi monolith Day 08 giúp trace biết lỗi nằm ở định tuyến hay retrieval. Không dùng LLM classify ở Sprint 1: nhanh, không tốn API, đủ cho tập từ khóa lab.

**Trade-off:** Câu mơ hồ có thể sai nhánh; sau này có thể thêm classifier.

**Bằng chứng từ trace/code:**

Câu SLA/P1: `route_reason` = `task contains P1/SLA/ticket/escalation keywords (priority over policy routing)`, `workers_called` = `['retrieval_worker', 'synthesis_worker']`. Câu hoàn tiền/Flash Sale: `route_reason` chứa `refund/policy/flash sale`, `workers_called` = `['retrieval_worker', 'policy_tool_worker', 'synthesis_worker']`. `route_decision` ghi `[route_decision] next=... route_reason='...'` vào `history`.

---

## 3. Tôi đã sửa một lỗi gì? (150–200 từ)

**Lỗi:** Collection Chroma `day09_docs` chưa được build từ `data/docs/`, nên retrieval trả về 0 chunk, `confidence` rất thấp, khó chứng minh RAG.

**Symptom:** Cảnh báo collection chưa có data; trace thiếu chunk thực từ tài liệu.

**Root cause:** Chưa chạy bước index trong `README.md` (script `python -c "..."` upsert 5 file vào `./chroma_db`).

**Cách sửa:** Chạy script index README; sau đó trace có chunk (ví dụ `sla_p1_2026.txt`), `worker_io_logs` ghi `chunks_count: 3`, confidence ước lượng cao hơn (ví dụ ~0.46 so với ~0.1 khi không có evidence).

**Trước/sau:** Trước: không chunk / cảnh báo. Sau: `run_20260414_122857.json` có `retrieved_chunks` và `sources` đầy đủ.

---

## 4. Tôi tự đánh giá đóng góp của mình (100–150 từ)

**Làm tốt:** State đủ `task`, `route_reason`, `history`, `risk_high`; API `graph.invoke({"task": ...})` tương thích kiểu LangGraph; nối `retrieval_run` thay placeholder — đúng hướng “refactor pipeline Day 08”.

**Chưa tốt:** Model embedding load lặp mỗi lần gọi worker → latency lớn; chưa có test tự động cho thứ tự routing.

**Nhóm phụ thuộc tôi:** Worker/MCP/trace cần `route_reason`/`supervisor_route` ổn định từ graph.

**Tôi phụ thuộc người khác:** Synthesis cần API key trong `.env` (nếu không sẽ `[SYNTHESIS ERROR]` dù retrieval đã có chunk).

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì? (50–100 từ)

Cache **một lần** `SentenceTransformer` và handle collection Chroma (singleton trong `retrieval` hoặc module riêng), vì trace cho thấy thời gian chủ yếu do load model lặp, không phải do supervisor — giảm `latency_ms` cho đúng hai câu hỏi Sprint 1 mà không đổi routing.

---

*File: `reports/individual/hoang_hiep.md`*

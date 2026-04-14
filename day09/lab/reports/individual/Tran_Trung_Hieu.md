# Báo Cáo Cá Nhân — Lab Day 09: Multi-Agent Orchestration

**Họ và tên:** Trần Trung Hiếu  
**Vai trò trong nhóm:** Sprint Lead 2 — Worker Owner  
**Ngày nộp:** 2026-04-14  
**Độ dài:** ~700 từ

---

## 1. Tôi phụ trách phần nào?

Tôi phụ trách **Sprint 2 — Worker Implementation**, bao gồm toàn bộ 3 workers và hệ thống contract định nghĩa giao tiếp giữa các thành phần.

**Module/file tôi chịu trách nhiệm chính:**
- `workers/retrieval.py` — Dense retrieval từ ChromaDB
- `workers/policy_tool.py` — Policy check + MCP tool integration
- `workers/synthesis.py` — LLM synthesis với grounded prompting
- `contracts/worker_contracts.yaml` — I/O contract định nghĩa interface cho toàn hệ thống

**Cách công việc kết nối với phần còn lại:**  
`AgentState` TypedDict do Sprint Lead 1 định nghĩa trong `graph.py` là ranh giới chung. Mỗi worker nhận `state: dict` và trả về `state: dict` đã được cập nhật — không ghi đè field của worker khác, chỉ append vào `workers_called`, `history`, `worker_io_logs`. Contract trong `worker_contracts.yaml` là tài liệu chính thức tôi viết để Sprint Lead 1 biết chính xác key nào sẽ có sau mỗi worker, tránh coupling ngầm.

**Bằng chứng:**  
`workers/retrieval.py` lines 97–138 (dense retrieval logic), `workers/policy_tool.py` lines 65–142 (policy analysis + exception detection), `workers/synthesis.py` lines 34–66 (LLM call với fallback chain), `contracts/worker_contracts.yaml` toàn bộ file.

---

## 2. Tôi đã ra một quyết định kỹ thuật gì?

**Quyết định:** Implement `policy_tool_worker` bằng rule-based exception detection thay vì LLM call.

**Lý do và các lựa chọn thay thế:**

Có hai phương án:
1. **LLM-based analysis** — Gọi `gpt-4o-mini` để phân tích policy từ chunks, linh hoạt hơn.
2. **Rule-based keyword matching** — Kiểm tra trực tiếp trong `task` và `context_text` bằng string match.

Tôi chọn rule-based vì:
- Policy exceptions có dạng cố định (flash_sale, digital_product, activated_product) — không cần LLM để nhận ra "Flash Sale" trong text
- Thêm 1 LLM call trong policy worker sẽ tăng latency ~3s mà không cải thiện accuracy đáng kể với dạng exception này
- Rule-based dễ test độc lập và deterministic — trace luôn reproducible

**Trade-off đã chấp nhận:**  
Câu hỏi phức tạp hơn (ví dụ: "sản phẩm từ đơn hàng đặt trước 01/02/2026 có áp dụng chính sách hoàn tiền v4 không?") không được xử lý đúng vì rule không đủ tinh tế. Tôi đã ghi rõ trong code: `# TODO Sprint 2: Gọi LLM để phân tích phức tạp hơn` và flag `policy_version_note` trong output để synthesis biết context còn thiếu.

**Bằng chứng từ code:**

```python
# workers/policy_tool.py:83-108 — rule-based exception detection
if "flash sale" in task_lower or "flash sale" in context_text:
    exceptions_found.append({
        "type": "flash_sale_exception",
        "rule": "Đơn hàng Flash Sale không được hoàn tiền (Điều 3, chính sách v4).",
        "source": "policy_refund_v4.txt",
    })
```

---

## 3. Tôi đã sửa một lỗi gì?

**Lỗi:** `workers/synthesis.py` fail với `[SYNTHESIS ERROR]` khi chạy standalone — pipeline qua `graph.py` hoạt động nhưng `python workers/synthesis.py` thì không generate được answer.

**Symptom:**  
Chạy `python workers/synthesis.py` ra `[SYNTHESIS ERROR] Không thể gọi LLM`. Không có exception nào được raise, log không có gì thêm.

**Root cause:**  
`workers/synthesis.py` không có `load_dotenv()`. Khi chạy worker độc lập (ngoài `graph.py` context), `os.getenv("OPENAI_API_KEY")` trả về `None`. `OpenAI(api_key=None)` ném `AuthenticationError`, nhưng `except Exception: pass` nuốt lỗi hoàn toàn — không có gì được in ra, pipeline âm thầm fall-through sang Gemini rồi xuống fallback string.

**Cách sửa** — 2 thay đổi:

1. Thêm `load_dotenv()` vào đầu file để worker chạy được độc lập:
```python
from dotenv import load_dotenv
load_dotenv()
```

2. Đổi `except Exception: pass` thành `except Exception as e: print(...)` để lỗi không bị nuốt:
```python
except Exception as e:
    print(f"[synthesis] OpenAI failed: {e}")
```

**Bằng chứng trước/sau:**  
Trước: output là `[SYNTHESIS ERROR] Không thể gọi LLM.`, confidence: 0.0.  
Sau: output có answer đầy đủ với citation, confidence: 0.55–0.65. Khi API key sai, in ra lỗi cụ thể `AuthenticationError` thay vì fail âm thầm.

---

## 4. Tôi tự đánh giá đóng góp của mình

**Làm tốt nhất ở điểm nào?**  
Viết `contracts/worker_contracts.yaml` trước khi implement — định nghĩa rõ từng field output, error format, và constraint. Nhờ đó Sprint Lead 1 không cần đọc code worker mới biết state sẽ có gì; `eval_trace.py` cũng tính metrics dựa chính xác vào các keys đã được contract. Constraint `"confidence < 0.4 → set hitl_triggered=True"` trong contract là nguồn dẫn đến implementation tương ứng trong `synthesis.py`.

**Làm chưa tốt ở điểm nào?**  
`retrieval_worker` dùng `path="./chroma_db"` (relative path) khiến ChromaDB không tìm được khi chạy standalone từ thư mục khác. Đáng ra phải dùng absolute path từ đầu bằng `pathlib.Path(__file__).parent.parent / "chroma_db"` — đây là lỗi cẩu thả, không phải thiếu kiến thức.

**Nhóm phụ thuộc vào tôi ở đâu?**  
Contract file — Sprint Lead 1 cần biết `policy_result` có field gì để `synthesis_worker_node` wrapper truyền đúng vào synthesis. Nếu contract sai, `graph.py` sẽ đọc key không tồn tại và crash âm thầm hoặc cho kết quả sai.

**Phần tôi phụ thuộc vào thành viên khác:**  
`AgentState` schema từ Sprint Lead 1 — tôi cần biết chính xác tên field (`retrieved_chunks`, `policy_result`, `needs_tool`) để worker đọc/ghi đúng. Nếu Sprint Lead 1 đổi tên field mà không thông báo, toàn bộ worker sẽ fail.

---

## 5. Nếu có thêm 2 giờ, tôi sẽ làm gì?

Tôi sẽ upgrade `analyze_policy()` trong `policy_tool_worker` từ rule-based sang LLM-based. Bằng chứng từ trace: câu q04 ("Sản phẩm kỹ thuật số đã kích hoạt có được hoàn tiền không?") trả về `policy_applies=False` nhưng không giải thích được *tại sao* áp dụng exception nào cho trường hợp cụ thể này — synthesis phải tự suy luận từ rule string thô. Với LLM trong policy worker, output sẽ là `explanation` tự nhiên hơn, synthesis chỉ cần format lại thay vì diễn giải rule. Code cho hướng này đã được comment sẵn tại `workers/policy_tool.py:120–131`.

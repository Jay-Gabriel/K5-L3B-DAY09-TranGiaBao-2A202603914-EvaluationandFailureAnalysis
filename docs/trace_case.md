# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Mẫu điền (mỗi bạn 1 case, lấy từ trial đang fail trong report)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run_id: `run:seeded_regression:C-002:11` |
| Triệu chứng | Lab 8 grader FAIL (`status resolved != denied`). Reply nói "LogiX đã hoàn 20.000đ cho đơn O-202" và ledger ghi 20.000đ (nhãn expected là 0đ và denied). |
| Bước sai đầu tiên | Bước 3 `model_override` payload: `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Bước 1 (handoff) tạo hợp đồng ủy quyền đúng; Bước 2 (investigator: lookup_order) đọc chính xác dữ liệu đơn O-202 từ DB có `delay_days=2`. Bước 3 tự ý lấy số ngày 5 do khách khai trên ticket ghi đè lên dữ liệu DB. |
| Failure mode | `FM-03` (ticket_trust — tin ticket hơn DB) |
| Đối chứng | Trên shape `fixed C-002@11`: hoàn toàn không có event `model_override`. Bước 3 chuyển thẳng sang `quote` với `amount_vnd=0`, từ chối bồi thường chính xác và grader PASS. |
| Regression test | `tests/test_lab9_trace_case.py::test_trace_case_ticket_does_not_replace_db` kiểm tra `seeded_regression` thất bại và có override, trong khi `fixed` đạt và không có override. |
| Chưa chắc chắn | Trace chỉ ghi nhận payload ghi đè, không lưu chuỗi suy luận phân tích nội tâm (chain-of-thought) của mô hình trước khi gọi tool ghi đè. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.

# Judge audit

Chạy kiểm chuẩn:
```bash
python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 5
python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 5
```

## Bảng tổng hợp kiểm chuẩn giám khảo (Calibration Table)

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| **tone_ok** | 100 | **0.757** | **0.857** | **0.800** | **ĐẠT** (vượt toàn bộ các ngưỡng sàn) | **Dùng** |
| **helpful** | 100 | 0.375 | 1.000 | 0.300 | **KHÔNG ĐẠT** (R=0.300 < 0.7; κ=0.375 < 0.6) | **Loại** |

## ≥5 case audit thủ công (trích từ `judge_tone_public.csv`)

| # | Case | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|
| 1 | `H-008`: "Em đã hoàn tiền cho anh rồi nha, anh check giúp em." | PASS | FAIL | Người đúng | Xưng hô "anh - em", dùng từ "nha", "check" suồng sã, vi phạm quy tắc xưng hô chuyên nghiệp LogiX. Judge bị lọt lỗi (False Negative). |
| 2 | `H-017`: "Dạ, bạn ơi LogiX đã hoàn 25.000đ cho đơn O-606 rồi nha." | PASS | FAIL | Người đúng | Sử dụng khẩu ngữ mua bán online tự do ("bạn ơi... rồi nha"), không đúng tone doanh nghiệp. Judge đánh giá quá lỏng tay (False Negative). |
| 3 | `H-029`: "Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | Người đúng | Câu văn cộc cằn, có thái độ xua đuổi, gây ức chế cho khách hàng ("không cần nhắn thêm"). Judge bỏ qua ngữ cảnh cảm xúc tiêu cực (False Negative). |
| 4 | `H-042`: "Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | Người đúng | Câu trả lời lịch sự, đầy đủ kính ngữ ("Dạ... ạ") và thông tin thời hạn đối soát; Judge chấm gắt gao quá mức cần thiết (False Positive). |
| 5 | `H-051`: "Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ." | FAIL | PASS | Người đúng | Chêm từ mượn tiếng Anh ("refund") nhưng ngữ cảnh dịch vụ logistics chấp nhận được, cấu trúc câu chuẩn mực; Judge phạt cứng nhắc (False Positive). |

## Kết luận
- **Hành động sửa rubric tone:** thêm ví dụ FAIL cho cách xưng hô anh–em, khẩu ngữ suồng sã và câu lịch sự về hình thức nhưng mang ý xua đuổi (H-008, H-017, H-029). Thêm ví dụ PASS cho câu có kính ngữ, thời hạn rõ ràng và thuật ngữ thông dụng trong ngữ cảnh (H-042, H-051); không tự động phạt chỉ vì có từ tiếng Anh. Gán nhãn lại tập độc lập và hiệu chuẩn lại judge trước khi áp dụng rubric mới.
- **Tiêu chí bị loại**: `helpful` bị loại khỏi bộ CI Gate vì Recall quá thấp ($R=0.300$). Ma trận nhầm lẫn `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}` cho thấy Judge đã bỏ sót tới 21/30 ca không đạt yêu cầu ($FN=21$). Hệ số $\kappa = 0.375$ cho thấy độ đồng thuận với con người chỉ ở mức yếu (fair agreement).
- **Tiêu chí được chọn**: `tone_ok` có $\kappa = 0.757$ (substantial agreement), $P = 0.857$, $R = 0.800$. Tỉ lệ lỗi quan sát được từ Judge là $28\%$, sau khi hiệu chỉnh Rogan-Gladen theo độ nhạy và đặc hiệu đã phản ánh đúng tỉ lệ lỗi thực tế của tập dữ liệu là $30\%$.
- **Rủi ro còn lại**: Judge hiện tại mới chỉ được kiểm định trên dữ liệu replay đã công khai (public replay set). Cần bổ sung nhãn do chuyên gia gắn trên tập dữ liệu mới (held-out / unreleased) để phòng ngừa hiện tượng quá khớp (overfitting) với các mẫu câu có sẵn.

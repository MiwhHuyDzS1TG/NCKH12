# Kiểm toán nội dung và truy vết nguồn

Nguồn khoa học chính: `presentation/BAO_CAO_NCKH12.docx`. Tất cả số liệu dưới đây đã được đối chiếu với văn bản, 5 bảng và 8 ảnh nhúng trong báo cáo. Ảnh sản phẩm ở slide 12 là `image6.png` và `image7.png` trích trực tiếp từ DOCX; ảnh có tên học sinh không được sử dụng.

| Slide | Nội dung chính | Số liệu / tuyên bố định lượng | Nguồn báo cáo | Trạng thái xác minh |
|---|---|---|---|---|
| 01 | Phạm vi DUET / SPEAK | Không có số liệu kết quả | Bìa, Tóm tắt | Đã xác minh; diễn đạt là nguyên mẫu hỗ trợ |
| 02 | Điểm nghẽn chấm thủ công | Khoảng 150 video/tuần trong kịch bản 5 lớp × 30 học sinh | Phần mở đầu, mục 1 | Đã xác minh; không suy ra số giờ tiết kiệm |
| 03 | Căn chỉnh trước khi chấm | Không có tỷ lệ kết quả | Phần mở đầu, mục 1–2 | Đã xác minh |
| 04 | Tính mới reference-aware | Sáu bước minh họa phương pháp, không phải sáu phép thử | Tóm tắt; Phần mở đầu mục 3; Chương 4.1 | Đã xác minh; không nhận tác quyền mô hình nền |
| 05 | Cấu trúc dữ liệu | 68 tổng; 50 development; 18 holdout; 12 ratings; 6 transcript; 3 P2.5 | Chương 2.1–2.3; Hình 1 | Đã xác minh; các tập không gộp |
| 06 | Pipeline Duet | Sáu bước xử lý | Chương 2.4; Hình 2 | Đã xác minh; residual chỉ hỗ trợ định vị |
| 07 | Kiến trúc kỹ thuật | React/TS; FastAPI/Python; FFmpeg/OpenCV/VAD; small.en; Fluency/MultiPA | Chương 2.5.1–2.5.4 | Đã xác minh vai trò; không đổi scorer |
| 08 | Thiết kế thực nghiệm | P1.4 N=68; ASR N=6; LOOCV N=12; P2.5 N=3; holdout N=18 chưa hoàn tất | Chương 2.6; Chương 3.1–3.4; Chương 4.2 | Đã xác minh; không tạo “accuracy AI” tổng quát |
| 09 | Khả năng căn chỉnh | 58 image + 4 audio-assisted = 62/68 = 91,2%; 6 chưa đủ điều kiện | Chương 3.1; Bảng 2 | Đã xác minh; ghi rõ không phải độ chính xác chấm nói |
| 10 | So sánh ASR | small.en 5,02%; distil-large-v3 8,69%; large-v3-turbo 8,81%; N=6 | Chương 3.2; Hình 3 | Đã xác minh; WER không phải phát âm đúng |
| 11 | Sai lệch điểm | LOOCV MAE: 0,4204 / 0,4912 / 0,5881; P2.5: 0,5133 / 0,4360 / 0,7027; same band 2/3, 2/3, 1/3; within-one 3/3, 3/3, 2/3 | Chương 3.3–3.4; Bảng 3; Hình 4 | Đã xác minh; N=3 không suy rộng |
| 12 | Sản phẩm | Không thêm score mới; ảnh giao diện thật | Chương 3.6; ảnh giao diện nhúng trong DOCX | Đã xác minh; dữ liệu nhận diện không dùng |
| 13 | Giới hạn và hướng phát triển | Một task T001; một người đánh giá có AI hỗ trợ; 18 holdout chưa kiểm định cuối | Chương 4.2–4.6; Bảng 5 | Đã xác minh; kế hoạch tách khỏi kết quả |
| 14 | Kết luận | Không có số liệu mới | Kết luận và kiến nghị | Đã xác minh; không có CEFR/IELTS/Overall |
| A01 | Công thức fluency | Ngưỡng pause khoảng 0,25 s; long pause khoảng 0,70 s | Chương 2.5.2 | Đã xác minh; mỗi feature chỉ là một phần bằng chứng |
| A02 | WER, MAE, LOOCV | Không có số liệu mới | Chương 2.6; Chương 3.2–3.4 | Đã xác minh cách diễn giải |
| A03 | Cổng an toàn và riêng tư | 5 alignment unreliable + 1 no-audio trong nhóm loại | Chương 2.8; Chương 3.1; Chương 4.1 | Đã xác minh; slide không công khai media học sinh |
| A04 | Ledger công nghệ | Không có benchmark mới | Chương 2.5.4; Tài liệu tham khảo | Đã xác minh ranh giới ownership |

## Các kiểm tra chống phóng đại

- Không có số Pearson, ICC hoặc QWK tự tạo.
- Không tuyên bố cải thiện năng lực học sinh vì chưa có nghiên cứu trước–sau.
- Không tuyên bố hệ thống tốt hơn sản phẩm khác khi chưa có đối chứng.
- Không biến ảnh Results của sản phẩm thành chứng nhận trình độ.
- Không tuyên bố holdout đã đánh giá.
- Không dùng ảnh DOCX chứa tên học sinh.


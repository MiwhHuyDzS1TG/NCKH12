# Quyết định thiết kế và kỹ thuật

## Hướng mỹ thuật

Deck dùng ngôn ngữ **bright editorial scientific**: nền trắng xanh rất nhạt, chữ serif Newsreader cho luận điểm lớn, Manrope cho nội dung và số liệu, xanh điện cho bằng chứng định lượng, cyan cho tín hiệu hỗ trợ và coral cho cảnh báo/giới hạn. Bố cục có khoảng thở lớn nhưng các slide trọng tâm có cấu trúc riêng, tránh cảm giác dashboard hoặc template card lặp lại.

Nhịp thị giác đi từ vấn đề → phương pháp → thiết kế thực nghiệm → kết quả → sản phẩm → giới hạn. Slide 09 dùng ma trận 68 điểm để thể hiện đúng mẫu số; slide 10 dùng thanh WER cùng một thang; slide 11 đặt LOOCV và P2.5 cạnh nhau nhưng kèm cảnh báo không suy rộng. Slide 12 dùng ảnh sản phẩm thật trích từ báo cáo, không dựng lại màn hình giả.

## Stack

- React 19 + TypeScript + Vite: component hóa từng slide và build cục bộ nhanh.
- GSAP: animation vào slide và fragment có cleanup, không thay đổi dữ liệu.
- Phosphor Icons: icon vector nhất quán, đóng gói trong bundle.
- Playwright: điều hướng trình duyệt, screenshot hai độ phân giải và PDF.
- CSS thuần theo design tokens: kiểm soát chính xác tỷ lệ 16:9 và print layout.

Không dùng CDN, không dùng PowerPoint làm implementation chính và không nối deck vào scorer. Project chỉ đọc nguồn báo cáo và ảnh giao diện đã có.

## Kiến trúc nội dung

`researchData.ts` chứa số liệu khoa học; `slideMeta` chứa tiêu đề, thời lượng, thông điệp, điều cần tránh và nguồn. Component slide chỉ trình bày dữ liệu đó. Cách tách này giúp test số liệu và giảm nguy cơ chỉnh một con số ở nhiều nơi.

Mỗi URL có dạng `#/sNN-fN`, vì vậy refresh và direct navigation ổn định. Print mode render mọi slide ở fragment cuối, ẩn controls và ép một slide trên một trang 16:9.

## Motion và accessibility

Animation chỉ phục vụ trình tự giải thích: pipeline đi từng nút, dot matrix hiện theo nhóm, biểu đồ mở lần lượt. `prefers-reduced-motion` tắt animation; toàn bộ nội dung vẫn hiện. Điều hướng dùng bàn phím, controls có tên truy cập, overview là dialog và màu chữ giữ tương phản cao.

## Quyết định khoa học

- Không có Overall score, CEFR, B2 hoặc IELTS.
- Không biến WER thành độ chính xác phát âm.
- Không gọi 91,2% là độ chính xác chấm nói.
- Không trộn development, P2.5 và holdout.
- Không đưa dữ liệu nhận diện học sinh lên slide.
- Các kế hoạch tương lai được ghi rõ là kế hoạch, không phải kết quả.

## Rollback

Toàn bộ implementation mới nằm dưới `presentation/duet-speak-presentation/`. Xóa hoặc bỏ qua thư mục này sẽ trả repository về đúng sản phẩm và nghiên cứu trước đó; không cần hoàn nguyên scorer, calibration hoặc dữ liệu.


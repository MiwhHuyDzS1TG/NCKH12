# Hướng dẫn trình chiếu

## Chuẩn bị trước buổi thi

1. Nhấp đúp `START_PRESENTATION.bat` khi vẫn còn kết nối Internet để chắc chắn dependencies đã được chuẩn bị.
2. Khi deck mở, bấm `F` để vào toàn màn hình và thử `→`, `←`, `O`, `N`.
3. Mở slide 12 trước một lần để kiểm tra ba ảnh sản phẩm cục bộ hiển thị rõ.
4. Giữ file `output/pdf/DUET-SPEAK-NCKH12.pdf` trên máy và một USB làm phương án dự phòng.
5. Không trình chiếu trực tiếp video hoặc âm thanh nhận diện học sinh; slide chỉ dùng ảnh giao diện đã ẩn danh trong báo cáo.

## Luồng thuyết trình đề xuất

Deck chính gồm 14 slide, thời lượng mục tiêu 10–12 phút. Dùng phím phải để lần lượt mở các fragment, không bấm liên tục quá nhanh ở slide 04, 06, 07, 08 và 09 vì mỗi bước giải thích một phần của quy trình.

Slide 12 là phần demo sản phẩm bằng ảnh giao diện thật đã có trong báo cáo. Nếu muốn mở sản phẩm đang chạy để demo trực tiếp, hãy làm việc đó ở một cửa sổ riêng; deck này không giả lập kết quả hay tình trạng kết nối.

## Phím điều khiển

| Phím | Tác dụng |
|---|---|
| `→`, `Space`, `PageDown` | Hiện fragment tiếp theo; khi đã đủ thì sang slide sau |
| `←`, `PageUp` | Lùi fragment; ở đầu slide thì quay về slide trước |
| `Home` / `End` | Đầu / cuối toàn bộ deck |
| `O` | Mở/đóng overview |
| `N` | Mở/đóng presenter notes |
| `M` | Ẩn/hiện thanh điều khiển |
| `A` | Đi thẳng tới phụ lục đầu tiên |
| `F` | Bật/tắt fullscreen |
| `Esc` | Đóng overview/notes hoặc thoát fullscreen |

## Presenter notes và overview

Presenter notes hiển thị thông điệp, thời lượng, điều cần tránh và nguồn của slide hiện tại. Overview cho phép chọn trực tiếp bất kỳ slide nào. Cả hai đều không xuất hiện trong PDF.

## Offline

Font Manrope và Newsreader, icon, ảnh sản phẩm và source code đều nằm trong project. Sau khi `node_modules` đã được chuẩn bị, launcher không cần tải nội dung từ CDN. Nếu môi trường không cho chạy Node, dùng PDF dự phòng.

## Màn hình và tỷ lệ

Deck ưu tiên 1920×1080 và đã kiểm tra ở 1366×768. Trên màn hình không đúng tỷ lệ, nội dung được letterbox để giữ 16:9 và không làm méo biểu đồ. Trình chiếu trên trình duyệt ở zoom 100%.

## Thông điệp an toàn cần giữ nguyên

- 91,2% là tỷ lệ video căn chỉnh đủ điều kiện, không phải độ chính xác chấm nói.
- 5,02% là WER trên 6 bản chép người xác nhận, không phải tỷ lệ phát âm đúng.
- P2.5 chỉ có 3 bài, không đủ để suy rộng.
- 18 video holdout chưa được dùng cho kiểm định cuối theo báo cáo.
- AI hỗ trợ đo lường; giáo viên giữ vai trò đánh giá.


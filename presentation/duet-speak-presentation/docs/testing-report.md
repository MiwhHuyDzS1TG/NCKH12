# Báo cáo kiểm thử

Trạng thái cuối cùng được cập nhật sau khi chạy build, unit, browser, screenshot và PDF QA.

## Phạm vi

- TypeScript và production build.
- Unit test cho điều hướng và bất biến dữ liệu khoa học.
- Playwright cho direct route, fragments, overview và print mode.
- Screenshot toàn bộ 18 slide ở 1920×1080 và 1366×768.
- Console error capture ở cả hai độ phân giải.
- PDF 16:9, một slide/trang, không có controls.
- Visual QA cho typography tiếng Việt, overflow, chart labels, ảnh sản phẩm và cảnh báo khoa học.

## Kết quả

Kết quả lệnh cuối cùng sẽ được ghi tại đây trong vòng verification cuối.

## Vấn đề/giới hạn đã biết

- PDF là bản dự phòng tĩnh: mọi fragment được mở hoàn chỉnh và không có animation.
- Fullscreen API cần hành động bàn phím/click của người dùng theo quy định trình duyệt.
- Deck không tự mở sản phẩm NCKH12; slide 12 trình bày ảnh giao diện thật từ báo cáo để giữ an toàn và hoạt động offline.
- Kiểm thử không tuyên bố thành công cho TikTok import hoặc ChatGPT authorization thật; hai việc đó nằm ngoài phạm vi presentation.


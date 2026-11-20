# DUET / SPEAK — Bài trình bày nghiên cứu tương tác

Đây là thành phẩm trình chiếu chính của báo cáo NCKH12. Bài trình bày là một web deck React/TypeScript tỷ lệ 16:9, hoạt động cục bộ, có điều hướng bàn phím, animation theo từng bước, overview, presenter notes và phụ lục kỹ thuật. PDF trong `output/` chỉ là bản dự phòng được xuất từ chính web deck.

## Mở nhanh trên Windows

Nhấp đúp `START_PRESENTATION.bat`. Trình duyệt sẽ tự mở tại slide đầu tiên. Sau khi chuẩn bị lần đầu, toàn bộ font và ảnh đều nằm cục bộ nên không cần Internet để trình chiếu.

## Chạy bằng dòng lệnh

Yêu cầu Node.js 20+ và Corepack.

```powershell
corepack pnpm install
corepack pnpm dev --host 127.0.0.1 --port 4173
```

Mở `http://127.0.0.1:4173/#/s01-f0`.

## Điều khiển chính

- `→` hoặc `Space`: hiện bước tiếp theo / sang slide sau.
- `←`: quay lại bước trước / slide trước.
- `Home`, `End`: đầu / cuối deck.
- `O`: tổng quan tất cả slide.
- `N`: ghi chú người thuyết trình.
- `M`: ẩn/hiện thanh điều khiển.
- `A`: chuyển tới phụ lục.
- `F`: toàn màn hình.

URL lưu cả slide và fragment, ví dụ `#/s04-f3`, nên có thể tải lại hoặc mở trực tiếp mà không mất vị trí.

## Build, kiểm thử và xuất bản dự phòng

```powershell
corepack pnpm build
corepack pnpm test
corepack pnpm test:e2e
corepack pnpm capture
corepack pnpm export:pdf
```

- Screenshot kiểm tra: `screenshots/1920x1080/` và `screenshots/1366x768/`.
- Contact sheet: `screenshots/contact-sheet-1920.png` và `screenshots/contact-sheet-1366.png`.
- PDF dự phòng: `output/pdf/DUET-SPEAK-NCKH12.pdf`.

## Phạm vi khoa học

Bài trình bày không thay đổi scorer, calibration, holdout hay sản phẩm thi đã khóa. Các con số được lấy từ `BAO_CAO_NCKH12.docx`; nguồn chi tiết có trong `docs/content-audit.md`. Deck không tuyên bố CEFR/IELTS, không đưa ra điểm tổng hợp và không diễn giải 91,2% hoặc WER như độ chính xác chấm nói.

## Tài liệu bàn giao

- `docs/presentation-guide.md`: hướng dẫn trình chiếu và xử lý sự cố.
- `docs/speaker-notes.md`: kịch bản 14 slide, mục tiêu 11 phút 15 giây.
- `docs/content-audit.md`: truy vết nội dung và số liệu.
- `docs/design-decisions.md`: kiến trúc và quyết định thiết kế.
- `docs/testing-report.md`: kiểm thử, ảnh kiểm tra và giới hạn.


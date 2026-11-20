# Speaker notes — 14 slide chính

Thời lượng mục tiêu: **11 phút 15 giây**. Phần phụ lục chỉ dùng khi hội đồng hỏi.

## Slide 01 — Mở đầu · 0:25

**Thông điệp:** DUET / SPEAK là nguyên mẫu hỗ trợ đánh giá luyện nói từ video tham chiếu, không thay giáo viên.

“Bài toán của nhóm bắt đầu từ một dạng bài quen thuộc: học sinh xem video mẫu rồi quay Duet để luyện nói. DUET / SPEAK giúp biến video đó thành bằng chứng có thể kiểm tra, để giáo viên phản hồi nhanh và có căn cứ hơn.”

**Nhấn mạnh:** “hỗ trợ đánh giá”. **Tránh:** gọi đây là hệ thống chấm trình độ chính thức.

## Slide 02 — Bài toán thực tiễn · 0:40

**Thông điệp:** 150 video mỗi tuần tạo ra điểm nghẽn phản hồi thủ công.

“Nếu năm lớp, mỗi lớp khoảng ba mươi học sinh cùng nộp bài, giáo viên có thể phải xử lý khoảng 150 video một tuần. Mỗi bài đều cần mở video, tìm đoạn học sinh nói, đối chiếu mẫu, nghe chỗ dừng và viết phản hồi. Nhóm tập trung tự động hóa phần đo đạc lặp lại; giáo viên vẫn quyết định nhận xét sư phạm.”

**Tránh:** tự quy đổi 150 video thành số giờ tiết kiệm khi chưa đo.

## Slide 03 — Vấn đề và mục tiêu · 0:40

**Thông điệp:** Phải tìm đúng lời học sinh trước khi đánh giá.

“Video Duet có thể chứa giọng mẫu, nhạc và lời học sinh. Vì vậy, việc đầu tiên không phải là chấm, mà là đặt đúng video Duet vào trục thời gian của video mẫu, xác định vùng học sinh nói, rồi mới trích bằng chứng. Ba mục tiêu là căn chỉnh, định vị và tạo bằng chứng có thể kiểm tra.”

**Tránh:** coi mọi tiếng nói trong Duet là lời học sinh.

## Slide 04 — Điểm mới · 1:00

**Thông điệp:** Video tham chiếu đã biết là tín hiệu tổ chức toàn pipeline.

“Nếu bỏ qua video mẫu, hệ thống phải suy đoán nguồn giọng từ một tín hiệu hỗn hợp. Cách của nhóm là tận dụng video mẫu đã biết. Quy trình đi từ video mẫu và video Duet, căn chỉnh hai trục thời gian, tìm vùng lời học sinh, rồi quay lại âm thanh gốc để lấy bằng chứng và phản hồi. Điểm đóng góp nằm ở reference-aware alignment, bảo toàn âm thanh gốc cho đánh giá và cơ chế người kiểm tra khi đầu vào thiếu tin cậy.”

**Tránh:** tuyên bố nhóm tạo ra Whisper hoặc một mô hình nền mới.

## Slide 05 — Dữ liệu nghiên cứu · 0:35

**Thông điệp:** Mỗi tập dữ liệu trả lời một câu hỏi riêng.

“Nghiên cứu có 68 video Duet cho bài T001: 50 video phát triển và 18 video giữ riêng. Bên trong development có các tập nhỏ: 12 đánh giá tiêu chí, 6 bản chép tham chiếu cho ASR và 3 bài kiểm tra P2.5. Các tập này không được gộp thành một kết quả chung.”

**Tránh:** nói holdout đã được đánh giá cuối.

## Slide 06 — Quy trình xử lý · 1:05

**Thông điệp:** Sáu bước tạo bằng chứng từ video đã quay.

“Đầu vào là Duet đã hoàn thành. Hệ thống căn chỉnh với video mẫu, dùng VAD cùng tín hiệu giảm ảnh hưởng mẫu để tìm lời học sinh, rồi lấy lại đúng đoạn từ âm thanh gốc. Trên âm thanh gốc đó, hệ thống chạy ASR và các phân tích tiêu chí, cuối cùng trả kết quả và gợi ý. Cancellation chỉ hỗ trợ phát hiện; không dùng âm thanh residual để chấm. Nếu đầu vào thiếu tin cậy, hệ thống cảnh báo hoặc chuyển người nghe kiểm tra.”

**Tránh:** nói âm thanh cancellation là nguồn điểm.

## Slide 07 — Kiến trúc kỹ thuật · 0:55

**Thông điệp:** Frontend trình bày; backend Python giữ pipeline chấm.

“Lớp trải nghiệm dùng React và TypeScript. FastAPI điều phối sang backend Python. FFmpeg, OpenCV và VAD xử lý tín hiệu; faster-whisper small.en tạo transcript; Fluency và MultiPA tạo bằng chứng theo tiêu chí. Nhóm xây pipeline, tích hợp, kiểm soát đầu vào, hiệu chỉnh và giao diện; các mô hình có sẵn được dùng trong phạm vi giới hạn.”

**Tránh:** mô tả frontend là nơi tính điểm.

## Slide 08 — Thiết kế thực nghiệm · 0:55

**Thông điệp:** Không có một con số “accuracy AI” tổng quát.

“P1.4 hỏi có căn chỉnh được không trên 68 video. P2.4 hỏi transcript lệch bao nhiêu trên 6 bản chép người xác nhận. LOOCV hỏi điểm máy lệch bao nhiêu trên 12 bài development. P2.5 hỏi cấu hình đã khóa duy trì ra sao trên 3 bài. Cuối cùng vẫn còn 18 bài giữ riêng chưa dùng. Mỗi phép thử trả lời một câu hỏi khác nhau.”

**Tránh:** cộng hoặc trung bình bốn phép thử thành một accuracy.

## Slide 09 — Kết quả căn chỉnh · 0:45

**Thông điệp:** 62/68 video đủ điều kiện xử lý tiếp.

“Trong khảo sát kỹ thuật, 58 video căn chỉnh bằng hình ảnh và 4 video cần âm thanh hỗ trợ, tổng cộng 62 trên 68, tương đương 91,2%. Sáu video chưa đủ điều kiện gồm năm trường hợp căn chỉnh không tin cậy và một trường hợp không có luồng âm thanh. Đây là tỷ lệ căn chỉnh, không phải độ chính xác chấm phát âm hay chấm nói.”

## Slide 10 — Kết quả ASR · 0:45

**Thông điệp:** small.en có WER thấp nhất trong phép đo này.

“Trên sáu bản chép tham chiếu do con người xác nhận, small.en đạt WER 5,02%, thấp hơn distil-large-v3 là 8,69% và large-v3-turbo là 8,81%. Vì vậy nhóm chọn small.en cho cấu hình hiện tại. WER đo sai khác bản chép; 5,02% không có nghĩa là 94,98% phát âm đúng.”

## Slide 11 — Đối chiếu điểm · 0:55

**Thông điệp:** Sai lệch được đo theo tiêu chí, nhưng mẫu còn nhỏ.

“Trong LOOCV với 12 bài development, MAE lần lượt là 0,4204 cho độ trôi chảy, 0,4912 cho phát âm và 0,5881 cho ngữ điệu. Ở P2.5 với 3 bài, các giá trị là 0,5133; 0,4360; và 0,7027. Với ba bài, hai tiêu chí có hai trên ba trường hợp cùng mức, còn ngữ điệu một trên ba. Quy mô này chưa đủ để suy rộng hoặc dùng tương quan làm bằng chứng thống kê.”

**Tránh:** diễn giải chênh lệch hai cột như cải thiện theo thời gian.

## Slide 12 — Sản phẩm và demo · 1:15

**Thông điệp:** Luồng thật đi từ video đến bằng chứng và gợi ý luyện tiếp.

“Đây là ảnh giao diện thật được lưu trong báo cáo. Người dùng chọn Duet đã hoàn thành; hệ thống kiểm tra đầu vào và phân tích cục bộ; kết quả hiển thị bằng chứng theo từng tiêu chí, transcript và gợi ý. Dữ liệu demo được ẩn danh, media không được gửi tới dịch vụ chấm bên ngoài. Khi demo trực tiếp, nhóm chỉ trình bày kết quả đã được pipeline thật tạo ra, không giả trạng thái phân tích hay kết nối.”

## Slide 13 — Giới hạn và hướng đi · 0:45

**Thông điệp:** Nguyên mẫu có bằng chứng bước đầu, chưa sẵn sàng cho chấm chính thức.

“Phạm vi hiện tại là một bài đọc T001, dữ liệu nhỏ, điểm tham chiếu chưa đa dạng và chủ yếu từ một người đánh giá có AI hỗ trợ. Kiểm định cuối trên 18 bài giữ riêng chưa hoàn tất. Bước tiếp theo là khóa phương pháp rồi kiểm định holdout, có nhiều giáo viên chấm độc lập, nhiều bài đọc và nghiên cứu trước–sau. Đây là kế hoạch, không phải kết quả đã có.”

## Slide 14 — Kết luận · 0:35

**Thông điệp:** AI hỗ trợ đo lường; giáo viên giữ vai trò đánh giá.

“Nhóm đã xây một quy trình phù hợp với video Duet, tạo bằng chứng có thể nghe lại và đặt giới hạn rõ khi dữ liệu không đủ tin cậy. Kết quả hiện tại là một nguyên mẫu hoạt động và một nền tảng cho kiểm định tiếp theo. AI hỗ trợ đo lường; giáo viên vẫn là người đánh giá.”

## Phụ lục Q&A

- **A01:** công thức Speech Rate, Articulation Rate, Phonation Ratio, Pause Ratio và Mean Length of Run.
- **A02:** phân biệt WER, MAE và LOOCV.
- **A03:** các cổng an toàn, quyền từ chối chấm và nguyên tắc không công khai dữ liệu nhận diện.
- **A04:** vai trò các công nghệ và ranh giới đóng góp của nhóm.


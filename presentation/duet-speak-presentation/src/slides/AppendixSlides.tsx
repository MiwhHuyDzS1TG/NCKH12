import { useRef } from 'react';
import { CheckCircle, LockKey, ShieldCheck, ShieldWarning } from '@phosphor-icons/react';
import { SlideFrame } from '../components/SlideFrame';
import type { SlideProps } from '../data/slides';
import { useSlideMotion } from '../hooks/useSlideMotion';

export function Appendix01({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="a01" section="Phụ lục kỹ thuật" source="Chương 2.5.2.">
      <div className="appendix-heading" data-enter><h2>Các chỉ số mô tả độ trôi chảy</h2><p>Mỗi chỉ số chỉ phản ánh một phần của nhịp nói.</p></div>
      <div className="formula-grid" data-enter>
        <div className="formula-card"><span>Speech Rate</span><strong>60 × N<sub>w</sub> / T</strong><small>số từ trên toàn lượt nói</small></div>
        <div className="formula-card"><span>Articulation Rate</span><strong>60 × N<sub>w</sub> / T<sub>s</sub></strong><small>số từ trên thời gian có tiếng nói</small></div>
        <div className="formula-card"><span>Phonation Ratio</span><strong>T<sub>s</sub> / T</strong><small>tỷ lệ thời gian có tiếng nói</small></div>
        <div className="formula-card"><span>Pause Ratio</span><strong>T<sub>p</sub> / T</strong><small>tỷ lệ thời gian dừng</small></div>
        <div className="formula-card"><span>Mean Length of Run</span><strong>N<sub>w</sub> / N<sub>runs</sub></strong><small>số từ trung bình giữa các khoảng dừng</small></div>
      </div>
      <p className="scientific-caption centered">Khoảng dừng được xét từ khoảng 0,25 giây. Khoảng dừng dài từ khoảng 0,70 giây.</p>
    </SlideFrame>
  );
}

export function Appendix02({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="a02" section="Phụ lục diễn giải" source="Chương 2.6; Chương 3.2-3.4.">
      <div className="appendix-heading" data-enter><h2>Ba chỉ số, ba câu hỏi khác nhau</h2></div>
      <div className="metric-definitions" data-enter>
        <div><strong>WER</strong><h3>Bản chép tự động lệch bao nhiêu?</h3><p>Tính từ thay thế, thêm và bỏ từ so với bản chép do người xác nhận.</p></div>
        <div><strong>MAE</strong><h3>Điểm máy lệch trung bình bao nhiêu?</h3><p>Khoảng cách tuyệt đối giữa dự đoán và đánh giá tham chiếu.</p></div>
        <div><strong>LOOCV</strong><h3>Cách quy đổi hoạt động ra sao trên development?</h3><p>Mỗi lượt xây từ 11 bài rồi dự đoán cho bài còn lại.</p></div>
      </div>
      <div className="interpretation-rule"><ShieldWarning /><span>Không chuyển WER thành độ chính xác phát âm. Không coi LOOCV là kiểm định độc lập.</span></div>
    </SlideFrame>
  );
}

export function Appendix03({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="a03" section="Phụ lục an toàn" source="Chương 2.8; Chương 3.1; Chương 4.1.">
      <div className="appendix-heading" data-enter><h2>Từ chối chấm cũng là một kết quả an toàn.</h2></div>
      <div className="safety-gates" data-enter>
        <div><ShieldWarning /><strong>Không có âm thanh</strong><span>Dừng xử lý</span></div>
        <div><ShieldWarning /><strong>Căn chỉnh thiếu tin cậy</strong><span>Yêu cầu kiểm tra</span></div>
        <div><ShieldWarning /><strong>Giọng mẫu hoặc nhạc lớn</strong><span>Chuyển người nghe</span></div>
        <div><CheckCircle /><strong>Đầu vào đủ điều kiện</strong><span>Phân tích có giới hạn</span></div>
      </div>
      <div className="privacy-band"><LockKey /><div><strong>Dữ liệu học sinh được mã hóa bằng mã bài khi báo cáo.</strong><span>Không trình chiếu công khai gương mặt, giọng nói hoặc đường dẫn nhận diện.</span></div></div>
    </SlideFrame>
  );
}

export function Appendix04({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="a04" section="Phụ lục công nghệ" source="Chương 2.5.4; Tài liệu tham khảo.">
      <div className="appendix-heading" data-enter><h2>Công nghệ được tích hợp theo vai trò rõ ràng</h2></div>
      <div className="tech-ledger" data-enter>
        <div><span>Video và tín hiệu</span><strong>FFmpeg, OpenCV, NumPy, SciPy</strong></div>
        <div><span>Phát hiện lời nói</span><strong>Silero VAD, WebRTC AEC3</strong></div>
        <div><span>Nhận dạng</span><strong>faster-whisper small.en</strong></div>
        <div><span>Phát âm và ngữ điệu</span><strong>MultiPA pretrained</strong></div>
        <div><span>Sản phẩm</span><strong>React, TypeScript, FastAPI, Python</strong></div>
      </div>
      <div className="ownership-note"><ShieldCheck /><span>Nhóm xây dựng pipeline, tích hợp, kiểm soát đầu vào, hiệu chỉnh và giao diện. Nhóm không tự nhận đã tạo ra Whisper hoặc MultiPA.</span></div>
    </SlideFrame>
  );
}

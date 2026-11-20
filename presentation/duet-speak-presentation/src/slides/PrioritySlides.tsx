import { useRef } from 'react';
import {
  ArrowDown, ArrowRight, Brain, Check, Cpu, FileAudio, FilmStrip,
  Gauge, Headphones, LockKey, MagnifyingGlass, Microphone, ShieldWarning,
  Sparkle, UserFocus, Waveform,
} from '@phosphor-icons/react';
import { Fragment, SlideFrame } from '../components/SlideFrame';
import { researchData } from '../data/researchData';
import type { SlideProps } from '../data/slides';
import { useSlideMotion } from '../hooks/useSlideMotion';

const innovationSteps = ['Video mẫu đã biết', 'Video Duet', 'Căn chỉnh', 'Vùng lời học sinh', 'Âm thanh gốc', 'Bằng chứng + phản hồi'];

export function Slide04({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s04" section="Điểm mới và tính sáng tạo" source="Tóm tắt; Phần mở đầu, mục 3; Chương 4.1.">
      <div className="slide-heading compact" data-enter>
        <h2>Không đoán tất cả từ đầu. Hệ thống khai thác <em>video tham chiếu đã biết.</em></h2>
      </div>
      <div className="innovation-compare" data-enter>
        <div className="baseline-side">
          <p>Không tận dụng tham chiếu</p>
          <div className="mixed-signal"><Waveform /><span>Âm thanh hỗn hợp</span></div>
          <ArrowDown />
          <div className="uncertain-node"><MagnifyingGlass /><span>Phải suy đoán nguồn giọng</span></div>
          <small>Minh họa khác biệt phương pháp, không phải hệ đối chứng thực nghiệm.</small>
        </div>
        <div className="innovation-side">
          <div className="innovation-flow">
            {innovationSteps.map((step, index) => (
              <Fragment key={step} step={index + 1} current={fragment} className={`innovation-node node-${index + 1}`}>
                <span>{index + 1}</span><strong>{step}</strong>
                {index < innovationSteps.length - 1 && <ArrowRight />}
              </Fragment>
            ))}
          </div>
          <div className="innovation-principles">
            <span>Reference-aware alignment</span><span>Original audio preservation</span><span>Human-in-the-loop</span>
          </div>
        </div>
      </div>
    </SlideFrame>
  );
}

const pipelineSteps = [
  { label: 'Nhận video', detail: 'Duet đã hoàn thành', icon: FilmStrip },
  { label: 'Căn chỉnh', detail: 'so với video mẫu', icon: UserFocus },
  { label: 'Tìm lời học sinh', detail: 'VAD + giảm ảnh hưởng mẫu', icon: Microphone },
  { label: 'Lấy âm thanh gốc', detail: 'theo mốc thời gian', icon: FileAudio },
  { label: 'Phân tích', detail: 'ASR + tiêu chí nói', icon: Brain },
  { label: 'Trả kết quả', detail: 'bằng chứng + gợi ý', icon: Gauge },
];

export function Slide06({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s06" section="Quy trình xử lý video Duet" source="Chương 2.4; Hình 2.">
      <div className="slide-heading compact" data-enter><h2>Từ video đã quay đến phản hồi luyện tập có căn cứ.</h2></div>
      <div className="pipeline-stage" data-enter>
        <div className="pipeline-line" />
        {pipelineSteps.map(({ label, detail, icon: Icon }, index) => (
          <Fragment key={label} step={index + 1} current={fragment} className={`pipeline-node pipeline-${index + 1}`}>
            <div className="node-orbit"><Icon weight="duotone" /></div>
            <span>{String(index + 1).padStart(2, '0')}</span><strong>{label}</strong><small>{detail}</small>
          </Fragment>
        ))}
        <div className="pipeline-signal" style={{ '--step': Math.max(1, fragment) } as React.CSSProperties} />
      </div>
      <div className="pipeline-detail">
        <span><b>{fragment || 1}</b> {pipelineSteps[Math.max(0, fragment - 1)]?.detail ?? pipelineSteps[0].detail}</span>
        <div className="review-branch"><ShieldWarning /><strong>Đầu vào thiếu tin cậy</strong><ArrowRight /><span>Cảnh báo hoặc người nghe kiểm tra</span></div>
      </div>
      <p className="scientific-caption centered">Cancellation chỉ hỗ trợ phát hiện. Phân tích tiêu chí quay lại âm thanh gốc.</p>
    </SlideFrame>
  );
}

const architectureLayers = [
  { name: 'Trải nghiệm', tech: 'React 19 + TypeScript', detail: 'chọn video, xem kết quả', icon: Sparkle },
  { name: 'Điều phối', tech: 'FastAPI + Python', detail: 'kết nối pipeline', icon: Cpu },
  { name: 'Tín hiệu', tech: 'FFmpeg + OpenCV + VAD', detail: 'căn chỉnh và định vị lời', icon: Waveform },
  { name: 'Nhận dạng', tech: 'faster-whisper small.en', detail: 'transcript và timestamp', icon: Headphones },
  { name: 'Phân tích', tech: 'Fluency + MultiPA', detail: 'đặc trưng và điểm sơ bộ', icon: Brain },
];

export function Slide07({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s07" section="Phương pháp kỹ thuật và kiến trúc" source="Chương 2.5.1-2.5.4.">
      <div className="architecture-layout">
        <div className="architecture-copy" data-enter>
          <h2>Một pipeline, nhiều lớp bằng chứng.</h2>
          <p>Frontend hiển thị và tương tác. Toàn bộ thuật toán chấm chạy trong backend Python.</p>
          <div className="architecture-legend"><span>Nhóm xây dựng và tích hợp</span><span>Mô hình có sẵn, dùng có giới hạn</span></div>
        </div>
        <div className="architecture-stack" data-enter>
          {architectureLayers.map(({ name, tech, detail, icon: Icon }, index) => (
            <Fragment key={name} step={index + 1} current={fragment} className="architecture-layer">
              <Icon weight="duotone" /><div><span>{name}</span><strong>{tech}</strong><small>{detail}</small></div>
              {index < architectureLayers.length - 1 && <ArrowDown className="layer-arrow" />}
            </Fragment>
          ))}
          <div className="data-pulse" style={{ '--layer': Math.max(1, fragment) } as React.CSSProperties} />
        </div>
      </div>
    </SlideFrame>
  );
}

const experiments = [
  { code: 'P1.4', question: 'Có căn chỉnh được không?', data: '68 video', metric: '58 + 4 = 62 dùng được' },
  { code: 'P2.4', question: 'Chép lời sai bao nhiêu?', data: '6 bản chép', metric: 'WER' },
  { code: 'LOOCV', question: 'Điểm máy lệch bao nhiêu?', data: '12 bài phát triển', metric: 'MAE từng tiêu chí' },
  { code: 'P2.5', question: 'Cấu hình khóa duy trì ra sao?', data: '3 bài', metric: 'MAE + mức lệch' },
];

export function Slide08({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s08" section="Thiết kế thực nghiệm và kiểm định" source="Chương 2.6; Chương 3.1-3.4; Chương 4.2.">
      <div className="slide-heading compact" data-enter><h2>Mỗi phép thử kiểm chứng một câu hỏi khác nhau.</h2></div>
      <div className="validation-map" data-enter>
        {experiments.map((experiment, index) => (
          <Fragment key={experiment.code} step={index + 1} current={fragment} className="experiment-block">
            <span>{experiment.code}</span><h3>{experiment.question}</h3>
            <div><b>{experiment.data}</b><small>{experiment.metric}</small></div>
          </Fragment>
        ))}
        <Fragment step={5} current={fragment} className="holdout-gate">
          <LockKey weight="duotone" /><div><span>KIỂM ĐỊNH CUỐI</span><strong>18 bài giữ riêng</strong><small>Chưa hoàn tất theo báo cáo hiện tại</small></div>
        </Fragment>
      </div>
      <p className="scientific-caption centered">Không có một con số “độ chính xác AI” tổng quát được suy ra từ bốn phép thử này.</p>
    </SlideFrame>
  );
}

export function Slide09({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  const dots = Array.from({ length: researchData.dataset.total }, (_, index) => index);
  return (
    <SlideFrame ref={ref} id="s09" section="Kết quả căn chỉnh video" source="Chương 3.1; Bảng 2.">
      <div className="alignment-results">
        <div className="alignment-hero" data-enter>
          <span className="hero-percent">91,2<small>%</small></span>
          <h2>video căn chỉnh đủ điều kiện sử dụng</h2>
          <p>62 trên 68 video trong khảo sát kỹ thuật P1.4.</p>
        </div>
        <div className="dot-matrix" data-enter aria-label="68 video: 58 căn chỉnh bằng hình ảnh, 4 nhờ âm thanh, 6 chưa đủ điều kiện">
          {dots.map((dot) => {
            const visible = fragment >= (dot < 58 ? 2 : dot < 62 ? 3 : 4);
            const kind = dot < 58 ? 'image-dot' : dot < 62 ? 'audio-dot' : 'fail-dot';
            return <i key={dot} className={`${kind} ${visible ? 'dot-visible' : ''}`} />;
          })}
          <div className="matrix-legend"><span><i className="image-dot" />58 hình ảnh</span><span><i className="audio-dot" />4 âm thanh hỗ trợ</span><span><i className="fail-dot" />6 chưa đủ điều kiện</span></div>
        </div>
        <Fragment step={5} current={fragment} className="alignment-equation"><b>58</b><span>+</span><b>4</b><span>=</span><strong>62 / 68</strong></Fragment>
      </div>
      <p className="result-warning">91,2% là tỷ lệ căn chỉnh video, không phải độ chính xác chấm phát âm hoặc chấm nói.</p>
    </SlideFrame>
  );
}

export function Slide10({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s10" section="Kết quả nhận dạng giọng nói" source="Chương 3.2; Hình 3.">
      <div className="chart-heading" data-enter><div><h2>small.en có WER thấp nhất.</h2><p>6 bản chép tham chiếu do con người xác nhận.</p></div><span>WER (%)<small>thấp hơn là tốt hơn</small></span></div>
      <div className="wer-chart" data-enter>
        {researchData.asr.map((item, index) => (
          <Fragment key={item.model} step={index + 1} current={fragment} className={`wer-row ${item.selected ? 'selected' : ''}`}>
            <strong>{item.model}</strong>
            <div className="wer-scale"><i style={{ '--value': item.wer / 10 } as React.CSSProperties} /></div>
            <b>{item.wer.toFixed(2).replace('.', ',')}%</b>
            {item.selected && <span><Check /> đã chọn</span>}
          </Fragment>
        ))}
        <div className="chart-axis"><span>0</span><span>2</span><span>4</span><span>6</span><span>8</span><span>10%</span></div>
      </div>
      <Fragment step={4} current={fragment} className="interpretation-band">
        <strong>5,02% WER</strong><span>không đồng nghĩa</span><strong>94,98% phát âm đúng</strong>
      </Fragment>
    </SlideFrame>
  );
}

export function Slide11({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s11" section="Đối chiếu điểm máy và người đánh giá" source="Chương 3.3-3.4; Bảng 3; Hình 4.">
      <div className="score-eval-heading" data-enter><h2>Sai lệch đã được đo theo từng tiêu chí.</h2><p>Thang 5 mức. Bằng chứng hiện vẫn ở quy mô nhỏ.</p></div>
      <div className="mae-compare" data-enter>
        <div className="mae-title"><span>Tiêu chí</span><span>Development / LOOCV <b>N = 12</b></span><span>Small validation / P2.5 <b>N = 3</b></span></div>
        {researchData.scoring.loocv.map((item, index) => {
          const p25 = researchData.scoring.p25.find((value) => value.criterion === item.criterion)!;
          return (
            <Fragment key={item.criterion} step={index + 1} current={fragment} className="mae-row">
              <strong>{item.criterion}</strong>
              <div className="mae-value loocv-value"><i style={{ '--value': item.mae / 0.8 } as React.CSSProperties} /><b>{item.mae.toFixed(2).replace('.', ',')}</b></div>
              <div className="mae-value p25-value"><i style={{ '--value': p25.mae / 0.8 } as React.CSSProperties} /><b>{p25.mae.toFixed(2).replace('.', ',')}</b><small>cùng mức {p25.sameBand}</small></div>
            </Fragment>
          );
        })}
      </div>
      <Fragment step={4} current={fragment} className="sample-warning"><ShieldWarning /><strong>N = 3 không đủ để suy rộng.</strong><span>Không dùng tương quan trên ba bài làm bằng chứng thống kê.</span></Fragment>
      <p className="scientific-caption centered">Hai nhóm bài và cách đánh giá khác nhau, nên không suy ra chất lượng tăng hoặc giảm theo thời gian.</p>
    </SlideFrame>
  );
}

export function Slide12({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s12" section="Sản phẩm DUET / SPEAK" source="Chương 3.6; ảnh giao diện thật trong báo cáo.">
      <div className="product-showcase">
        <div className="product-heading" data-enter><h2>Một luồng sử dụng rõ ràng, từ video đến bằng chứng.</h2><p>Dữ liệu demo ẩn danh. Không gửi media tới dịch vụ chấm bên ngoài.</p></div>
        <div className="browser-frame" data-enter>
          <div className="browser-top"><span /><span /><span /><b>DUET / SPEAK</b></div>
          <img src="./images/product-home.png" alt="Trang chủ thật của sản phẩm DUET / SPEAK" />
        </div>
        <div className="product-states" data-enter>
          <Fragment step={1} current={fragment} className="product-state active-state"><span>01</span><strong>Chọn Duet</strong><small>video đã hoàn thành</small></Fragment>
          <Fragment step={2} current={fragment} className="product-state"><span>02</span><strong>Phân tích cục bộ</strong><small>kiểm tra đầu vào trước</small></Fragment>
          <Fragment step={3} current={fragment} className="product-state"><span>03</span><strong>Xem bằng chứng</strong><small>tiêu chí, transcript, gợi ý</small></Fragment>
        </div>
        <Fragment step={3} current={fragment} className="results-preview">
          <img src="./images/product-results.png" alt="Màn hình kết quả thật với bốn tiêu chí của DUET / SPEAK" />
        </Fragment>
      </div>
    </SlideFrame>
  );
}

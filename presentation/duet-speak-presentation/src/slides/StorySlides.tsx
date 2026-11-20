import { useRef } from 'react';
import { ArrowRight, CheckCircle, Clock, MicrophoneStage, ShieldCheck, VideoCamera } from '@phosphor-icons/react';
import { Fragment, SlideFrame } from '../components/SlideFrame';
import { researchData } from '../data/researchData';
import type { SlideProps } from '../data/slides';
import { useSlideMotion } from '../hooks/useSlideMotion';

const manualTasks = ['Mở video', 'Tìm đoạn nói', 'Đối chiếu mẫu', 'Nghe chỗ dừng', 'Viết phản hồi'];

export function Slide01({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s01" section="Báo cáo nghiên cứu" className="opening-slide">
      <div className="opening-grid">
        <div className="opening-copy" data-enter>
          <p className="opening-product">DUET <span>/</span> SPEAK</p>
          <h1>Đánh giá luyện nói từ <em>video tham chiếu.</em></h1>
          <p className="opening-subtitle">Phần mềm hỗ trợ đánh giá luyện nói tiếng Anh đa phương thức, với bằng chứng giọng nói có thể kiểm tra.</p>
        </div>
        <div className="signal-composition" aria-label="Minh họa hai luồng âm thanh được căn chỉnh" data-enter>
          <div className="signal-label reference-label">VIDEO MẪU</div>
          <div className="signal signal-a">{Array.from({ length: 34 }, (_, i) => <i key={i} style={{ '--h': `${22 + ((i * 17) % 58)}%` } as React.CSSProperties} />)}</div>
          <div className="alignment-plane"><span /><span /><span /><span /><strong>ALIGN</strong></div>
          <div className="signal signal-b">{Array.from({ length: 34 }, (_, i) => <i key={i} style={{ '--h': `${18 + ((i * 23) % 70)}%` } as React.CSSProperties} />)}</div>
          <div className="signal-label learner-label">VIDEO DUET</div>
        </div>
      </div>
      <div className="opening-meta" data-enter>
        <span>{researchData.project.school}</span>
        <span>{researchData.project.competition}</span>
        <span>{researchData.project.year}</span>
      </div>
    </SlideFrame>
  );
}

export function Slide02({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s02" section="Bối cảnh" source="Phần mở đầu, mục 1.">
      <div className="content-grid problem-layout">
        <div className="problem-number" data-enter>
          <span className="big-number">150</span>
          <strong>video / tuần</strong>
          <p>Một giáo viên có thể phải mở, nghe, đối chiếu và phản hồi.</p>
        </div>
        <div className="manual-flow" data-enter>
          <h2>Khi số bài tăng, phản hồi thủ công trở thành điểm nghẽn.</h2>
          <div className="task-stream">
            {manualTasks.map((task, index) => (
              <Fragment key={task} step={Math.min(index + 1, 3)} current={fragment} className="task-item">
                <span>{String(index + 1).padStart(2, '0')}</span><strong>{task}</strong>{index < manualTasks.length - 1 && <ArrowRight />}
              </Fragment>
            ))}
          </div>
          <p className="scientific-caption">Dự án tự động hóa phần đo đạc lặp lại. Giáo viên vẫn quyết định nhận xét sư phạm.</p>
        </div>
      </div>
    </SlideFrame>
  );
}

export function Slide03({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s03" section="Vấn đề và mục tiêu" source="Phần mở đầu, mục 1-2.">
      <div className="slide-heading" data-enter>
        <h2>Muốn đánh giá lời học sinh, trước hết phải biết <em>học sinh nói ở đâu.</em></h2>
      </div>
      <div className="timeline-visual" data-enter>
        <div className="timeline-row"><span>Video mẫu</span><div className="track reference-track"><i /><i /><i /></div></div>
        <div className="timeline-row"><span>Video Duet</span><div className="track duet-track"><i /><i /><i /><i /></div></div>
        <Fragment step={1} current={fragment} className="timeline-row"><span>Lời học sinh</span><div className="track learner-track"><i /><i /><i /></div></Fragment>
        <div className="timeline-axis"><span>00:00</span><span>00:30</span><span>01:00</span><span>01:30</span></div>
      </div>
      <div className="objective-line" data-enter>
        <Fragment step={1} current={fragment}><strong>Căn chỉnh</strong><span>đặt đúng tương quan thời gian</span></Fragment>
        <Fragment step={2} current={fragment}><strong>Định vị</strong><span>tìm vùng lời học sinh</span></Fragment>
        <Fragment step={3} current={fragment}><strong>Bằng chứng</strong><span>đo, cảnh báo và phản hồi</span></Fragment>
      </div>
    </SlideFrame>
  );
}

export function Slide05({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  const d = researchData.dataset;
  return (
    <SlideFrame ref={ref} id="s05" section="Dữ liệu nghiên cứu" source="Chương 2.1-2.3; Hình 1.">
      <div className="slide-heading compact" data-enter>
        <h2>Một bộ dữ liệu. Nhiều tập bằng chứng, mỗi tập trả lời một câu hỏi.</h2>
      </div>
      <div className="dataset-composition" data-enter>
        <div className="dataset-total"><span>{d.total}</span><strong>video Duet</strong><small>T001, hai lớp 10 Toán và 10 Lý</small></div>
        <div className="split-block development"><span>{d.development}</span><strong>phát triển và thử nghiệm</strong></div>
        <div className="split-block holdout"><span>{d.holdout}</span><strong>giữ riêng</strong><small>chưa kiểm định cuối</small></div>
        <Fragment step={1} current={fragment} className="evidence-chip ratings"><b>12</b><span>đánh giá tiêu chí</span></Fragment>
        <Fragment step={2} current={fragment} className="evidence-chip asr"><b>6</b><span>bản chép tham chiếu</span></Fragment>
        <Fragment step={3} current={fragment} className="evidence-chip validation"><b>3</b><span>kiểm tra P2.5</span></Fragment>
      </div>
      <p className="scientific-caption centered">Development, P2.5 và holdout không được gộp thành một tập kết quả.</p>
    </SlideFrame>
  );
}

export function Slide13({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s13" section="Hạn chế và hướng phát triển" source="Chương 4.2-4.6; Bảng 5.">
      <div className="slide-heading compact" data-enter><h2>Nguyên mẫu đã có bằng chứng bước đầu. Việc kiểm định vẫn phải đi tiếp.</h2></div>
      <div className="limits-layout" data-enter>
        <Fragment step={1} current={fragment} className="limits-column current">
          <span className="column-mark"><Clock /></span>
          <h3>Giới hạn hiện tại</h3>
          <ul>
            <li>Một bài đọc T001</li><li>Dữ liệu nhỏ, điểm ít đa dạng</li><li>Một người đánh giá có AI hỗ trợ</li><li>Chưa có kiểm định cuối trên 18 bài giữ riêng</li>
          </ul>
        </Fragment>
        <Fragment step={2} current={fragment} className="limits-column next">
          <span className="column-mark"><ArrowRight /></span>
          <h3>Bước nghiên cứu tiếp theo</h3>
          <ul>
            <li>Kiểm định tập giữ riêng sau khi khóa phương pháp</li><li>Nhiều giáo viên chấm độc lập</li><li>Nhiều bài đọc và điều kiện thu âm</li><li>Nghiên cứu trước - sau về hiệu quả giáo dục</li>
          </ul>
        </Fragment>
      </div>
      <p className="status-note"><ShieldCheck /> Các mục bên phải là kế hoạch, chưa phải kết quả đã hoàn thành.</p>
    </SlideFrame>
  );
}

export function Slide14({ active, fragment }: SlideProps) {
  const ref = useRef<HTMLElement>(null);
  useSlideMotion(ref, active, fragment);
  return (
    <SlideFrame ref={ref} id="s14" section="Kết luận" source="Kết luận và kiến nghị.">
      <div className="closing-layout">
        <div className="closing-statement" data-enter>
          <p>DUET / SPEAK</p>
          <h2>AI hỗ trợ đo lường.<br /><em>Giáo viên giữ vai trò đánh giá.</em></h2>
        </div>
        <Fragment step={1} current={fragment} className="contribution-strip">
          <div><VideoCamera /><strong>Quy trình phù hợp Duet</strong></div>
          <div><MicrophoneStage /><strong>Bằng chứng có thể nghe lại</strong></div>
          <div><CheckCircle /><strong>Đánh giá có giới hạn rõ</strong></div>
        </Fragment>
        <Fragment step={2} current={fragment} className="closing-tagline">Một nguyên mẫu hoạt động. Một quy trình minh bạch. Một nền tảng cho kiểm định tiếp theo.</Fragment>
      </div>
    </SlideFrame>
  );
}

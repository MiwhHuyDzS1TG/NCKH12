import type { SlideMeta } from '../data/slides';

export function Overview({ slides, onSelect, onClose }: { slides: SlideMeta[]; onSelect: (index: number) => void; onClose: () => void }) {
  return (
    <div className="overview" role="dialog" aria-modal="true" aria-label="Tổng quan các slide">
      <header>
        <div>
          <p>Tổng quan bài trình bày</p>
          <h2>Chọn một slide để tiếp tục</h2>
        </div>
        <button type="button" onClick={onClose}>Đóng</button>
      </header>
      <div className="overview-grid">
        {slides.map((slide, index) => (
          <button key={slide.id} type="button" className={'appendix' in slide && slide.appendix ? 'appendix-card' : ''} onClick={() => onSelect(index)}>
            <span>{slide.id.toUpperCase()}</span>
            <strong>{slide.title}</strong>
            <small>{slide.section}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

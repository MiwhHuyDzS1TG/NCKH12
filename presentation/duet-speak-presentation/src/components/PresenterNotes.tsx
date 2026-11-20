import type { SlideMeta } from '../data/slides';

export function PresenterNotes({ slide, onClose }: { slide: SlideMeta; onClose: () => void }) {
  return (
    <aside className="presenter-notes" aria-label="Ghi chú người trình bày">
      <div className="notes-head"><strong>{slide.title}</strong><button type="button" onClick={onClose}>Đóng</button></div>
      <dl>
        <div><dt>Thông điệp</dt><dd>{slide.message}</dd></div>
        <div><dt>Thời lượng</dt><dd>{slide.duration}</dd></div>
        <div><dt>Cần tránh</dt><dd>{slide.avoid}</dd></div>
        <div><dt>Nguồn</dt><dd>{slide.source}</dd></div>
      </dl>
    </aside>
  );
}

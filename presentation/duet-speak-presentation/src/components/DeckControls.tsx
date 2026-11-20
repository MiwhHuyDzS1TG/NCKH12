import { ArrowsOut, CaretLeft, CaretRight, GridFour, ListBullets, NotePencil } from '@phosphor-icons/react';

type ControlsProps = {
  index: number;
  total: number;
  onPrevious: () => void;
  onNext: () => void;
  onOverview: () => void;
  onFullscreen: () => void;
  onNotes: () => void;
  onAppendix: () => void;
};

export function DeckControls(props: ControlsProps) {
  return (
    <nav className="deck-controls" aria-label="Điều khiển trình chiếu">
      <button type="button" onClick={props.onPrevious} aria-label="Trang trước"><CaretLeft weight="bold" /></button>
      <span className="deck-counter">{String(props.index + 1).padStart(2, '0')} / {String(props.total).padStart(2, '0')}</span>
      <button type="button" onClick={props.onNext} aria-label="Trang sau"><CaretRight weight="bold" /></button>
      <span className="control-rule" />
      <button type="button" onClick={props.onOverview} aria-label="Tổng quan"><GridFour /></button>
      <button type="button" onClick={props.onNotes} aria-label="Ghi chú người trình bày"><NotePencil /></button>
      <button type="button" onClick={props.onAppendix} aria-label="Mở phụ lục"><ListBullets /></button>
      <button type="button" onClick={props.onFullscreen} aria-label="Toàn màn hình"><ArrowsOut /></button>
    </nav>
  );
}

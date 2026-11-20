import { forwardRef, type ReactNode } from 'react';

type SlideFrameProps = {
  id: string;
  section: string;
  title?: string;
  children: ReactNode;
  className?: string;
  source?: string;
};

export const SlideFrame = forwardRef<HTMLElement, SlideFrameProps>(
  ({ id, section, title, children, className = '', source }, ref) => (
    <section ref={ref} className={`slide ${className}`} data-slide-id={id} aria-label={title ?? section}>
      <div className="slide-chrome">
        <span className="slide-brand">DUET<span>/</span>SPEAK</span>
        <span className="slide-section">{section}</span>
      </div>
      {children}
      {source && <p className="slide-source">Nguồn: {source}</p>}
    </section>
  ),
);

SlideFrame.displayName = 'SlideFrame';

export function Fragment({ step, current, children, className = '' }: { step: number; current: number; children: ReactNode; className?: string }) {
  return (
    <div className={`${className} fragment ${current >= step ? 'is-visible' : ''}`} aria-hidden={current < step}>
      {children}
    </div>
  );
}

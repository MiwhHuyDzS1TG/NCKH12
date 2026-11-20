import { useCallback, useEffect, useMemo, useState } from 'react';
import { slides } from '../data/slides';
import { mainSlideCount } from '../data/researchData';
import { DeckControls } from '../components/DeckControls';
import { Overview } from '../components/Overview';
import { PresenterNotes } from '../components/PresenterNotes';
import { locationHash, nextLocation, parseDeckLocation, previousLocation, type DeckLocation } from './navigation';

const printMode = new URLSearchParams(window.location.search).has('print');

export function App() {
  const [location, setLocation] = useState<DeckLocation>(() => parseDeckLocation(window.location.hash, slides));
  const [overview, setOverview] = useState(false);
  const [notes, setNotes] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);

  const move = useCallback((next: DeckLocation) => {
    setLocation(next);
    window.history.replaceState(null, '', locationHash(slides, next));
  }, []);
  const next = useCallback(() => move(nextLocation(slides, location)), [location, move]);
  const previous = useCallback(() => move(previousLocation(slides, location)), [location, move]);
  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) {
      void document.exitFullscreen?.();
    } else {
      void document.documentElement.requestFullscreen?.();
    }
  }, []);

  useEffect(() => {
    if (!window.location.hash) window.history.replaceState(null, '', locationHash(slides, location));
  }, [location]);

  useEffect(() => {
    const syncFromHash = () => setLocation(parseDeckLocation(window.location.hash, slides));
    window.addEventListener('hashchange', syncFromHash);
    return () => window.removeEventListener('hashchange', syncFromHash);
  }, []);

  useEffect(() => {
    if (printMode) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) return;
      if (event.key === 'ArrowRight' || event.key === ' ' || event.key === 'PageDown') { event.preventDefault(); next(); }
      if (event.key === 'ArrowLeft' || event.key === 'PageUp') { event.preventDefault(); previous(); }
      if (event.key === 'Home') move({ slide: 0, fragment: 0 });
      if (event.key === 'End') move({ slide: mainSlideCount - 1, fragment: slides[mainSlideCount - 1].maxFragment });
      if (event.key.toLowerCase() === 'o') setOverview((value) => !value);
      if (event.key.toLowerCase() === 'n') setNotes((value) => !value);
      if (event.key.toLowerCase() === 'm') setControlsVisible((value) => !value);
      if (event.key.toLowerCase() === 'a') move({ slide: mainSlideCount, fragment: 0 });
      if (event.key.toLowerCase() === 'f') toggleFullscreen();
      if (event.key === 'Escape') { setOverview(false); setNotes(false); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [move, next, previous, toggleFullscreen]);

  const current = slides[location.slide];
  const progress = useMemo(() => ((location.slide + 1) / slides.length) * 100, [location.slide]);

  if (printMode) {
    return (
      <main className="print-deck">
        {slides.map((slide) => {
          const Component = slide.component;
          return <Component key={slide.id} active fragment={slide.maxFragment} print />;
        })}
      </main>
    );
  }

  return (
    <main className="deck-shell">
      <div className="deck-stage">
        {slides.map((slide, index) => {
          const Component = slide.component;
          const active = index === location.slide;
          return (
            <div key={slide.id} className={`slide-slot ${active ? 'is-active' : ''}`} aria-hidden={!active}>
              <Component active={active} fragment={active ? location.fragment : 0} />
            </div>
          );
        })}
      </div>
      {controlsVisible && (
        <DeckControls
          index={location.slide}
          total={slides.length}
          onPrevious={previous}
          onNext={next}
          onOverview={() => setOverview(true)}
          onFullscreen={toggleFullscreen}
          onNotes={() => setNotes((value) => !value)}
          onAppendix={() => move({ slide: mainSlideCount, fragment: 0 })}
        />
      )}
      {overview && <Overview slides={slides} onClose={() => setOverview(false)} onSelect={(slide) => { move({ slide, fragment: 0 }); setOverview(false); }} />}
      {notes && <PresenterNotes slide={current} onClose={() => setNotes(false)} />}
      <div className="progress-line" style={{ width: `${progress}%` }} aria-hidden="true" />
    </main>
  );
}

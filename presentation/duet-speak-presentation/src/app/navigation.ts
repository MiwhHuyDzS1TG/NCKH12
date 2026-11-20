import type { SlideMeta } from '../data/slides';

export type DeckLocation = { slide: number; fragment: number };

export function parseDeckLocation(hash: string, slides: SlideMeta[]): DeckLocation {
  const match = hash.match(/^#\/?([sa]\d{2})(?:-f(\d+))?$/i);
  if (!match) return { slide: 0, fragment: 0 };
  const slide = Math.max(0, slides.findIndex((item) => item.id === match[1].toLowerCase()));
  const max = slides[slide]?.maxFragment ?? 0;
  return { slide, fragment: Math.min(Number(match[2] ?? 0), max) };
}

export function locationHash(slides: SlideMeta[], location: DeckLocation) {
  const current = slides[location.slide] ?? slides[0];
  return `#/${current.id}-f${location.fragment}`;
}

export function nextLocation(slides: SlideMeta[], location: DeckLocation): DeckLocation {
  const current = slides[location.slide];
  if (location.fragment < current.maxFragment) {
    return { ...location, fragment: location.fragment + 1 };
  }
  return { slide: Math.min(location.slide + 1, slides.length - 1), fragment: 0 };
}

export function previousLocation(slides: SlideMeta[], location: DeckLocation): DeckLocation {
  if (location.fragment > 0) return { ...location, fragment: location.fragment - 1 };
  const slide = Math.max(0, location.slide - 1);
  return { slide, fragment: slides[slide].maxFragment };
}

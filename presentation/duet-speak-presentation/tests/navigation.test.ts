import { describe, expect, it } from 'vitest';
import { locationHash, nextLocation, parseDeckLocation, previousLocation } from '../src/app/navigation';
import { slides } from '../src/data/slides';

describe('slide navigation', () => {
  it('parses direct slide and fragment navigation', () => {
    expect(parseDeckLocation('#/s04-f3', slides)).toEqual({ slide: 3, fragment: 3 });
  });

  it('advances through fragments before the next slide', () => {
    expect(nextLocation(slides, { slide: 3, fragment: 2 })).toEqual({ slide: 3, fragment: 3 });
    expect(nextLocation(slides, { slide: 3, fragment: 6 })).toEqual({ slide: 4, fragment: 0 });
  });

  it('returns to the final fragment of the previous slide', () => {
    expect(previousLocation(slides, { slide: 4, fragment: 0 })).toEqual({ slide: 3, fragment: 6 });
  });

  it('keeps a stable URL hash', () => {
    expect(locationHash(slides, { slide: 9, fragment: 4 })).toBe('#/s10-f4');
  });
});

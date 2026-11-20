import { useLayoutEffect, type RefObject } from 'react';
import { gsap } from 'gsap';

export function useSlideMotion(
  scope: RefObject<HTMLElement | null>,
  active: boolean,
  fragment: number,
) {
  useLayoutEffect(() => {
    if (!active || !scope.current) return;
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const context = gsap.context(() => {
      const enter = gsap.utils.toArray<HTMLElement>('[data-enter]');
      gsap.fromTo(
        enter,
        { opacity: 0, y: 22 },
        { opacity: 1, y: 0, duration: 0.72, stagger: 0.07, ease: 'power3.out' },
      );
    }, scope);
    return () => context.revert();
  }, [active, fragment, scope]);
}

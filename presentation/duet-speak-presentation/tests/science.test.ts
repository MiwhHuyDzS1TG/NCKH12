import { describe, expect, it } from 'vitest';
import { researchData, slideMeta } from '../src/data/researchData';

describe('scientific data integrity', () => {
  it('preserves the reported dataset split', () => {
    expect(researchData.dataset.development + researchData.dataset.holdout).toBe(researchData.dataset.total);
    expect(researchData.dataset).toMatchObject({ total: 68, development: 50, holdout: 18 });
  });

  it('preserves alignment arithmetic', () => {
    expect(researchData.alignment.image + researchData.alignment.audioAssisted).toBe(researchData.alignment.usable);
    expect(researchData.alignment.usable + researchData.alignment.notEligible).toBe(researchData.dataset.total);
  });

  it('selects the measured lowest WER backend', () => {
    const selected = researchData.asr.find((item) => item.selected);
    expect(selected?.model).toBe('small.en');
    expect(selected?.wer).toBe(Math.min(...researchData.asr.map((item) => item.wer)));
  });

  it('contains 14 main slides and four appendix slides', () => {
    expect(slideMeta.filter((slide) => !('appendix' in slide))).toHaveLength(14);
    expect(slideMeta.filter((slide) => 'appendix' in slide)).toHaveLength(4);
  });
});

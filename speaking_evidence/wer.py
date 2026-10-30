"""Auditable word-error counts against an explicitly human-corrected reference."""
from __future__ import annotations

import re

FILLERS = {"um", "uh", "erm", "er", "hmm"}


def words_for_wer(text: str) -> list[str]:
    """Ignore case and punctuation only; do not repair grammar or repetitions."""
    return re.sub(r"[^\w\s]", "", text.casefold(), flags=re.UNICODE).split()


def word_error_counts(reference: str, hypothesis: str) -> dict:
    ref, hyp = words_for_wer(reference), words_for_wer(hypothesis)
    # Each cell carries cost plus S/I/D counts. A stable tie order makes audit reproducible.
    dp = [[(0, 0, 0, 0) for _ in range(len(hyp) + 1)] for _ in range(len(ref) + 1)]
    for i in range(1, len(ref) + 1):
        dp[i][0] = (i, 0, 0, i)
    for j in range(1, len(hyp) + 1):
        dp[0][j] = (j, 0, j, 0)
    for i in range(1, len(ref) + 1):
        for j in range(1, len(hyp) + 1):
            prior = dp[i-1][j-1]
            if ref[i-1] == hyp[j-1]:
                dp[i][j] = prior
                continue
            substitute = (prior[0] + 1, prior[1] + 1, prior[2], prior[3])
            prior_insert = dp[i][j-1]
            insert = (prior_insert[0] + 1, prior_insert[1], prior_insert[2] + 1, prior_insert[3])
            prior_delete = dp[i-1][j]
            delete = (prior_delete[0] + 1, prior_delete[1], prior_delete[2], prior_delete[3] + 1)
            dp[i][j] = min((substitute, insert, delete), key=lambda item: item[0])
    errors, substitutions, insertions, deletions = dp[-1][-1]
    return {"reference_words": len(ref), "hypothesis_words": len(hyp),
            "substitutions": substitutions, "insertions": insertions, "deletions": deletions,
            "word_count_difference": len(hyp) - len(ref),
            "wer": errors / len(ref) if ref else None,
            "reference_filler_words": sum(w in FILLERS for w in ref),
            "hypothesis_filler_words": sum(w in FILLERS for w in hyp)}

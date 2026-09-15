# Contamination review

This review is post-sealing: no gold patch, test patch, hint, or evaluator label is used during generation.
The heuristic below is a review worksheet; final classification requires human judgment.

| Instance | Reference category | Custom category | Evidence note |
|---|---|---|---|
| sphinx-doc__sphinx-8551 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom failed on tool validation after 3 turns. No solution exposure. |
| django__django-11999 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom failed on tool validation after 5 turns. No solution exposure. |
| django__django-11815 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom exhausted loop after 7 turns. No solution exposure. |
| django__django-12304 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom failed on tool validation after 3 turns. No solution exposure. |
| django__django-12273 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom failed on output parse error after 10 turns. No solution exposure. |
| django__django-12262 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom halted by Groq 8k TPM rate limit after 10 turns. No solution exposure. |
| django__django-12039 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom failed on output parse error after 3 turns. No solution exposure. |
| django__django-11964 | no specific memorization signal | no specific memorization signal | Both arms produced empty patches. Reference exited without diff; Custom failed on tool validation after 8 turns. No solution exposure. |

Categories: no specific memorization signal; suspected memorization; confirmed procedural exposure; inconclusive.

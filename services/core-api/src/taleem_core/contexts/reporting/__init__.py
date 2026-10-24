"""Reporting context: issued report cards (REPORT_CARD_CONTRACT.md, doc 29 §2-§3 and §5).

A report card is an immutable, issued snapshot for one learner, one class and one period. Every
figure on it is derived, at the moment of issue, from records that already exist elsewhere: the
learning context's assessment evidence and mastery events, the school context's marked homework,
and the published lesson versions. Nothing on a card can be typed in except one attributed teacher
comment. A correction is a new card that ``supersedes`` the old one; an issued card is never
edited. Promotion decisions (doc 29 §4) are out of scope.

Other contexts are reached only through the ports in ``application/ports.py``, wired in the
composition root (``main.py``).
"""

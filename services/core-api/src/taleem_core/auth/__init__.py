"""Authentication & authorization FRAMEWORK (governance-safe).

M1 provides the *seams* only: JWT structural verification and a deny-by-default Policy Decision
Point. It implements NO child accounts, NO guardian anchoring, NO enrolment, and NO real
credentials — those depend on unresolved governance decisions (FOUNDER_DECISIONS FD-01/05/14).
Production uses asymmetric JWKS + KMS + the full PDP (docs/11, docs/12).
"""

"""Identity & consent bounded context.

Owns *who may use Project Taleem and on whose authority*: guardian accounts, verifiable parental
consent, child (learner) enrolment, and the child-safe sign-in journey. This is the context that
closes FD-14 — Blocker 1 delivered production token *cryptography*; this delivers the *journey*.

Design rules that this context exists to enforce:

- **A child never has an email address, a password, or any contact detail.** A learner is created by
  a guardian and signs in with a family code, their own display name, and a short PIN, on a device
  the guardian enrolled. The only child attribute stored is a guardian-chosen display name.
- **No child may sign in without live, un-withdrawn guardian consent** covering the current policy
  version. The check fails closed: an unreadable consent store denies sign-in.
- **Consent is append-only evidence, not a boolean.** Granting and withdrawing both write immutable
  records carrying the policy version and the evidence of how consent was captured.
- **Every identity decision is audited** to an append-only trail a guardian (for their own family)
  and an operator (for safeguarding) can read.
"""

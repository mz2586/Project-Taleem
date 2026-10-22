"""School / organization context — the pilot-minimum teacher backend (GLOBAL_PRODUCT_SCOPE §F/§G).

An organization is a tenant: every class, enrolment, and assignment belongs to exactly one, and
every query is scoped by the organization of the acting teacher (read from the database, never from
the request). Teachers see only learners in their own classes, and only while the learner's guardian
has granted ``progress_sharing`` — checked live on every request.

Nothing here is, or is labelled as, an accredited programme.
"""

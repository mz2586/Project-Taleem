# Taleem School — Education-Partner Requirements

**Status:** Requirements draft · **Prepared:** 2026-10-22 · **Scope reference:**
[`GLOBAL_PRODUCT_SCOPE.md`](GLOBAL_PRODUCT_SCOPE.md) § Two connected pathways

**Superseded framing (2026-10-24).** The definitive mission makes Taleem an AI-led school with no
hired teaching workforce. Partners here are certification, invigilation, attestation and
safeguarding partners, not teaching partners. The class and assignment tools below are optional
oversight features; every learner capability also has an AI-led path. Recommended qualification
route: [`decisions/ACCREDITATION_PATHWAYS.md`](decisions/ACCREDITATION_PATHWAYS.md). The original
text follows for history:

Taleem School is the teacher-supported, structured pathway. It can lead to a recognized
qualification **only through an authorized education partner**. This document states what such a
partner must provide and what Taleem must build, so that a partner conversation has a concrete
basis. It does not block Taleem Learn: the free learning platform is built and released
independently.

## Non-negotiable rule

No screen, report, certificate, or message may describe Taleem Learn activity as enrolment in a
school, as accredited study, or as leading to a qualification. Wording that does so is a release
defect. Accredited status may appear only for a named partner programme, once a signed agreement
is on file.

## What a partner must provide

| # | Requirement | Why |
| --- | --- | --- |
| P-1 | Legal authority to award or recognize the qualification in the target jurisdiction | Taleem cannot self-accredit |
| P-2 | Named curriculum and assessment standards, with the right to deliver them digitally | Maps onto a curriculum pack |
| P-3 | What the partner certifies, invigilates or attests (exam entry, practical-work certificates, admission attestation): **never teaching**. A route that requires teacher-led instruction is recorded as incompatible ([`ACCREDITATION_PATHWAYS.md`](decisions/ACCREDITATION_PATHWAYS.md)), not accommodated by hiring teachers | AI-led mission ([`GLOBAL_PRODUCT_SCOPE.md`](GLOBAL_PRODUCT_SCOPE.md)) |
| P-4 | Assessment and invigilation rules for summative assessment (remote or in person) | Integrity of awards |
| P-5 | Attendance and progression rules (what counts, and minimums) | FD-10 attendance semantics |
| P-6 | Safeguarding standards and a designated safeguarding lead for its learners | M-Safe alignment |
| P-7 | A data-processing agreement: roles (controller/processor), retention, residency | FD-01/FD-02 |
| P-8 | Report-card and transcript format and recognition | FD-17 |

## What Taleem must build (pilot minimum first)

| Capability | Pilot minimum | Later |
| --- | --- | --- |
| Organization tenancy | One school organization with isolated data, tested | Many schools, regional policies |
| Classes and enrolment | Teacher-created class; learner joins with guardian consent | Bulk import, transfers |
| Teacher roles and authorization | Teacher sees only their classes' learners (deny-by-default PDP) | Department heads, admins |
| Assignments | Assign published lessons with a due date; see completion and mastery | Teacher-authored items |
| Academic calendar | Terms from the curriculum pack's calendar | Holidays, regional variants |
| Reports | Per-learner progress report labelled with the partner programme | Partner transcript formats |
| Attendance | Recorded per FD-10 once decided | Timetabling |

Dependencies: R1 platform (identity, consent, curriculum packs, sync), the teacher-experience
workstream, and FD-10 and FD-17 decisions.

## Owner actions

Identify candidate partners, open the conversation, and sign the agreement (P-1 to P-8). None of
this is an engineering task, and nothing above is claimed as available until it is built and the
agreement exists.

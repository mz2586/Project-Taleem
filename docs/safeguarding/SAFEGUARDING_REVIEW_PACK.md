# Safeguarding Review Pack: Disclosure Phrase List and Child Holding Messages

> **STATUS: NOT APPROVED — for qualified safeguarding review. Nothing here is approved until signed.**
>
> Typed questions to "Ask your teacher" (feature flag `ai_teacher.ask_free_text`) are **OFF** and
> **stay off** until §6 is signed by a qualified reviewer and the engineering changes it lists are
> merged. Nothing in this pack changes the running system. Every item marked **PROPOSED** is a
> suggestion for the reviewer to accept, amend or reject; none of it is in the live phrase list or
> the live message strings.

| | |
| --- | --- |
| **For** | A qualified child-safeguarding reviewer (clinician or designated safeguarding lead) |
| **Decides** | (a) the disclosure/distress phrase list; (b) the words a child sees after a match |
| **Prepared by** | Engineering, 2026-11-17, from the code at the commit that adds this file |
| **Does not decide** | SLA values and 24/7 staffing (FD-06), external referral and mandatory reporting (FD-04), data retention (M-Gov). Those stay open and are listed only where they limit what a message may promise. |
| **Related** | [52 Crisis protocol](../03-security-privacy/52-safeguarding-crisis-protocol.md) · [59 Safeguarding concerns](../03-security-privacy/59-safeguarding-concerns.md) · [Homework and marking contract §6](../10-curriculum-studio/HOMEWORK_AND_MARKING_CONTRACT.md) · [Founder decisions FD-04, FD-06](../../FOUNDER_DECISIONS.md) · [Master scope §11](../../PROJECT_TALEEM_MASTER_SCOPE.md) |

## 1. Purpose and scope

Project Taleem is a free, AI-led online school for children aged about 6 to 12, starting in
Pakistan, in Urdu first and English. Much of a child's learning happens with no human teacher
reading their work. The project's rule is: **nobody reading must not mean nobody protecting.**

Today, the only automatic protection on a child's written words is a **phrase list**: a short list of
English, Urdu and Roman-Urdu phrases. When a child's text contains one, a safeguarding concern is
created for a human to look at. The list was written by engineers as a starter. It has never been
reviewed by a safeguarding professional.

This pack asks the reviewer to:

1. check that §2 (how it works) is understood, including what it cannot do;
2. approve, amend or reject each phrase in the live list (§3);
3. accept or reject proposed additions and open questions (§4);
4. approve, amend or reject the words a child sees (§5);
5. sign §6, which states exactly what engineering will change for each approval.

**In scope:** the phrase list file, the "Ask your teacher" holding message, the "not in this
lesson" message, and what a child sees (or does not see) after a homework match.

**Out of scope:** the child's own "Tell a grown-up" reporting flow (already built, reviewed
separately under M-Safe), the triage console, SLA numbers, staffing, referral routes, and any
AI or model-based detection (none is switched on; see §2.6).

## 2. How screening works today

This section describes only what the code does. Sources are named so an engineer can check each
claim. Where something is not certain it says **UNCERTAIN**.

### 2.1 What text is screened, and when

| Path | What is screened | When | Status |
| --- | --- | --- | --- |
| **Homework** (written answers) | The full text of every written answer a child submits, including resubmissions and answers typed offline | Straight after the answer is saved on the server, in the same request. An answer typed offline is screened only when the phone reconnects and sends it. | **Live** in the code. Children do not use the system yet (NO-GO, master scope §11). |
| **Ask your teacher** (typed question) | The child's typed question (up to 300 characters) | Before the question is answered. Nothing from the lesson is shown until the screen has run. | **OFF.** Runs only when the flag `ai_teacher.ask_free_text` is on **and** the child's guardian has given live `ai_teaching` consent. The flag is off by default (an unknown flag is off). |

Tap-to-choose questions ("Show me an example", "What do children often get wrong?", "Tell me the
main idea again") contain no child text and are not screened.

Nothing else a child types is screened by this list today. The child's own "Tell a grown-up"
message goes straight to the safeguarding queue anyway.

Code: `services/core-api/src/taleem_core/contexts/school/application/school_service.py` (`_screen`),
`contexts/learning/application/ai_teacher_service.py` (`ask`), `main.py` (wiring),
`contexts/safeguarding/application/service.py` (`screen_submission`).

### 2.2 How a phrase matches

Both the child's text and each phrase are first put into the same plain form
(`contexts/safeguarding/domain/disclosure.py`, `normalise`):

1. Unicode NFKC normalisation (this also turns Arabic "presentation form" letters into ordinary ones).
2. Lower-case (case folding), so `HITS ME` and `hits me` are the same.
3. Arabic letters are changed to their Urdu forms: `ي` and `ى` become `ی`; `ك` becomes `ک`; and
   every heh (Arabic `ه`, Urdu `ھ` and `ہ`) becomes `ہ`, so Urdu typed on an Arabic keyboard
   matches (added 2026-11-17). No other letters are changed.
4. Arabic-script vowel marks (zabar, zer, pesh, shadd, tanween and similar), the superscript alif and
   the tatweel (stretching line) are removed.
5. Apostrophes are removed, so `don't` becomes `dont`.
6. Every other character that is not a letter or a digit (punctuation, emoji, symbols) becomes a space.
7. Runs of spaces become one space.

A phrase **matches** when its plain form appears in the child's plain text **as whole words, next
to each other, in the same order**. Examples (all checked by running the code):

| Child writes | Matches? | Why |
| --- | --- | --- |
| `He hits me every day` | Yes, `en-01` | contains the words `hits me` |
| `the boy hits me in the story` | Yes, `en-01` | the screen cannot tell a story from a disclosure |
| `he hit me` | **No** | `hit` is not `hits` |
| `Don't tell anyone!!` | Yes, `en-09` | apostrophe and `!!` removed |
| `do not tell anybody` | **No** | `anybody` is not `anyone` |
| `kill my self` | **No** | `my self` is two words; the list has `myself` |
| `میں خود کو مار دوں گا` | Yes, `ur-11` | `مار` stands as its own word |
| `میں خود کو مارنا چاہتا ہوں` | **No** | `مارنا` is one word, not `مار` |
| `میں گھر جانے سے ڈرتا ہوں` | **No** | `ڈرتا` is one word, not `ڈر` |
| `وہ مجهے مارتا هے` (Arabic `ه`) | Yes, `ur-01` | every heh is folded to `ہ` (since 2026-11-17) |
| `khud kushi` | **No** | the list has `khudkushi` as one word |
| `mai marna chahta hun` | **No** | the list has `hoon`, not `hun` |

There is no spelling tolerance, no stemming, no model and no score. The same text always gives the
same result.

### 2.3 Categories and tiers

Every phrase has one of the existing concern categories. The category sets the priority tier
(`contexts/safeguarding/domain/model.py`, `CATEGORY_PRIORITY`). Tiers follow the
[crisis protocol §2](../03-security-privacy/52-safeguarding-crisis-protocol.md).

| Category | What it is for (child wording in the app) | Tier |
| --- | --- | --- |
| `felt_unsafe` | "Someone made me feel unsafe" (abuse, grooming) | T1 |
| `very_sad` | "I feel very sad or scared" (distress, self-harm) | T1 |
| `bullying` | "Someone is bullying me" | T2 |
| `upsetting_lesson` | "Something in a lesson upset me" (not used by the list) | T2 |
| `other` | "Something else" (not used by the list) | T3 |

**No category is T0 ("imminent harm").** This is deliberate: a T0 promise needs a live human
within minutes, 24/7, and that does not exist (FD-06 open). If a text matches phrases in more than
one category, the concern takes the most urgent tier (T1 before T2); between two categories of the
same tier, the alphabetically first category name is used (`felt_unsafe` before `very_sad`)
(`strongest_category`). A new category (for example "neglect") would need a code change, not only
a list change.

### 2.4 What happens on a match

1. **One** safeguarding concern is created in the safeguarding triage queue, "raised by" the system
   (`disclosure_screen`), about that child, with the tier of the strongest category.
2. The concern's own text is a **fixed engineering note**, not the child's words, for example:
   *"Raised automatically by the homework disclosure screen (starter phrase list, pending M-Safe
   approval). Matched entries: en-01. Read homework submission … The child was not told."* For a
   typed question it says "ask-the-teacher" and "lesson question" instead.
3. In the same database transaction, the child's **exact text** is stored as the concern's
   **evidence snapshot**, with a SHA-256 fingerprint so tampering can be detected. It cannot be
   edited afterwards (a database trigger refuses updates and deletes except during a privacy
   erasure).
4. An audit row records that the concern was raised (category and tier only).
5. A counter goes up (`taleem_safeguarding_concerns_raised_total`, by tier and "raised by" only).
   Monitoring has a critical alert for an unacknowledged T1 concern and a warning for T2/T3, sent to
   `team: safeguarding`. **That alert destination is not configured**, so today nobody is paged
   ([59 §4](../03-security-privacy/59-safeguarding-concerns.md)).
6. **Nobody outside the platform is contacted.** No guardian, teacher, school, helpline, police or
   agency is told. External referral routes do not exist (FD-04).

At most **one open** system concern exists per homework submission or typed question at a time.
See §2.7, item 1, for what happens on resubmission after a concern is resolved.

### 2.5 Who sees it, what the child sees, what is stored

**Who can see the concern:** only an account with the `safeguarding_lead` role, in the triage
console. The lead must press a button to see what the child wrote; every such read is audited
(who, when, which concern, never the text). Guardians, teachers, mentors and operators have no route
to it. A guardian is never told, because the concern may be about someone in the child's home
([crisis protocol §4](../03-security-privacy/52-safeguarding-crisis-protocol.md)).

**What the child sees:**

| Path | On a match | When nothing matches |
| --- | --- | --- |
| Homework | **Nothing changes.** The child sees the same "saved" message as any other answer. The "Tell a grown-up" button is in the header of every child screen, as always. | Same. |
| Ask your teacher | The **holding message** (§5.1) and a **Get help** link to the "Tell a grown-up" page. No lesson text is shown and the question is not repeated back. | An answer quoted from the lesson, or the **"not in this lesson"** message (§5.2). |

**What is stored, and for how long:**

| Data | Stored? | Retention |
| --- | --- | --- |
| Concern (category, tier, status, fixed note, which screen, submission or question id) | Yes | **No period set** (pending M-Gov and FD-04). If a guardian asks for erasure, the default keeps it with the child's reference replaced by a one-way tombstone; an `erase` setting deletes it instead ([59 §3](../03-security-privacy/59-safeguarding-concerns.md)). |
| Evidence snapshot (the child's exact text, time, attempt, item, objective, fingerprint) | Yes, only for a matched text | Same as the concern. Withheld from guardian data exports. |
| A homework answer that did not match | Yes, as ordinary schoolwork | Ordinary learner-work retention (periods unset, pending M-Gov). |
| A typed question that did not match | **No.** Not stored and not logged. | Not applicable. |
| Logs and metrics | Counts and tier only; never the text, never a child reference | Platform log retention. |

### 2.6 What is not used

- **No AI model reads the child's text for safety.** An in-region distress classifier is a stated
  precondition for any AI marking (FD-03 brief) and does not exist.
- **Typed questions are answered by quoting the lesson only**, never by a model.
- The holding message is a **fixed string in the web app**, chosen by a fixed key
  (`ai_teacher.ask.holding`). No model writes or changes it, as the crisis protocol §3 requires.

### 2.7 Known limits of phrase matching

**Missed disclosures (false negatives).** A phrase list will miss most real disclosures. Children
rarely use the exact words on a list. Specifically:

- **Inflection and tense.** `hit me`, `hitting me`, `beat me` and `touched my` miss English entries
  written in one tense. In Urdu, the whole-word rule means `مار` does not match `مارنا`, `مارا` or
  `ماریں`, and `ڈر` does not match `ڈرتا` or `ڈرتی`.
- **Roman Urdu spelling varies widely.** `hoon` / `hun` / `hu` / `hn`, `marna` / `maarna`, `mujhe` /
  `mujhay` / `mjhe`, `khudkushi` / `khud kushi` / `khudkhushi`. Only one spelling of each is listed.
- **Urdu spelling and keyboards.** Joined or split words (`خودکشی` / `خود کشی`), and letters typed
  from Arabic or Persian keyboards. `ي`, `ى`, `ك` and every heh (`ه`, `ھ`, `ہ`) are folded, so
  `مجهے` matches `مجھے` (heh folding added 2026-11-17). Split and joined words are not.
- **Child spelling.** `tuches`, `hitts`, `sucide`, `dont tel`. None are listed.
- **Other languages.** There are no Punjabi, Sindhi, Pashto, Saraiki or Balochi entries.
- **Indirect disclosure.** "My uncle comes to my room at night", "I have a secret friend online",
  drawings, hints, or a story about "a friend". A list cannot catch these.
- **Typed questions on a lesson that is not published** are now screened first (fixed
  2026-11-17); before, they were refused before the screen ran.

**False alarms (false positives).** The screen cannot tell who is speaking or why:

- story or comprehension homework ("the giant hits me", "he said do not tell anyone, it is a
  surprise party");
- a lesson about bullying or safety, where children are asked to write about exactly these things;
- jokes, song lyrics and games ("my brother hits me in the game");
- a word used in a lesson (`خودکشی` in a social-studies text).

Every false alarm is a T1 or T2 item in a queue that, today, has no staffed rota. A long list
increases false alarms; a short list misses more. That balance is the reviewer's decision.

**Engineering observations for the reviewer** (not decided here; see the cover report):

1. **Fixed 2026-11-17 (alembic 0022).** A homework resubmission used to be never screened as new
   once any system concern existed for the submission. Now at most one concern is *open* per
   submission: while it is open, the lead sees newer text beside the snapshot; once it is resolved,
   a later attempt with different matching words raises a new concern. The exact words a reviewer
   already closed do not re-alert. Reviewer question: is that last rule right?
2. **Partly fixed 2026-11-17.** If the screen fails during a typed question, the question is no
   longer answered: the child gets "something went wrong, try again" (HTTP 503) and the failure is
   counted, so a disclosure is not silently dropped if they retry. For homework, a failed screen is
   still only counted (the child's answer is saved) and is **not** retried.
3. The lead's console labels flagged text as "the homework answer" even when it came from a typed
   question. The concern note and screen field (`learner/ask`) do say "lesson question".

## 3. The complete current phrase list

Generated from `services/core-api/src/taleem_core/contexts/safeguarding/disclosure_phrases.json`
by `taleem_core.tools.safeguarding_phrase_table`. Phrases are reproduced exactly; the last column is the
normalised form produced by the live `normalise()` function, which is what the matcher compares.

**Matching rule (every entry):** after normalisation (§2.2), the entry matches when its compared
form appears in the child's normalised text as whole words, adjacent and in order. No other rule
applies to any entry.

To regenerate after the list changes (from the repository root, Python 3.11+, standard library only):

```sh
python -m taleem_core.tools.safeguarding_phrase_table --write   # in services/core-api
python -m taleem_core.tools.safeguarding_phrase_table --check   # exit 1 if stale
```

<!-- phrase-table:start -->

Source: `disclosure_phrases.json`, version 1, status `pending_m_safe_approval`.

| ID | Category | Tier | Language | Phrase (exact, from the JSON) | Compared as (normalised; must appear as whole words, in order) |
| --- | --- | --- | --- | --- | --- |
| `en-01` | `felt_unsafe` | T1 | English | hits me | `hits me` |
| `en-02` | `felt_unsafe` | T1 | English | beats me | `beats me` |
| `en-03` | `felt_unsafe` | T1 | English | hurts me | `hurts me` |
| `en-04` | `felt_unsafe` | T1 | English | slaps me | `slaps me` |
| `en-05` | `felt_unsafe` | T1 | English | kicks me | `kicks me` |
| `en-06` | `felt_unsafe` | T1 | English | touches me | `touches me` |
| `en-07` | `felt_unsafe` | T1 | English | touched me | `touched me` |
| `en-08` | `felt_unsafe` | T1 | English | do not tell anyone | `do not tell anyone` |
| `en-09` | `felt_unsafe` | T1 | English | dont tell anyone | `dont tell anyone` |
| `en-10` | `felt_unsafe` | T1 | English | locks me in | `locks me in` |
| `en-11` | `felt_unsafe` | T1 | English | scared to go home | `scared to go home` |
| `en-12` | `very_sad` | T1 | English | want to die | `want to die` |
| `en-13` | `very_sad` | T1 | English | kill myself | `kill myself` |
| `en-14` | `very_sad` | T1 | English | hurt myself | `hurt myself` |
| `en-15` | `very_sad` | T1 | English | cut myself | `cut myself` |
| `en-16` | `very_sad` | T1 | English | end my life | `end my life` |
| `en-17` | `very_sad` | T1 | English | nobody loves me | `nobody loves me` |
| `en-18` | `very_sad` | T1 | English | no one loves me | `no one loves me` |
| `en-19` | `very_sad` | T1 | English | better off dead | `better off dead` |
| `en-20` | `bullying` | T2 | English | bullies me | `bullies me` |
| `en-21` | `bullying` | T2 | English | bullying me | `bullying me` |
| `ur-01` | `felt_unsafe` | T1 | Urdu (script) | مجھے مارتا ہے | `مجہے مارتا ہے` |
| `ur-02` | `felt_unsafe` | T1 | Urdu (script) | مجھے مارتی ہے | `مجہے مارتی ہے` |
| `ur-03` | `felt_unsafe` | T1 | Urdu (script) | مجھے مارتے ہیں | `مجہے مارتے ہیں` |
| `ur-04` | `felt_unsafe` | T1 | Urdu (script) | مجھے چھوتا ہے | `مجہے چہوتا ہے` |
| `ur-05` | `felt_unsafe` | T1 | Urdu (script) | کسی کو مت بتانا | `کسی کو مت بتانا` |
| `ur-06` | `felt_unsafe` | T1 | Urdu (script) | کسی کو نہ بتانا | `کسی کو نہ بتانا` |
| `ur-07` | `felt_unsafe` | T1 | Urdu (script) | گھر جانے سے ڈر | `گہر جانے سے ڈر` |
| `ur-08` | `very_sad` | T1 | Urdu (script) | مرنا چاہتا ہوں | `مرنا چاہتا ہوں` |
| `ur-09` | `very_sad` | T1 | Urdu (script) | مرنا چاہتی ہوں | `مرنا چاہتی ہوں` |
| `ur-10` | `very_sad` | T1 | Urdu (script) | خودکشی | `خودکشی` |
| `ur-11` | `very_sad` | T1 | Urdu (script) | خود کو مار | `خود کو مار` |
| `ur-12` | `very_sad` | T1 | Urdu (script) | خود کو نقصان | `خود کو نقصان` |
| `ur-13` | `very_sad` | T1 | Urdu (script) | کوئی مجھ سے پیار نہیں کرتا | `کوئی مجہ سے پیار نہیں کرتا` |
| `ur-14` | `bullying` | T2 | Urdu (script) | مجھے تنگ کرتے ہیں | `مجہے تنگ کرتے ہیں` |
| `ur-15` | `bullying` | T2 | Urdu (script) | مجھے تنگ کرتا ہے | `مجہے تنگ کرتا ہے` |
| `rur-01` | `felt_unsafe` | T1 | Roman Urdu | mujhe marta hai | `mujhe marta hai` |
| `rur-02` | `felt_unsafe` | T1 | Roman Urdu | mujhe marti hai | `mujhe marti hai` |
| `rur-03` | `felt_unsafe` | T1 | Roman Urdu | kisi ko mat batana | `kisi ko mat batana` |
| `rur-04` | `very_sad` | T1 | Roman Urdu | marna chahta hoon | `marna chahta hoon` |
| `rur-05` | `very_sad` | T1 | Roman Urdu | marna chahti hoon | `marna chahti hoon` |
| `rur-06` | `very_sad` | T1 | Roman Urdu | khudkushi | `khudkushi` |

| Category | English | Roman Urdu | Urdu (script) | Total |
| --- | --- | --- | --- | --- |
| `felt_unsafe` | 11 | 3 | 7 | 21 |
| `very_sad` | 8 | 3 | 6 | 17 |
| `bullying` | 2 | 0 | 2 | 4 |
| **All** | 21 | 6 | 15 | 42 |

<!-- phrase-table:end -->

The file's own header reads: *"STARTER LIST — pending safeguarding-lead approval (M-Safe)."* The
file's `status` field is `pending_m_safe_approval`; no code reads that field.

## 4. Reviewer questions and PROPOSED additions

> Everything in this section is **PROPOSED**. None of it is in the live list. Engineering wrote
> these proposals; they are prompts for an expert, not expert advice. Urdu and Roman-Urdu wording
> must be confirmed by a native-speaker reviewer; Punjabi entries are marked **DRAFT** and must be
> written or confirmed by a native speaker.

Each proposal shows the existing category it would use, because the matcher can only use the five
categories in §2.3. Proposal IDs (`P-…`) are for this review only; approved entries will get
permanent IDs in the file.

For every proposal, remember the whole-word rule: each tense or spelling a child might use must be
its own entry, and a short entry (one or two common words) matches far more ordinary schoolwork.

### 4.1 General questions (all categories)

| # | Question for the reviewer | Decision |
| --- | --- | --- |
| Q1 | Should story, comprehension or "write about bullying" homework be screened the same way as any other answer? (Today it is; it will raise false alarms.) | |
| Q2 | Is a first-person form required (`hits me`) or should third-person forms (`he hits`, `مارتا ہے` without `مجھے`) also match? Third-person forms catch "a friend" disclosures but match far more stories. | |
| Q3 | What is the acceptable false-alarm load for the queue while no rota is staffed (FD-06)? | |
| Q4 | Should hunger/neglect, running away, child labour and early marriage be `felt_unsafe` (T1), `other` (T3), or a new category (needs a code change and a tier)? | |
| Q5 | Which languages beyond Urdu and English must be covered before typed questions are switched on? | |
| Q6 | Should engineering add spelling tolerance (fold `ه`→`ہ`/`ھ`, treat `خود کشی` = `خودکشی`, collapse Roman `aa`/`oo`)? This is a code change with its own false-alarm risk; engineering would show the reviewer test cases before shipping it. | |

### 4.2 Self-harm and severe distress (`very_sad`, T1)

| ID | Lang | PROPOSED phrase | Gap it closes | False-alarm risk | Accept / Amend / Reject |
| --- | --- | --- | --- | --- | --- |
| P-VS-01 | en | kill my self | two-word "my self" | Low | |
| P-VS-02 | en | hurt my self | two-word "my self" | Low | |
| P-VS-03 | en | cut my self | two-word "my self" | Low | |
| P-VS-04 | en | cutting myself | tense | Low | |
| P-VS-05 | en | hurting myself | tense | Low | |
| P-VS-06 | en | wanna die | child register | Medium (games) | |
| P-VS-07 | en | want to be dead | variant | Low | |
| P-VS-08 | en | wish i was dead | variant | Low | |
| P-VS-09 | en | wish i was never born | variant | Low | |
| P-VS-10 | en | dont want to live | variant (`don't` folds to `dont`) | Low | |
| P-VS-11 | en | do not want to live | variant | Low | |
| P-VS-12 | en | suicide | keyword | Medium (lesson topics) | |
| P-VS-13 | en | sucide | child spelling | Medium | |
| P-VS-14 | en | suiside | child spelling | Medium | |
| P-VS-15 | en | hate my life | distress | Medium | |
| P-VS-16 | ur | خود کو مارنا | `مار` whole-word gap (most natural phrasing) | Low | |
| P-VS-17 | ur | خود کشی | split spelling of `خودکشی` | Medium (lesson topics) | |
| P-VS-18 | ur | جینا نہیں چاہتا | "don't want to live" (m) | Low | |
| P-VS-19 | ur | جینا نہیں چاہتی | "don't want to live" (f) | Low | |
| P-VS-20 | ur | مر جانا چاہتا ہوں | variant (m) | Low | |
| P-VS-21 | ur | مر جانا چاہتی ہوں | variant (f) | Low | |
| P-VS-22 | ur | کاش میں مر جاؤں | "I wish I would die" | Low | |
| P-VS-23 | ur | خود کو تکلیف | "hurt myself" | Low | |
| P-VS-24 | ur-Latn | marna chahta hun | `hun` spelling | Low | |
| P-VS-25 | ur-Latn | marna chahta hu | `hu` spelling | Low | |
| P-VS-26 | ur-Latn | marna chahti hun | `hun` spelling (f) | Low | |
| P-VS-27 | ur-Latn | marna chahti hu | `hu` spelling (f) | Low | |
| P-VS-28 | ur-Latn | khud kushi | split spelling | Medium | |
| P-VS-29 | ur-Latn | khudkhushi | common misspelling | Medium | |
| P-VS-30 | ur-Latn | khud ko maar | "kill myself" | Low | |
| P-VS-31 | ur-Latn | jeena nahi chahta | "don't want to live" | Low | |
| P-VS-32 | ur-Latn | koi mujhse pyar nahi karta | Roman form of `ur-13` | Low | |

Reviewer questions:

- Should "nobody loves me" type phrases (live `en-17`, `en-18`, `ur-13`) stay T1, or are they
  better as a lower tier (needs a new category)?
- Are there Pakistani child idioms for despair that are not literal ("dil karta hai sab khatam ho
  jaye")? Please add.

### 4.3 Physical and sexual abuse (`felt_unsafe`, T1)

| ID | Lang | PROPOSED phrase | Gap it closes | False-alarm risk | Accept / Amend / Reject |
| --- | --- | --- | --- | --- | --- |
| P-FU-01 | en | hit me | tense / child grammar | **High** (stories, games) | |
| P-FU-02 | en | hitting me | tense | Medium | |
| P-FU-03 | en | beat me | tense | Medium (games: "beat me at") | |
| P-FU-04 | en | beating me | tense | Medium | |
| P-FU-05 | en | slapped me | tense | Low | |
| P-FU-06 | en | kicked me | tense | Medium | |
| P-FU-07 | en | burns me | variant | Low | |
| P-FU-08 | en | touch me | grammar ("he touch me") | Medium | |
| P-FU-09 | en | touching me | tense | Low | |
| P-FU-10 | en | private parts | sexual abuse | Medium (science lessons) | |
| P-FU-11 | en | bad touch | child term | Low | |
| P-FU-12 | en | tuches me | child spelling | Low | |
| P-FU-13 | en | ties me | variant | Low | |
| P-FU-14 | ur | مجھے مارا | past tense | Medium | |
| P-FU-15 | ur | مجھے مارتی ہیں | plural/respect form (f) | Low | |
| P-FU-16 | ur | مجھے چھوتی ہے | "touches me" (f) | Low | |
| P-FU-17 | ur | مجھے چھوتے ہیں | "touch me" (pl.) | Low | |
| P-FU-18 | ur | غلط جگہ چھو | "touched in the wrong place" | Low | |
| P-FU-19 | ur | گندی حرکت | "dirty act" | Low | |
| P-FU-20 | ur | گھر جانے سے ڈرتا | `ڈر` whole-word gap (m) | Low | |
| P-FU-21 | ur | گھر جانے سے ڈرتی | `ڈر` whole-word gap (f) | Low | |
| P-FU-22 | ur-Latn | mujhe maarta hai | `maarta` spelling | Low | |
| P-FU-23 | ur-Latn | mujhe marte hain | plural form | Low | |
| P-FU-24 | ur-Latn | mujhe chhoota hai | "touches me" | Low | |
| P-FU-25 | ur-Latn | mujhe chuta hai | "touches me", spelling | Low | |
| P-FU-26 | ur-Latn | ghar jane se dar | Roman form of `ur-07` | Low | |
| P-FU-27 | pa-Latn | mainu marda | **DRAFT** Punjabi "hits me" (m) | Low | |
| P-FU-28 | pa-Latn | mainu mardi | **DRAFT** Punjabi "hits me" (f) | Low | |
| P-FU-29 | pa | مینوں ماردا | **DRAFT** Punjabi (Shahmukhi) "hits me" | Low | |

### 4.4 Secrecy and grooming, including online contact (`felt_unsafe`, T1)

| ID | Lang | PROPOSED phrase | Gap it closes | False-alarm risk | Accept / Amend / Reject |
| --- | --- | --- | --- | --- | --- |
| P-GR-01 | en | dont tell anybody | `anybody` variant | Medium (surprises) | |
| P-GR-02 | en | do not tell anybody | `anybody` variant | Medium | |
| P-GR-03 | en | dont tell any one | split spelling | Medium | |
| P-GR-04 | en | dont tell your mom | grooming script | Medium | |
| P-GR-05 | en | dont tell your parents | grooming script | Medium | |
| P-GR-06 | en | our secret | grooming | **High** (stories) | |
| P-GR-07 | en | send me pictures | online grooming | Low | |
| P-GR-08 | en | send pics | online grooming | Low | |
| P-GR-09 | en | without clothes | sexual | Low | |
| P-GR-10 | en | meet me alone | grooming | Low | |
| P-GR-11 | en | secret friend | grooming | Medium | |
| P-GR-12 | ur | کسی کو نہیں بتانا | negation variant | Medium | |
| P-GR-13 | ur | کسی کو مت بتاؤ | imperative variant | Medium | |
| P-GR-14 | ur | کسی کو نہ بتاؤ | imperative variant | Medium | |
| P-GR-15 | ur | ہمارا راز ہے | "it's our secret" | Medium | |
| P-GR-16 | ur | تصویر بھیجو | "send a picture" | Medium | |
| P-GR-17 | ur | اکیلے ملو | "meet alone" | Low | |
| P-GR-18 | ur-Latn | kisi ko na batana | Roman form of `ur-06` | Medium | |
| P-GR-19 | ur-Latn | kisi ko mat batao | imperative | Medium | |
| P-GR-20 | ur-Latn | tasveer bhejo | "send a picture" | Medium | |
| P-GR-21 | ur-Latn | pic bhejo | "send pic" | Medium | |
| P-GR-22 | pa-Latn | kise nu na dassin | **DRAFT** Punjabi "don't tell anyone" | Medium | |

Reviewer question: grooming is usually gradual and indirect. Should engineering stop treating
"online contact" as something a phrase list can catch, and instead treat it as a product rule (the
platform has no child-to-child or adult-to-child messaging today)?

### 4.5 Bullying (`bullying`, T2)

| ID | Lang | PROPOSED phrase | Gap it closes | False-alarm risk | Accept / Amend / Reject |
| --- | --- | --- | --- | --- | --- |
| P-BU-01 | en | bully me | grammar | Medium | |
| P-BU-02 | en | bullied me | tense | Medium | |
| P-BU-03 | en | make fun of me | variant | Medium | |
| P-BU-04 | en | call me names | variant | Low | |
| P-BU-05 | en | nobody plays with me | exclusion | Low | |
| P-BU-06 | ur | مجھے تنگ کرتی ہے | feminine form of `ur-15` | Low | |
| P-BU-07 | ur | مذاق اڑاتے ہیں | "make fun" | Medium | |
| P-BU-08 | ur | مجھے چھیڑتے ہیں | "tease me" (can also mean harassment) | Medium | |
| P-BU-09 | ur-Latn | mujhe tang karte hain | Roman form of `ur-14` | Low | |
| P-BU-10 | ur-Latn | mujhe tang karta hai | Roman form of `ur-15` | Low | |
| P-BU-11 | ur-Latn | mazaq udate hain | "make fun" | Medium | |

Reviewer question: `چھیڑنا` / `chherna` can mean street harassment of girls. Should it be
`felt_unsafe` (T1) rather than `bullying` (T2)?

### 4.6 Exploitation: child labour and early marriage (category: reviewer to decide, Q4)

| ID | Lang | PROPOSED phrase | Gap it closes | False-alarm risk | Accept / Amend / Reject |
| --- | --- | --- | --- | --- | --- |
| P-EX-01 | en | have to work instead of school | child labour | Low | |
| P-EX-02 | en | not allowed to go to school | denied schooling | Medium | |
| P-EX-03 | en | forced to marry | early marriage | Low | |
| P-EX-04 | ur | زبردستی شادی | "forced marriage" | Low (social-studies lessons) | |
| P-EX-05 | ur | میری شادی کر رہے ہیں | "they are marrying me off" | Low | |
| P-EX-06 | ur | سکول نہیں جانے دیتے | "don't let me go to school" | Medium | |
| P-EX-07 | ur-Latn | meri shadi kar rahe | "marrying me off" | Low | |

### 4.7 Hunger and neglect (category: reviewer to decide, Q4)

| ID | Lang | PROPOSED phrase | Gap it closes | False-alarm risk | Accept / Amend / Reject |
| --- | --- | --- | --- | --- | --- |
| P-NG-01 | en | nothing to eat | hunger | Medium | |
| P-NG-02 | en | no food at home | hunger | Low | |
| P-NG-03 | en | go to bed hungry | hunger | Low | |
| P-NG-04 | ur | کھانے کو کچھ نہیں | "nothing to eat" | Medium | |
| P-NG-05 | ur | بھوکا سوتا ہوں | "I sleep hungry" (m) | Low | |
| P-NG-06 | ur | بھوکی سوتی ہوں | "I sleep hungry" (f) | Low | |
| P-NG-07 | ur-Latn | khana nahi milta | "I don't get food" | Low | |

Reviewer question: a plain "I am hungry" is ordinary and is deliberately **not** proposed. Is that right?

### 4.8 Running away (category: reviewer to decide, Q4)

| ID | Lang | PROPOSED phrase | Gap it closes | False-alarm risk | Accept / Amend / Reject |
| --- | --- | --- | --- | --- | --- |
| P-RA-01 | en | run away from home | running away | Low (stories) | |
| P-RA-02 | en | ran away from home | tense | Low | |
| P-RA-03 | en | dont want to go home | live list has only "scared to go home" | Low | |
| P-RA-04 | ur | گھر سے بھاگ | "run from home" (any tense) | Medium | |
| P-RA-05 | ur | گھر نہیں جانا چاہتا | "don't want to go home" (m) | Low | |
| P-RA-06 | ur | گھر نہیں جانا چاہتی | "don't want to go home" (f) | Low | |
| P-RA-07 | ur-Latn | ghar se bhaag | "run from home" | Medium | |

### 4.9 Languages with no entries (questions only)

Engineering has **not** drafted Sindhi, Pashto, Saraiki or Balochi phrases and will not guess
them. For each, the reviewer is asked: is it needed before launch in the first cohort's area, and
who will supply and check it?

| Language | Needed before typed questions go live? | Who supplies | Who checks |
| --- | --- | --- | --- |
| Punjabi (Shahmukhi and Roman) | | | |
| Sindhi | | | |
| Pashto | | | |
| Saraiki | | | |
| Other: | | | |

### 4.10 Live entries to look at closely

These live entries behave in ways the reviewer may not expect:

- `ur-11` `خود کو مار` does **not** match `خود کو مارنا` (P-VS-16 proposes the fix).
- `ur-07` `گھر جانے سے ڈر` matches `ڈر لگتا ہے` but not `ڈرتا` / `ڈرتی` (P-FU-20, P-FU-21).
- `ur-10` `خودکشی` and `rur-06` `khudkushi` will match lessons that mention the topic.
- `en-08` / `en-09` (`do not tell anyone`) will match surprise-party stories.
- `en-06` / `en-07` (`touches me`, `touched me`) will match science or sensory lessons ("the sand
  touches me").

## 5. PROPOSED child-facing messages

### 5.0 Constraints every message must meet

- **No promise of a response time** or of a person replying, calling or coming. There is no 24/7
  staffing and no SLA (FD-06 open). The current child "Tell a grown-up" receipt already follows this.
- **No promise of secrecy or of telling.** The platform cannot promise "nobody will know", and it
  must not say "we will tell your parents" (the guardian may be the risk; crisis protocol §4).
- **Shared-device safe.** A family phone is often shared. Assume an adult in the home may read the
  screen. The message must not name abuse, repeat the child's words, or say "we have reported this".
- **Not a person pretending.** The "teacher" is software. It must not say "I am worried about you"
  or "Thank you for telling **me**" in a way that suggests a human heard.
- **Directs to a real, present adult** and to the existing "Tell a grown-up" page.
- **Crisis resource only if verified.** Crisis protocol §3 asks for a safe local crisis resource.
  No helpline is shown today, and engineering will not add any number the reviewer has not verified
  (see §5.4).
- **Reading level.** Ages 6 to 12, many early readers. Target: sentences of 10 words or fewer,
  everyday words, Urdu in simple spoken register. The holding message currently has **no read-aloud
  button** (only lesson passages do); see §5.5, item E4.

### 5.1 Ask your teacher: holding message (served on every match)

Message key `student.askTeacher.holding` (server key `ai_teacher.ask.holding`). The server returns
the **same key for every match**, whatever the category or tier, so one text covers T1 and T2. The
child also sees a **Get help** link (key `student.askTeacher.getHelp`, currently "Get help" /
"مدد لیں") to the "Tell a grown-up" page.

**Current placeholder (live strings, not approved):**

| Lang | Text |
| --- | --- |
| en | Thank you for telling me. You are not in trouble. If you feel unsafe, please talk to a grown-up you trust. You can also get help here. |
| ur | بتانے کا شکریہ۔ آپ کسی مشکل میں نہیں ہیں۔ اگر آپ خود کو محفوظ محسوس نہیں کرتے تو کسی بھروسے والے بڑے سے بات کریں۔ آپ یہاں سے مدد بھی لے سکتے ہیں۔ |

Concerns with the placeholder:

- "Thank you for telling **me**" suggests a person heard.
- **UNCERTAIN, native speaker to confirm:** the Urdu `آپ کسی مشکل میں نہیں ہیں` reads literally as
  "you are not in any difficulty". To a child who has just described a difficulty, that may sound
  dismissive. "You are not in trouble" means "you have not done wrong".
- "If you feel unsafe" names the subject on a shared screen.

**PROPOSED H-1 (recommended starting point):**

| Lang | Text |
| --- | --- |
| en | Thank you for writing this. You have not done anything wrong. If something is wrong, tell a grown-up you trust. If you are in danger now, go to a grown-up near you. You can also tap Get help. |
| ur | یہ لکھنے کا شکریہ۔ آپ نے کوئی غلطی نہیں کی۔ اگر کچھ ٹھیک نہیں ہے تو کسی بھروسے والے بڑے کو بتائیں۔ اگر آپ کو ابھی خطرہ ہے تو اپنے پاس کسی بڑے کے پاس جائیں۔ آپ "مدد لیں" بھی دبا سکتے ہیں۔ |

- *Rationale:* validates without judging; "you have not done anything wrong" is the common
  child-safeguarding reassurance; points to a present adult and to the in-app route; says nothing
  about who will read it, so it promises nothing the rota cannot keep; neutral if an adult reads the
  screen.
- *Reading level:* five sentences, longest 10 words (en). Everyday words. Urdu in spoken register.
- *Tier:* the same text for T1 (`felt_unsafe`, `very_sad`) and T2 (`bullying`). No T0 text exists
  because nothing is assigned T0.

**PROPOSED H-2 (only if the reviewer wants the child told a person will read it):**

| Lang | Text |
| --- | --- |
| en | Thank you for writing this. You have not done anything wrong. A person at Taleem who keeps children safe will read it. That may take some time. If you are in danger now, go to a grown-up near you. You can also tap Get help. |
| ur | یہ لکھنے کا شکریہ۔ آپ نے کوئی غلطی نہیں کی۔ تعلیم میں بچوں کی حفاظت کرنے والا ایک شخص اسے پڑھے گا۔ اس میں کچھ وقت لگ سکتا ہے۔ اگر آپ کو ابھی خطرہ ہے تو اپنے پاس کسی بڑے کے پاس جائیں۔ آپ "مدد لیں" بھی دبا سکتے ہیں۔ |

- *Rationale:* honest acknowledgement, matching the existing "Tell a grown-up" receipt ("A trained
  grown-up at Taleem will read this"). "That may take some time" is there because no response time
  can be promised.
- *Condition:* only true once a `safeguarding_lead` account is staffed and the alert destination is
  configured. Until then H-2 would be a promise the platform cannot keep. It also tells anyone
  reading the screen that the text was passed on.
- *Brand spelling:* `تعلیم`, as in the live Urdu "Tell a grown-up" receipt.

**What NOT to say (both versions):**

| Do not say | Why |
| --- | --- |
| "Someone will contact you / reply / call you soon" | No staffing or SLA (FD-06). |
| "Within 24 hours", "today", any time | Same. |
| "Your parents / teacher will be told" | The guardian may be the risk; teachers never see concerns. |
| "Nobody else will see this" / "This is a secret" | Untrue (the lead sees it) and mirrors grooming language. |
| "I am worried about you", "I understand" | Software pretending to be a person. |
| "We have reported this" | Untrue (nobody is contacted, FD-04) and unsafe on a shared screen. |
| Repeating any of the child's words | Shared-device risk; already prevented in code. |
| "Are you sure?" / "Tell me more" | The screen does not hold a conversation; nobody would read a reply in time. |
| Any phone number not verified under §5.4 | A wrong or closed number at a crisis moment is harmful. |

### 5.2 Ask your teacher: "not in this lesson" message

Key `student.askTeacher.notInLesson`. Shown when the question is not answered by the lesson,
**including when a real disclosure was missed by the phrase list** (§2.7). So this message is also
what most children who disclose in a typed question will see.

**Current placeholder:**

| Lang | Text |
| --- | --- |
| en | That is not in this lesson. Try another question, or ask a grown-up you trust. |
| ur | یہ اس سبق میں نہیں ہے۔ کوئی اور سوال پوچھیں، یا کسی بھروسے والے بڑے سے پوچھیں۔ |

**PROPOSED N-1:**

| Lang | Text |
| --- | --- |
| en | I could not find that in this lesson. Try another question. If something is wrong, you can tap Tell a grown-up. |
| ur | یہ اس سبق میں نہیں ملا۔ کوئی اور سوال پوچھیں۔ اگر کچھ ٹھیک نہیں ہے تو "کسی بڑے کو بتائیں" دبائیں۔ |

- *Rationale:* a missed disclosure should still meet a gentle pointer to the reporting route,
  without suggesting the child said something wrong. "Tell a grown-up" is the existing button name.
- *Button name:* `کسی بڑے کو بتائیں` is the live Urdu label of the "Tell a grown-up" button
  (`safeguarding.entry.label` in `ur.ts`); engineering will copy it from there, not retype it.
- *Reading level:* three sentences, longest 10 words (en).
- *What NOT to say:* "I don't understand your question" (blames the child); anything implying the
  question was read by a person.

### 5.3 Homework path

**Today:** on a match, the child sees **nothing different** (the normal "Saved" message). The
"Tell a grown-up" button is in every child screen's header. This is set by the
[homework contract §6](../10-curriculum-studio/HOMEWORK_AND_MARKING_CONTRACT.md) and the server
returns nothing about the match to the app.

| Option | What the child sees on a match | For | Against | Engineering cost |
| --- | --- | --- | --- | --- |
| **HW-0 (current, PROPOSED to keep)** | Nothing different | Shared-device safe; a false alarm on a story does not confuse the child | A child who disclosed gets no acknowledgement | None |
| HW-1 | The H-1 text (or the reviewer's amended text) under "Saved" | The child knows their words mattered | Shows on a shared screen that something was flagged; false alarms on stories will show it too | API contract change: the submit response must say "show the holding message" |
| HW-2 | A short line under **every** saved open answer, match or not: "If something is wrong, you can tap Tell a grown-up." / "اگر کچھ ٹھیک نہیں ہے تو "کسی بڑے کو بتائیں" دبائیں۔" | Reaches every child, reveals nothing | Repetition may make children ignore it | Client string only |

### 5.4 Crisis resource (crisis protocol §3)

No helpline is shown anywhere today. The reviewer is asked whether one should be, and which.
Engineering lists candidates **only as a starting point; every one is UNVERIFIED** (number, hours,
whether it accepts calls from children, which provinces it serves, whether calling it could put a
child at risk):

| Candidate | UNVERIFIED detail | Reviewer: verified? number, hours, child-safe? |
| --- | --- | --- |
| Child Protection & Welfare Bureau, Punjab | helpline 1121 | |
| Madadgaar National Helpline | 1098 | |
| Rozan counselling helpline | number to be confirmed | |
| Police emergency | 15 | |
| Rescue | 1122 | |

### 5.5 Engineering notes on presentation (no reviewer decision needed, for awareness)

- **E1.** The holding message and the "Get help" link are fixed strings in
  `apps/web/lib/i18n/messages/en.ts` and `ur.ts`. They are chosen by key, never generated.
- **E2.** The question is never shown back to the child after a match (enforced in
  `apps/web/lib/student/askTeacher.ts`).
- **E3.** After the holding message the child can close the panel and continue the lesson, and can
  type again. **Reviewer question:** is that right, or should typing pause for the rest of the
  session?
- **E4.** There is no read-aloud for the holding message. For 6 to 7 year olds this matters. Adding
  one is a small client change.

## 6. Sign-off

Sign each item. "Amend" means write the replacement in the space (or attach a page). An item left
blank is **not approved**. Engineering changes only what is approved, in a reviewed pull request
that links to this signed pack.

### 6.1 Reviewer

| Field | Entry |
| --- | --- |
| Name | |
| Role | |
| Qualification / registration (body and number) | |
| Organisation | |
| Languages reviewed (en / ur / Roman ur / other) | |
| Native-speaker check of Urdu by (name, if different) | |
| Date | |
| Signature | |

### 6.2 Live phrase list (one row per live entry)

| ID | Approve | Amend (write new phrase or category) | Reject (remove) |
| --- | --- | --- | --- |
| en-01 | ☐ | | ☐ |
| en-02 | ☐ | | ☐ |
| en-03 | ☐ | | ☐ |
| en-04 | ☐ | | ☐ |
| en-05 | ☐ | | ☐ |
| en-06 | ☐ | | ☐ |
| en-07 | ☐ | | ☐ |
| en-08 | ☐ | | ☐ |
| en-09 | ☐ | | ☐ |
| en-10 | ☐ | | ☐ |
| en-11 | ☐ | | ☐ |
| en-12 | ☐ | | ☐ |
| en-13 | ☐ | | ☐ |
| en-14 | ☐ | | ☐ |
| en-15 | ☐ | | ☐ |
| en-16 | ☐ | | ☐ |
| en-17 | ☐ | | ☐ |
| en-18 | ☐ | | ☐ |
| en-19 | ☐ | | ☐ |
| en-20 | ☐ | | ☐ |
| en-21 | ☐ | | ☐ |
| ur-01 | ☐ | | ☐ |
| ur-02 | ☐ | | ☐ |
| ur-03 | ☐ | | ☐ |
| ur-04 | ☐ | | ☐ |
| ur-05 | ☐ | | ☐ |
| ur-06 | ☐ | | ☐ |
| ur-07 | ☐ | | ☐ |
| ur-08 | ☐ | | ☐ |
| ur-09 | ☐ | | ☐ |
| ur-10 | ☐ | | ☐ |
| ur-11 | ☐ | | ☐ |
| ur-12 | ☐ | | ☐ |
| ur-13 | ☐ | | ☐ |
| ur-14 | ☐ | | ☐ |
| ur-15 | ☐ | | ☐ |
| rur-01 | ☐ | | ☐ |
| rur-02 | ☐ | | ☐ |
| rur-03 | ☐ | | ☐ |
| rur-04 | ☐ | | ☐ |
| rur-05 | ☐ | | ☐ |
| rur-06 | ☐ | | ☐ |

### 6.3 Items, decisions and the engineering change each one unlocks

| # | Item | Approve / Amend / Reject | Engineering change unlocked by approval |
| --- | --- | --- | --- |
| S1 | Live phrase list as marked in §6.2 | | Replace the `phrases` array in `services/core-api/src/taleem_core/contexts/safeguarding/disclosure_phrases.json` with the approved entries; bump `version`; set `status` and `_header` to name this sign-off (reviewer, date). Update the fixed concern note in `contexts/safeguarding/application/service.py` (it says "starter phrase list, pending M-Safe approval"), `STARTER_HEADER` in `domain/disclosure.py`, and the tests that assert them (`test_ai_led_homework_units.py`, and `test_self_paced_homework.py` / `test_safeguarding_context.py` if `en-01` or `ur-01` change). Regenerate §3 with `python -m taleem_core.tools.safeguarding_phrase_table --write`. |
| S2 | PROPOSED additions in §4.2 to §4.8, as marked in each table, with categories decided under Q4 | | Add the accepted entries to the same file with permanent IDs, in the same pull request as S1, with one match test per new entry. A new category (Q4) is a separate code change and needs its tier approved here. |
| S3 | Q6 spelling tolerance (fold `ه`, split/joined words, Roman vowels) | | Change `normalise()` in `domain/disclosure.py` only after the reviewer has seen the before/after test cases engineering will supply. Not unlocked by this signature alone. |
| S4 | Holding message: H-1, H-2, or amended text (§5.1) | | Replace `student.askTeacher.holding` in `apps/web/lib/i18n/messages/en.ts` and `ur.ts` with the approved text, word for word. |
| S5 | "Not in this lesson" message: N-1 or amended (§5.2) | | Replace `student.askTeacher.notInLesson` in `en.ts` and `ur.ts`. |
| S6 | Homework path: HW-0, HW-1 or HW-2 (§5.3) | | HW-0: none. HW-2: add one client string to the homework screen. HW-1: API contract change plus client change, in its own reviewed pull request. |
| S7 | Crisis resource (§5.4): none, or the verified entries | | Add only the verified entries, as fixed strings, to the help page and (if chosen) the holding message. |
| S8 | E3 (typing after a match) and E4 (read-aloud), §5.5 | | Client changes as decided. |
| S9 | Switching on typed questions | | **Only after S1 and S4 are approved and their changes merged**, and any condition the reviewer adds below is met, the owner may add `ai_teacher.ask_free_text` to `TALEEM_ENABLED_FLAGS` in the target environment. Engineering will not enable it. |

Conditions the reviewer sets for S9 (for example: a named safeguarding lead account exists; the
`team: safeguarding` alert destination is configured; a drill has shown a concern reaching a person;
specific languages are covered):

| Condition | Met? (date, evidence) |
| --- | --- |
| | |
| | |
| | |

Reviewer comments:

| Comment |
| --- |
| |

## Change log

| Date | Change | Author |
| --- | --- | --- |
| 2026-11-17 | First review pack: how screening works, the live list (generated), proposals, proposed messages, sign-off form. Nothing approved. | Engineering |

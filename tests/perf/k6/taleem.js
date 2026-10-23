// Project Taleem — load / soak / spike scenarios for the Core API (k6).
//
// Run through tests/perf/run.sh (make perf-load | perf-soak | perf-spike), which starts a real
// uvicorn + PostgreSQL, seeds SYNTHETIC families/teachers (setup, not timed) and passes:
//   PERF_PROFILE   load | soak | spike
//   PERF_BASE_URL  http://127.0.0.1:<port>
//   PERF_SEED      path to the seed JSON written by tests/perf/seed.py
//   PERF_SUMMARY   where handleSummary writes the k6 JSON summary
//
// Every virtual user owns one synthetic family and sends that family's own RFC 5737 address as
// X-Real-IP (the server trusts it via TALEEM_CLIENT_IP_HEADER=x-real-ip, as on Vercel). The sign-in
// limiter (10 per client per 60 s) is NOT lowered: a learner's day is paced to at most ~5 sign-ins
// per minute per address, so a 429 here means the harness is wrong, and it is counted.

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import exec from 'k6/execution';

const BASE = __ENV.PERF_BASE_URL || 'http://127.0.0.1:8790';
const PROFILE = (__ENV.PERF_PROFILE || 'load').toLowerCase();
const SEED = JSON.parse(open(__ENV.PERF_SEED));
const LOAD_VUS = parseInt(__ENV.PERF_LOAD_VUS || '60', 10);
const SOAK_VUS = parseInt(__ENV.PERF_SOAK_VUS || '10', 10);
const SOAK_DURATION = __ENV.PERF_SOAK_DURATION || '12m';
const SPIKE_BASE = parseInt(__ENV.PERF_SPIKE_BASE_VUS || '5', 10);
const LOAD_RAMP_S = parseInt(__ENV.PERF_LOAD_RAMP_S || '120', 10);
const LOAD_HOLD_S = parseInt(__ENV.PERF_LOAD_HOLD_S || '180', 10);
const ACCURACY = parseFloat(__ENV.PERF_ACCURACY || '0.6');
const ITERATION_FLOOR_S = 12; // >= 12 s per learner day keeps each address <= 5 sign-ins/min

const rateLimited = new Counter('taleem_rate_limited');
const serverErrors = new Counter('taleem_server_errors');
const nothingToLearn = new Counter('taleem_planner_nothing_to_learn');

// PERF-01 (docs/01-product/04-non-functional-requirements.md): API p95 < 300 ms, p99 < 800 ms.
// auth_kdf (PBKDF2-SHA256, 600 000 iterations — production minimum) has no documented budget; the
// 1500/3000 ms figures are PROPOSALS (tests/perf/README.md). Thresholds report; run.sh decides
// whether a miss fails the run (PERF_ENFORCE=1).
const GROUPS = ['auth_kdf', 'learning', 'sync', 'progress', 'packages', 'guardian_reads', 'teacher_reads'];
const thresholds = {
  http_req_failed: ['rate<0.001'],
  checks: ['rate>0.999'],
  taleem_rate_limited: ['count==0'],
};
for (const g of GROUPS) {
  const budget = g === 'auth_kdf' ? ['p(95)<1500', 'p(99)<3000'] : ['p(95)<300', 'p(99)<800'];
  thresholds[`http_req_duration{grp:${g}}`] = budget;
  thresholds[`http_req_failed{grp:${g}}`] = ['rate<0.001'];
}

function profileScenarios() {
  if (PROFILE === 'soak') {
    return {
      learners: { executor: 'constant-vus', exec: 'learnerDay', vus: SOAK_VUS, duration: SOAK_DURATION },
      guardians: { executor: 'constant-vus', exec: 'guardianReads', vus: 3, duration: SOAK_DURATION },
      teachers: { executor: 'constant-vus', exec: 'teacherReads', vus: 2, duration: SOAK_DURATION },
    };
  }
  if (PROFILE === 'spike') {
    const peak = SPIKE_BASE * 10; // sudden 10x burst
    return {
      learners: {
        executor: 'ramping-vus', exec: 'learnerDay', startVUs: SPIKE_BASE,
        stages: [
          { duration: '1m', target: SPIKE_BASE },
          { duration: '10s', target: peak },
          { duration: '1m', target: peak },
          { duration: '10s', target: SPIKE_BASE },
          { duration: '1m', target: SPIKE_BASE },
        ],
        gracefulRampDown: '30s',
      },
      guardians: { executor: 'constant-vus', exec: 'guardianReads', vus: 2, duration: '3m20s' },
      teachers: { executor: 'constant-vus', exec: 'teacherReads', vus: 2, duration: '3m20s' },
    };
  }
  return {
    learners: {
      executor: 'ramping-vus', exec: 'learnerDay', startVUs: 0,
      stages: [
        { duration: `${LOAD_RAMP_S}s`, target: LOAD_VUS },
        { duration: `${LOAD_HOLD_S}s`, target: LOAD_VUS },
        { duration: '30s', target: 0 },
      ],
      gracefulRampDown: '30s',
    },
    guardians: { executor: 'constant-vus', exec: 'guardianReads', vus: 5, duration: `${LOAD_RAMP_S + LOAD_HOLD_S + 30}s` },
    teachers: { executor: 'constant-vus', exec: 'teacherReads', vus: 3, duration: `${LOAD_RAMP_S + LOAD_HOLD_S + 30}s` },
  };
}

export const options = {
  scenarios: profileScenarios(),
  thresholds,
  summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max', 'count'],
  discardResponseBodies: false,
  noConnectionReuse: false,
  setupTimeout: '30s',
};

// --------------------------------------------------------------------------------------- helpers

function family() {
  const fams = SEED.families;
  const i = exec.vu.idInTest - 1;
  if (i >= fams.length) {
    exec.test.abort(`seed has ${fams.length} families but VU ${i + 1} needs one; raise --families`);
  }
  return fams[i];
}

function headers(ip, token) {
  const h = { 'Content-Type': 'application/json', 'X-Real-IP': ip };
  if (token) h.Authorization = `Bearer ${token}`;
  return { headers: h };
}

function call(method, path, body, ip, token, grp, name) {
  const params = headers(ip, token);
  params.tags = { grp, name };
  const res = http.request(method, `${BASE}${path}`, body === null ? null : JSON.stringify(body), params);
  if (res.status === 429) rateLimited.add(1, { grp });
  if (res.status >= 500) serverErrors.add(1, { grp, name });
  return res;
}

function ok(res, label, statuses) {
  return check(res, { [`${label} ${statuses.join('/')}`]: (r) => statuses.includes(r.status) });
}

function json(res) {
  try {
    return res.json();
  } catch (_e) {
    return {};
  }
}

function uuid4() {
  // Synthetic client-generated ids (evidence + event ids), RFC 4122 v4 shape.
  const hex = '0123456789abcdef';
  let s = '';
  for (let i = 0; i < 32; i++) {
    let n = Math.floor(Math.random() * 16);
    if (i === 12) n = 4;
    if (i === 16) n = (n & 0x3) | 0x8;
    s += hex[n];
  }
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`;
}

function answerFor(itemRef) {
  const correct = SEED.answer_key[itemRef] ?? 0;
  // A learner still learning: right ACCURACY of the time (default 0.6), so mastery is not reached
  // on the first day and the planner keeps teaching (the fixture is a single lesson).
  return Math.random() < ACCURACY ? correct : (correct + 1) % 4;
}

// ------------------------------------------------------------------------------------ scenarios

export function learnerDay() {
  const started = Date.now();
  const f = family();
  const ip = f.ip;
  const signin = call('POST', '/v1/identity/learners:signin',
    { familyCode: f.family_code, displayName: f.display_name, pin: f.pin, deviceId: `perf-${f.index}` },
    ip, null, 'auth_kdf', 'learners:signin');
  if (!ok(signin, 'learner sign-in', [200])) { sleep(ITERATION_FLOOR_S); return; }
  const token = json(signin).session.access_token;
  const ref = f.student_ref;
  sleep(1);

  ok(call('GET', '/v1/offline/packages', null, ip, token, 'packages', 'offline/packages'), 'packages', [200]);
  const started201 = call('POST', '/v1/learning/sessions', { student_ref: ref }, ip, token, 'learning', 'sessions');
  if (!ok(started201, 'session start', [201])) { sleep(ITERATION_FLOOR_S); return; }
  const base = `/v1/learning/sessions/${json(started201).session_id}`;

  const next = call('POST', `${base}:next`, {}, ip, token, 'learning', 'sessions:next');
  ok(next, 'planner next', [200]);
  const objective = SEED.objective_code;
  let items = SEED.item_refs;
  if (json(next).objective_code) {
    const taught = call('POST', `${base}:teach`, { objective_code: objective }, ip, token, 'learning', 'sessions:teach');
    ok(taught, 'teach', [200]);
    items = (json(taught).items || []).map((it) => it.item_ref);
    for (const itemRef of items) {
      sleep(0.5 + Math.random()); // a child reads and taps
      ok(call('POST', `${base}:answer`,
        { objective_code: objective, item_ref: itemRef, option: answerFor(itemRef), hints_used: 0 },
        ip, token, 'learning', 'sessions:answer'), 'answer', [200]);
    }
  } else {
    // Mastered (one fixture lesson exists): the planner has nothing new. The child still practised
    // offline from the cached package, so that day's work arrives as a larger sync batch instead.
    nothingToLearn.add(1);
  }
  const offlineAttempts = json(next).objective_code ? 3 : 10;
  ok(call('POST', `${base}:end`, {}, ip, token, 'learning', 'sessions:end'), 'end', [200]);

  // The same child's offline practice from earlier, uploaded as one batch when the device is back.
  const deltas = Array.from({ length: offlineAttempts }, (_v, i) => items[i % items.length]).map((itemRef, i) => ({
    clientEventId: uuid4(),
    type: 'attempt.submitted',
    entityKey: `student:${ref}|lesson:${SEED.lesson_id}`,
    clientSeq: i + 1,
    payload: {
      student_ref: ref, objective_code: objective, item_ref: itemRef, option: answerFor(itemRef),
      evidence_id: uuid4(), session_id: `offline-${uuid4()}`, context: 'practice',
    },
  }));
  sleep(1);
  ok(call('POST', '/v1/sync/batch', { cursor: 0, deltas }, ip, token, 'sync', 'sync/batch'), 'sync', [200]);
  sleep(1);
  ok(call('GET', `/v1/learning/students/${ref}/progress`, null, ip, token, 'progress', 'students/progress'), 'progress', [200]);

  const remaining = ITERATION_FLOOR_S - (Date.now() - started) / 1000;
  if (remaining > 0) sleep(remaining);
}

let guardianToken = null;

export function guardianReads() {
  const f = family();
  if (!guardianToken) {
    const s = call('POST', '/v1/identity/guardians:signin', { email: f.email, passphrase: f.passphrase },
      f.ip, null, 'auth_kdf', 'guardians:signin');
    if (!ok(s, 'guardian sign-in', [200])) { sleep(10); return; }
    guardianToken = json(s).session.access_token;
  }
  const t = guardianToken;
  const reads = [
    ['/v1/guardian/dashboard', 'guardian/dashboard'],
    ['/v1/identity/learners', 'identity/learners'],
    [`/v1/identity/consents/${f.student_ref}`, 'identity/consents'],
    [`/v1/school/children/${f.student_ref}/classes`, 'school/children/classes'],
  ];
  for (const [path, name] of reads) {
    const r = call('GET', path, null, f.ip, t, 'guardian_reads', name);
    if (r.status === 401) guardianToken = null; // expired: sign in again next iteration
    ok(r, name, [200]);
    sleep(0.5);
  }
  sleep(3);
}

let teacherToken = null;

export function teacherReads() {
  const teachers = SEED.teachers;
  const t = teachers[(exec.vu.idInTest - 1) % teachers.length];
  if (!teacherToken) {
    const s = call('POST', '/v1/school/teachers:signin', { email: t.email, passphrase: t.passphrase, deviceId: 'perf-teacher' },
      t.ip, null, 'auth_kdf', 'teachers:signin');
    if (!ok(s, 'teacher sign-in', [200])) { sleep(10); return; }
    teacherToken = json(s).session.access_token;
  }
  const reads = [
    ['/v1/school/classes', 'school/classes'],
    [`/v1/school/classes/${t.class_id}`, 'school/classes/{id}'],
    [`/v1/school/classes/${t.class_id}/assignments/${t.assignment_id}/progress`, 'school/assignment/progress'],
  ];
  for (const [path, name] of reads) {
    const r = call('GET', path, null, t.ip, teacherToken, 'teacher_reads', name);
    if (r.status === 401) teacherToken = null;
    ok(r, name, [200]);
    sleep(0.5);
  }
  sleep(3);
}

export function handleSummary(data) {
  const out = {};
  out[__ENV.PERF_SUMMARY || '/tmp/taleem-perf-summary.json'] = JSON.stringify(data, null, 2);
  out.stdout = `k6 ${PROFILE} finished; summary JSON written for tests/perf/summarize.py\n`;
  return out;
}

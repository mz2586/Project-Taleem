import { describe, expect, it } from "vitest";

import { ApiError } from "../../student/types";
import { childAccess, familyDashboardModel, familyNudge, type FamilyDashboardModel } from "../dashboard";
import { consent, dashboard, granted, learner, profile, summary } from "./fixtures";

const OFFLINE = new ApiError(0, { code: "OFFLINE" });
const SERVER = new ApiError(500, {});
const SIGNED_OUT = new ApiError(401, {});

const ok = <T,>(value: T) => ({ status: "ok" as const, value });
const err = (error: unknown) => ({ status: "error" as const, error });
const pending = { status: "pending" as const };

function children(model: FamilyDashboardModel) {
  if (model.kind !== "children") throw new Error(`expected children, got ${model.kind}`);
  return model;
}

describe("familyDashboardModel", () => {
  it("is loading until both requests settle", () => {
    expect(familyDashboardModel({ identity: pending, dashboard: ok(dashboard([])) }).kind).toBe("loading");
    expect(familyDashboardModel({ identity: ok(profile([])), dashboard: pending }).kind).toBe("loading");
  });

  it("a newly registered guardian with no children gets the add-a-child state", () => {
    const model = familyDashboardModel({ identity: ok(profile([])), dashboard: ok(dashboard([])) });
    expect(model).toEqual({ kind: "no-children" });
    expect(familyNudge(model)).toBe("add-child");
  });

  it("children who have not answered anything show 'no progress yet', not zeros", () => {
    const model = children(
      familyDashboardModel({
        identity: ok(profile([learner({ consent: granted(["learning_data"]) })])),
        dashboard: ok(dashboard([summary("stu_1")])),
      }),
    );
    expect(model.children[0]!.progress).toEqual({ kind: "none-yet" });
    expect(model.noProgressYet).toBe(true);
  });

  it("a child enrolled but not yet known to the guardian service is 'no progress yet'", () => {
    const model = children(familyDashboardModel({ identity: ok(profile([learner()])), dashboard: ok(dashboard([])) }));
    expect(model.children).toHaveLength(1);
    expect(model.children[0]).toMatchObject({ name: "Ali", access: "not-given", progress: { kind: "none-yet" } });
  });

  it("shows a summary once there are answers", () => {
    const s = summary("stu_1", { total_attempts: 12, objectives_mastered: 2, accuracy: 0.75 });
    const model = children(familyDashboardModel({ identity: ok(profile([learner()])), dashboard: ok(dashboard([s])) }));
    expect(model.children[0]!.progress).toEqual({ kind: "summary", summary: s });
    expect(model.noProgressYet).toBe(false);
  });

  it("both APIs down is a failure, offline when the network is gone", () => {
    expect(familyDashboardModel({ identity: err(OFFLINE), dashboard: err(OFFLINE) })).toEqual({ kind: "failed", failure: "offline" });
    expect(familyDashboardModel({ identity: err(SERVER), dashboard: err(SERVER) })).toEqual({ kind: "failed", failure: "error" });
    expect(familyDashboardModel({ identity: err(SERVER), dashboard: err(OFFLINE) })).toEqual({ kind: "failed", failure: "offline" });
  });

  it("a lost session wins over everything", () => {
    expect(familyDashboardModel({ identity: err(SIGNED_OUT), dashboard: ok(dashboard([])) })).toEqual({
      kind: "failed",
      failure: "signed-out",
    });
    expect(familyDashboardModel({ identity: ok(profile([])), dashboard: err(SIGNED_OUT) })).toEqual({
      kind: "failed",
      failure: "signed-out",
    });
  });

  it("learning service down: names and permissions still shown, progress marked unavailable", () => {
    const model = children(familyDashboardModel({ identity: ok(profile([learner()])), dashboard: err(SERVER) }));
    expect(model.progressUnavailable).toBe(true);
    expect(model.noProgressYet).toBe(false);
    expect(model.children[0]!.progress).toEqual({ kind: "unavailable" });
  });

  it("identity down: progress still shown, children unnamed", () => {
    const s = summary("stu_9", { total_attempts: 3 });
    const model = children(familyDashboardModel({ identity: err(SERVER), dashboard: ok(dashboard([s])) }));
    expect(model.identityUnavailable).toBe(true);
    expect(model.children[0]).toMatchObject({ studentRef: "stu_9", name: null, access: "unknown" });
  });

  it("unions both lists, identity order first, without duplicates", () => {
    const model = children(
      familyDashboardModel({
        identity: ok(profile([learner({ student_ref: "a", display_name: "A" }), learner({ student_ref: "b", display_name: "B" })])),
        dashboard: ok(dashboard([summary("b"), summary("legacy")])),
      }),
    );
    expect(model.children.map((c) => c.studentRef)).toEqual(["a", "b", "legacy"]);
  });
});

describe("childAccess and familyNudge", () => {
  it("locked and suspended accounts win over consent", () => {
    expect(childAccess(learner({ status: "locked", consent: granted(["learning_data"]) }))).toBe("locked");
    expect(childAccess(learner({ status: "suspended" }))).toBe("suspended");
    expect(childAccess(learner({ consent: granted(["learning_data"]) }))).toBe("given");
  });

  it("nudges to unlock first, then to give permission, but never nags after a withdrawal", () => {
    const build = (...ls: ReturnType<typeof learner>[]) =>
      familyDashboardModel({ identity: ok(profile(ls)), dashboard: ok(dashboard([])) });
    expect(familyNudge(build(learner({ status: "locked" }), learner({ student_ref: "x" })))).toBe("unlock");
    expect(familyNudge(build(learner()))).toBe("give-permission");
    expect(familyNudge(build(learner({ consent: consent({ last_change_at: 5 }) })))).toBeNull();
    expect(familyNudge(build(learner({ consent: granted(["learning_data"]) })))).toBeNull();
    expect(familyNudge({ kind: "loading" })).toBeNull();
  });
});

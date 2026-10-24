import { describe, expect, it } from "vitest";

import { submitPath } from "../api";

describe("homework submit routing (§2 assignment vs §6 self-paced)", () => {
  it("sends an assignment item to its assignment", () => {
    expect(submitPath("stu_1", { source: "assignment", assignmentId: "asg_9" }, "ai-hw-1")).toBe(
      "/v1/school/learners/stu_1/homework/asg_9/items/ai-hw-1:submit",
    );
  });

  it("sends lesson practice to the self-paced route by objective, never 'null'", () => {
    const path = submitPath("stu_1", { source: "self_paced", objectiveCode: "MATH-G4-NB-01" }, "ai-hw-1");
    expect(path).toBe("/v1/school/learners/stu_1/homework/self-paced/MATH-G4-NB-01/items/ai-hw-1:submit");
    expect(path).not.toContain("null");
  });
});

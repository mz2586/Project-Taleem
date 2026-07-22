import { describe, expect, it, vi } from "vitest";

import { startAutoDrain } from "../backgroundSync";

class FakeTarget {
  private readonly handlers = new Map<string, EventListener[]>();
  addEventListener(type: string, fn: EventListener): void {
    const list = this.handlers.get(type) ?? [];
    list.push(fn);
    this.handlers.set(type, list);
  }
  removeEventListener(type: string, fn: EventListener): void {
    this.handlers.set(type, (this.handlers.get(type) ?? []).filter((h) => h !== fn));
  }
  dispatch(type: string): void {
    for (const fn of this.handlers.get(type) ?? []) fn(new Event(type));
  }
  count(type: string): number {
    return (this.handlers.get(type) ?? []).length;
  }
}

describe("auto-drain on reconnect", () => {
  it("drains once on start, and again on the online event when online", () => {
    const target = new FakeTarget();
    let online = false;
    const drain = vi.fn(async () => undefined);
    const stop = startAutoDrain({ drain, target, isOnLine: () => online });

    expect(drain).toHaveBeenCalledTimes(0); // offline on start → no drain

    online = true;
    target.dispatch("online");
    expect(drain).toHaveBeenCalledTimes(1);

    stop();
    target.dispatch("online");
    expect(drain).toHaveBeenCalledTimes(1); // unsubscribed
    expect(target.count("online")).toBe(0);
  });

  it("does not drain on an online event while still offline (captive portal)", () => {
    const target = new FakeTarget();
    const drain = vi.fn(async () => undefined);
    startAutoDrain({ drain, target, isOnLine: () => false });
    target.dispatch("online");
    expect(drain).not.toHaveBeenCalled();
  });
});

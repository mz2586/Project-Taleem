import { describe, expect, it } from "vitest";

import { currentlyOnline, makeProbe, watchConnectivity } from "../connectivity";

// A minimal EventTarget stand-in so connectivity can be driven deterministically.
class FakeTarget {
  private readonly handlers = new Map<string, EventListener[]>();
  addEventListener(type: string, fn: EventListener): void {
    const list = this.handlers.get(type) ?? [];
    list.push(fn);
    this.handlers.set(type, list);
  }
  removeEventListener(type: string, fn: EventListener): void {
    const list = (this.handlers.get(type) ?? []).filter((h) => h !== fn);
    this.handlers.set(type, list);
  }
  dispatch(type: string): void {
    for (const fn of this.handlers.get(type) ?? []) fn(new Event(type));
  }
}

describe("connectivity detection", () => {
  it("reports initial state then reacts to offline/online events", async () => {
    const target = new FakeTarget();
    let online = true;
    const states: boolean[] = [];
    const unsub = watchConnectivity((v) => states.push(v), {
      target,
      isOnLine: () => online,
    });

    expect(states[0]).toBe(true); // initial emit
    online = false;
    target.dispatch("offline");
    online = true;
    target.dispatch("online"); // no probe → immediately online
    expect(states).toEqual([true, false, true]);

    unsub();
    target.dispatch("offline");
    expect(states).toHaveLength(3); // unsubscribed — no further updates
  });

  it("uses an active probe to confirm real reachability on 'online'", async () => {
    const target = new FakeTarget();
    const states: boolean[] = [];
    watchConnectivity((v) => states.push(v), {
      target,
      isOnLine: () => true,
      probe: async () => false, // link is up but nothing reachable (captive portal)
    });
    target.dispatch("online");
    await Promise.resolve();
    await Promise.resolve();
    expect(states.at(-1)).toBe(false);
  });

  it("makeProbe returns false when fetch throws", async () => {
    const probe = makeProbe("/health", (async () => {
      throw new Error("offline");
    }) as unknown as typeof fetch);
    expect(await probe()).toBe(false);
  });

  it("currentlyOnline reads the supplied predicate", () => {
    expect(currentlyOnline(() => false)).toBe(false);
  });
});

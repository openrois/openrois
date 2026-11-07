/**
 * Unit tests for emitter.ts, the event emitter under RoISClient and the transport.
 *
 * Run with: npx vitest run
 */

import { describe, it, expect, vi, afterEach } from "vitest";
import { TypedEmitter } from "../src/emitter";

type Events = {
  tick: [count: number, label: string];
  error: [error: Error];
};

/** Emits on demand, which only the class itself may do. */
class Emitter extends TypedEmitter<Events> {
  tick(count: number, label: string = ""): void {
    this.emit("tick", count, label);
  }

  fail(error: Error): void {
    this.emit("error", error);
  }
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("TypedEmitter", () => {
  it("passes every listener the event's arguments, in the order they were added", () => {
    const emitter = new Emitter();
    const calls: string[] = [];
    emitter.on("tick", (count, label) => calls.push(`first ${count} ${label}`));
    emitter.on("tick", (count, label) => calls.push(`second ${count} ${label}`));

    emitter.tick(1, "a");

    expect(calls).toEqual(["first 1 a", "second 1 a"]);
  });

  it("stops calling a listener removed with off(), and leaves the others", () => {
    const emitter = new Emitter();
    const removed = vi.fn();
    const kept = vi.fn();
    emitter.on("tick", removed);
    emitter.on("tick", kept);

    emitter.off("tick", removed);
    emitter.off("tick", vi.fn());
    emitter.tick(1);

    expect(removed).not.toHaveBeenCalled();
    expect(kept).toHaveBeenCalledOnce();
  });

  it("lets a listener remove itself without skipping the next one", () => {
    const emitter = new Emitter();
    const once = () => {
      emitter.off("tick", once);
    };
    const next = vi.fn();
    emitter.on("tick", once);
    emitter.on("tick", next);

    emitter.tick(1);

    expect(next).toHaveBeenCalledOnce();
  });

  it("returns the emitter from on() and off(), so calls can chain", () => {
    const emitter = new Emitter();
    const listener = vi.fn();

    expect(emitter.on("tick", listener).off("tick", listener)).toBe(emitter);
  });

  it("does nothing for an event nobody listens to", () => {
    expect(() => new Emitter().tick(1)).not.toThrow();
  });

  it("logs an error nobody listens to, and does not throw", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const emitter = new Emitter();
    const error = new Error("bad message");

    expect(() => emitter.fail(error)).not.toThrow();

    expect(log).toHaveBeenCalledWith("OpenRoIS:", error);
  });

  it("gives an error to its listeners and does not log it", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const emitter = new Emitter();
    const listener = vi.fn();
    emitter.on("error", listener);
    const error = new Error("bad message");

    emitter.fail(error);

    expect(listener).toHaveBeenCalledWith(error);
    expect(log).not.toHaveBeenCalled();
  });

  it("reports what a listener throws, and calls the next listener", () => {
    const emitter = new Emitter();
    const next = vi.fn();
    const faults = vi.fn();
    const thrown = new Error("listener failed");
    emitter.on("tick", () => {
      throw thrown;
    });
    emitter.on("tick", next);
    emitter.on("error", faults);

    emitter.tick(1);

    expect(next).toHaveBeenCalledOnce();
    expect(faults).toHaveBeenCalledWith(thrown);
  });

  it("wraps a thrown value that is not an Error", () => {
    const emitter = new Emitter();
    const faults = vi.fn();
    emitter.on("tick", () => {
      throw "plain text";
    });
    emitter.on("error", faults);

    emitter.tick(1);

    expect(faults.mock.calls[0][0]).toBeInstanceOf(Error);
    expect(faults.mock.calls[0][0].message).toBe("plain text");
  });

  it("reports an async listener that rejects", async () => {
    const emitter = new Emitter();
    const thrown = new Error("async listener failed");
    const reported = new Promise<Error>((resolve) => emitter.on("error", resolve));
    emitter.on("tick", async () => {
      throw thrown;
    });

    emitter.tick(1);

    await expect(reported).resolves.toBe(thrown);
  });

  it("logs what an error listener throws, and does not call it again", () => {
    const log = vi.spyOn(console, "error").mockImplementation(() => {});
    const emitter = new Emitter();
    const thrown = new Error("error listener failed");
    const listener = vi.fn(() => {
      throw thrown;
    });
    emitter.on("error", listener);

    expect(() => emitter.fail(new Error("bad message"))).not.toThrow();

    expect(listener).toHaveBeenCalledOnce();
    expect(log).toHaveBeenCalledWith("OpenRoIS:", thrown);
  });
});

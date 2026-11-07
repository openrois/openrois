/**
 * A small typed event emitter for RoISClient and WebSocketTransport.
 *
 * Node's EventEmitter would need the `events` package in browsers, its types need
 * @types/node, and it throws on an "error" event with no listener, so one bad message
 * from a server would end the process. Here a fault is an event that nothing can turn
 * into a throw: it goes to the "error" listeners, or to the console if there are none.
 */

/** The events of an emitter: each name maps to its listener's arguments. */
export type EmitterEvents<Events> = Record<keyof Events, unknown[]> & {
  error: [error: Error];
};

/** Base class of whatever emits events. Only the class itself can emit. */
export class TypedEmitter<Events extends EmitterEvents<Events>> {
  // No prototype, so an event name that only JavaScript callers can pass, such as
  // "constructor", finds nothing.
  private readonly listeners: { [E in keyof Events]?: ((...args: Events[E]) => void)[] } =
    Object.create(null);

  /** Add a listener. It stays until off() removes it. */
  on<E extends keyof Events>(event: E, listener: (...args: Events[E]) => void): this {
    (this.listeners[event] ??= []).push(listener);
    return this;
  }

  /** Remove a listener added with on(). */
  off<E extends keyof Events>(event: E, listener: (...args: Events[E]) => void): this {
    const added = this.listeners[event] ?? [];
    const index = added.lastIndexOf(listener);
    if (index !== -1) {
      added.splice(index, 1);
    }
    return this;
  }

  /**
   * Call the listeners of an event. A listener that throws, or an async listener that
   * rejects, is reported as a fault, because the caller is the reader of a socket and
   * must carry on with the next message.
   */
  protected emit<E extends keyof Events>(event: E, ...args: Events[E]): void {
    // A copy, so a listener can remove itself without skipping the next one.
    const listeners = [...(this.listeners[event] ?? [])];
    if (event === "error" && listeners.length === 0) {
      console.error("OpenRoIS:", args[0]);
    }
    for (const listener of listeners) {
      try {
        const returned: unknown = listener(...args);
        if (returned instanceof Promise) {
          returned.catch((fault: unknown) => this.reportFault(event, fault));
        }
      } catch (fault) {
        this.reportFault(event, fault);
      }
    }
  }

  /** Pass on what a listener threw. An "error" listener that throws can only be logged. */
  private reportFault(event: keyof Events, fault: unknown): void {
    if (event === "error") {
      console.error("OpenRoIS:", fault);
      return;
    }
    const error = fault instanceof Error ? fault : new Error(String(fault));
    this.emit("error", ...([error] as unknown as Events["error"]));
  }
}

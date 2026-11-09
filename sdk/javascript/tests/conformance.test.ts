/**
 * The conformance list of testing/conformance/README.md, one test per scenario with the
 * id in its name. tests/coverage.test.ts fails when an id of the list has no test here.
 *
 * This file runs unchanged in Node.js and in a browser, so it uses only the public
 * surface and takes only URLs, which tests/conformance.setup.ts provides. Every fault
 * comes from a RoIS call on `mock/fault` or from a path of the scripted server. W01 to W03
 * stay with testing/conformance/wire_check.py, because a client SDK cannot reach them.
 *
 * The suite runs when OPENROIS_GATEWAY_URL names a gateway with the mock adapter behind
 * it, and is skipped otherwise:
 *
 *   OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npx vitest run tests/conformance.test.ts
 *   OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npm run test:browser
 *
 * OPENROIS_MOCK_ENGINE_ID names the engine of the mock adapter, `mock` by default.
 */

import { beforeAll, describe, expect, inject, it } from "vitest";
import {
  COMPONENT_REF,
  ConnectionError,
  RoISClient,
  RoISError,
  RpcError,
  TransportError,
  allOf,
  componentRef,
  componentType,
  like,
  quote,
  type RoISClientEvents,
} from "../src/rois-client";

const gatewayUrl = inject("gatewayUrl");
const scriptedUrl = inject("scriptedUrl");
const engineId = inject("engineId");
const suite = gatewayUrl ? describe : describe.skip;

const DETECTION = `${engineId}/person_detection`;
const NAVIGATION = `${engineId}/navigation`;
const INFORMATION = `${engineId}/system_information`;
const FAULT = `${engineId}/fault`;

const COMPLETED = "rois.command.completed";
const NOTIFY_EVENT = "rois.event.notify_event";
const NOTIFY_ERROR = "rois.system.notify_error";
const PROFILE_CHANGED = "rois.system.profile_changed";

/** The longest wait for one notification, enough for a detection at full time scale. */
const WAIT = 20_000;

/** The longest a scenario takes, which holds several waits at full time scale. */
const SCENARIO = 60_000;

/** How many commands the scenario on lost completions runs. */
const COMPLETION_ROUNDS = 100;

/** How many parameter changes it runs, which take longer than a command. */
const PARAMETER_ROUNDS = 5;

type Notification =
  | typeof COMPLETED
  | typeof NOTIFY_EVENT
  | typeof NOTIFY_ERROR
  | typeof PROFILE_CHANGED;
type Params<N extends Notification> = RoISClientEvents[N][0];

/**
 * A client and every notification it received since it connected, which is the recipe
 * of the SDK README: the listener is there before the call whose ids it records.
 */
class Session {
  readonly received: { [N in Notification]: Params<N>[] } = {
    [COMPLETED]: [],
    [NOTIFY_EVENT]: [],
    [NOTIFY_ERROR]: [],
    [PROFILE_CHANGED]: [],
  };
  private readonly waiters = new Set<() => void>();

  constructor(readonly client: RoISClient) {
    client.on(COMPLETED, (params) => this.record(COMPLETED, params));
    client.on(NOTIFY_EVENT, (params) => this.record(NOTIFY_EVENT, params));
    client.on(NOTIFY_ERROR, (params) => this.record(NOTIFY_ERROR, params));
    client.on(PROFILE_CHANGED, (params) => this.record(PROFILE_CHANGED, params));
  }

  private record<N extends Notification>(method: N, params: Params<N>): void {
    this.received[method].push(params);
    for (const wake of [...this.waiters]) {
      wake();
    }
  }

  /** Wait until `find` returns something, looking again at each notification. */
  private until<T>(find: () => T | undefined, what: string): Promise<T> {
    return new Promise((resolve, reject) => {
      const look = (): boolean => {
        const found = find();
        if (found === undefined) {
          return false;
        }
        clearTimeout(timer);
        this.waiters.delete(wake);
        resolve(found);
        return true;
      };
      const wake = (): void => {
        look();
      };
      const timer = setTimeout(() => {
        this.waiters.delete(wake);
        reject(new Error(`No ${what} within ${WAIT} ms`));
      }, WAIT);
      if (!look()) {
        this.waiters.add(wake);
      }
    });
  }

  /** The first notification of a method whose params match, waiting for it if needed. */
  next<N extends Notification>(
    method: N,
    match: (params: Params<N>) => boolean = () => true,
  ): Promise<Params<N>> {
    return this.until(() => this.received[method].find(match), method);
  }

  /** Wait until a method has been received more than `count` times. */
  beyond(method: Notification, count: number): Promise<number> {
    return this.until(() => {
      const total = this.received[method].length;
      return total > count ? total : undefined;
    }, `${method} past ${count}`);
  }

  /** Wait until a command completes, and return its status. */
  async completion(commandId: string): Promise<string> {
    const params = await this.next(COMPLETED, (p) => p.command_id === commandId);
    return params.status;
  }
}

/** Run a session on a new client, and close it however the session ends. */
async function session<T>(run: (live: Session) => Promise<T>, url: string = gatewayUrl): Promise<T> {
  const client = await RoISClient.connect(url);
  try {
    return await run(new Session(client));
  } finally {
    await client.disconnect();
  }
}

/** Expect a call to fail with a RoIS return code. */
async function refused(call: Promise<unknown>, returnCode: string): Promise<void> {
  const error = await call.then(
    () => undefined,
    (reason: unknown) => reason,
  );
  expect(error).toBeInstanceOf(RoISError);
  expect((error as RoISError).returnCode).toBe(returnCode);
}

/** What a client reports when its connection closes. */
function closeOf(client: RoISClient): Promise<[code: number, reason: string]> {
  return new Promise((resolve) => {
    client.on("close", (code, reason) => resolve([code, reason]));
  });
}

/** The target_positions parameter of the navigation. */
function targets(value: string) {
  return [{ name: "target_positions", data_type_ref: "string[]", value }];
}

/** A command that gives its text back as a result, which tells it from any other. */
function echo(text: string) {
  return {
    component_ref: FAULT,
    command_type: "echo",
    arguments: [{ name: "text", data_type_ref: "string", value: text }],
  };
}

/** A command that ends with a chosen status. */
function endWith(status: string) {
  return {
    component_ref: FAULT,
    command_type: "end_with",
    arguments: [{ name: "status", data_type_ref: "string", value: status }],
  };
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

/** Whether the stack answers and the mock adapter has joined it. */
async function stackIsUp(): Promise<boolean> {
  try {
    return await session(async ({ client }) => (await client.search()).includes(FAULT));
  } catch {
    return false;
  }
}

suite("the conformance list", { timeout: SCENARIO }, () => {
  beforeAll(async () => {
    // The stack may still be starting when the run begins.
    const deadline = Date.now() + SCENARIO;
    while (!(await stackIsUp())) {
      if (Date.now() > deadline) {
        throw new Error(`${FAULT} did not appear at ${gatewayUrl}`);
      }
      await sleep(500);
    }
  }, SCENARIO);

  it("C01 disconnect is safe twice, in turn and overlapping, and a call after it fails locally", async () => {
    const client = await RoISClient.connect(gatewayUrl);
    const closed: number[] = [];
    client.on("close", (code) => closed.push(code));

    await client.disconnect();
    await client.disconnect();

    expect(closed).toEqual([1000]);
    await expect(client.search()).rejects.toBeInstanceOf(TransportError);
    await expect(client.search()).rejects.toThrow("not connected");

    // The last call is what a block of `await using` runs when it ends during a disconnect.
    const overlapped = await RoISClient.connect(gatewayUrl);
    await Promise.all([
      overlapped.disconnect(),
      overlapped.disconnect(),
      overlapped[Symbol.asyncDispose](),
    ]);
    await expect(overlapped.search()).rejects.toThrow("not connected");
  });

  it("C02 getProfile lists the sub profile and each component profile", async () => {
    await session(async ({ client }) => {
      const { profile, component_profiles } = await client.getProfile();
      const engines = (profile.sub_profiles ?? []).map((p) => p.identifier.code);
      expect(engines).toContain(engineId);
      for (const ref of [DETECTION, NAVIGATION, INFORMATION, FAULT]) {
        expect(component_profiles[ref]).toBeDefined();
      }
      const navigation = component_profiles[NAVIGATION];
      expect(navigation?.function).toBe("actuation");
      expect((navigation?.command_profiles ?? []).map((c) => c.name)).toEqual([
        "start",
        "stop",
        "suspend",
        "resume",
      ]);
    });
  });

  it("C03 search selects by ref, by type, with LIKE and with AND", async () => {
    const byType = componentType({ authority: "OMG", code: "Navigation" });
    const prefix = like(COMPONENT_REF, `${engineId}/%`);
    await session(async ({ client }) => {
      expect(await client.search(componentRef(NAVIGATION))).toEqual([NAVIGATION]);
      expect(await client.search(byType)).toEqual([NAVIGATION]);
      expect(await client.search(allOf(prefix, byType))).toEqual([NAVIGATION]);
      // Each term matches alone, so an empty answer shows that both were applied.
      expect(await client.search(componentRef(DETECTION))).toEqual([DETECTION]);
      expect(await client.search(allOf(componentRef(DETECTION), byType))).toEqual([]);
      expect(await client.search(prefix)).toEqual(
        expect.arrayContaining([DETECTION, NAVIGATION, INFORMATION, FAULT]),
      );
      await refused(client.search("nonsense !! 1"), "BAD_PARAMETER");
    });
  });

  it("C04 a quote in a condition value survives the builders", async () => {
    await session(async ({ client }) => {
      expect(quote("it's")).toBe("'it''s'");
      // A quote that reached the engine unescaped would end the literal early, and the
      // engine would answer BAD_PARAMETER where these find nothing.
      expect(await client.search(componentRef("it's/odd"))).toEqual([]);
      expect(await client.search(like(COMPONENT_REF, "it's%"))).toEqual([]);
    });
  });

  it("C05 query follows its condition, UNSUPPORTED with no match, BAD_PARAMETER with several", async () => {
    await session(async ({ client }) => {
      const position = await client.query("robot_position", componentRef(INFORMATION));
      expect(position.map((r) => r.name)).toEqual(["position_data", "robot_ref", "timestamp"]);
      await refused(client.query("no_such_query"), "UNSUPPORTED");
      await refused(client.query("component_status"), "BAD_PARAMETER");
      // Several components declare this query, so only the condition can make it answer.
      const status = await client.query("component_status", componentRef(NAVIGATION));
      expect(status.map((r) => r.name)).toContain("status");
    });
  });

  it("C06 bind, bindAny, release, an actuator refuses a second client, a sensor is shared", async () => {
    await session(async ({ client: first }) => {
      await session(async ({ client: second }) => {
        await first.bind(NAVIGATION);
        await refused(second.bind(NAVIGATION), "OUT_OF_RESOURCES");
        await refused(second.bindAny(componentRef(NAVIGATION)), "OUT_OF_RESOURCES");

        await first.bind(DETECTION);
        await second.bind(DETECTION);

        await first.release(NAVIGATION);
        expect(await second.bindAny(componentRef(NAVIGATION))).toBe(NAVIGATION);
      });
    });
  });

  it("C07 a bind ends with its session", async () => {
    await session(async ({ client }) => {
      await client.bind(NAVIGATION);
    });
    await session(async ({ client }) => {
      await client.bind(NAVIGATION);
    });
  });

  it("C08 setParameter applies and completes, a bad value changes nothing", async () => {
    await session(async (live) => {
      const { client } = live;
      await client.bind(NAVIGATION);
      const applied = await client.setParameter(NAVIGATION, targets('["kitchen"]'));
      expect(await live.completion(applied)).toBe("OK");

      await refused(client.setParameter(NAVIGATION, targets("not json")), "BAD_PARAMETER");

      const parameters = await client.getParameter(NAVIGATION);
      const value = parameters.find((p) => p.name === "target_positions")?.value;
      expect(value).toContain("kitchen");
      await live.completion(await client.setParameter(NAVIGATION, targets('["home"]')));
    });
  });

  it("C09 execute runs from bind to reached_target, with ids from the reply", async () => {
    await session(async (live) => {
      const { client } = live;
      await client.bind(NAVIGATION);
      await live.completion(await client.setParameter(NAVIGATION, targets('["kitchen"]')));
      const subscribeId = await client.subscribe("reached_target", componentRef(NAVIGATION));

      const [commandId = ""] = await client.execute([
        { component_ref: NAVIGATION, command_type: "start" },
      ]);

      expect(await live.completion(commandId)).toBe("OK");
      const event = await live.next(NOTIFY_EVENT, (p) => p.subscribe_id === subscribeId);
      expect(event.event_type).toBe("reached_target");
      expect(event.results?.find((r) => r.name === "target")?.value).toBe("kitchen");
      expect(await client.getCommandResult(commandId)).toEqual([]);
      await live.completion(await client.setParameter(NAVIGATION, targets('["home"]')));
    });
  });

  it("C10 a sequence with branches returns ids in order, branch by branch", async () => {
    await session(async (live) => {
      const { client } = live;
      await client.bind(FAULT);

      const ids = await client.execute([
        echo("first"),
        {
          branch_list: [
            { command_list: [echo("left one"), echo("left two")] },
            { command_list: [echo("right")] },
          ],
        },
        echo("last"),
      ]);

      expect(await Promise.all(ids.map((id) => live.completion(id)))).toEqual(
        ids.map(() => "OK"),
      );
      // Each command gives back its own text, so the ids must name them in this order.
      const results = await Promise.all(ids.map((id) => client.getCommandResult(id)));
      expect(results.map(([text]) => text?.value)).toEqual([
        "first",
        "left one",
        "left two",
        "right",
        "last",
      ]);
    });
  });

  it("C11 a listener added before the call sees every completion of the ids in the reply", async () => {
    await session(async (live) => {
      const { client } = live;
      await client.bind(NAVIGATION);
      const ids: string[] = [];
      for (let round = 0; round < COMPLETION_ROUNDS; round += 1) {
        const [id = ""] = await client.execute([
          { component_ref: NAVIGATION, command_type: "stop" },
        ]);
        ids.push(id);
        expect(await live.completion(id)).toBe("OK");
      }
      for (let round = 0; round < PARAMETER_ROUNDS; round += 1) {
        const id = await client.setParameter(NAVIGATION, targets('["home"]'));
        ids.push(id);
        expect(await live.completion(id)).toBe("OK");
      }
      const seen = live.received[COMPLETED].map((p) => p.command_id);
      expect(seen).toEqual(ids);
    });
  });

  it("C12 a command ending badly aborts the later items, release aborts with ABORT", async () => {
    await session(async (live) => {
      const { client } = live;
      await client.bind(FAULT);
      const [failing = "", later = "", last = ""] = await client.execute([
        endWith("ERROR"),
        echo("never runs"),
        echo("never runs either"),
      ]);
      expect(await live.completion(failing)).toBe("ERROR");
      expect(await live.completion(later)).toBe("ABORT");
      expect(await live.completion(last)).toBe("ABORT");

      await client.bind(NAVIGATION);
      const [running = ""] = await client.execute([
        { component_ref: NAVIGATION, command_type: "start" },
      ]);
      await client.release(NAVIGATION);
      expect(await live.completion(running)).toBe("ABORT");
    });
  });

  it("C13 subscribe, unsubscribe and two clients on one event", async () => {
    const condition = componentRef(DETECTION);
    await session(async (first) => {
      await session(async (second) => {
        const one = await first.client.subscribe("person_detected", condition);
        expect(await first.client.subscribe("person_detected", condition)).toBe(one);
        const other = await second.client.subscribe("person_detected", condition);
        expect(other).not.toBe(one);
        await first.client.unsubscribe(`${engineId}/sub-0`);
        // This condition selects a component without the event, which only a condition
        // that reaches the engine can refuse. No event of the mock adapter is declared
        // twice, so the refusal is what shows it here.
        await refused(
          first.client.subscribe("person_detected", componentRef(NAVIGATION)),
          "UNSUPPORTED",
        );

        await first.next(NOTIFY_EVENT, (p) => p.subscribe_id === one);
        await second.next(NOTIFY_EVENT, (p) => p.subscribe_id === other);
        expect(first.received[NOTIFY_EVENT].every((p) => p.subscribe_id === one)).toBe(true);
        expect(second.received[NOTIFY_EVENT].every((p) => p.subscribe_id === other)).toBe(true);

        // One client leaves by unsubscribing. Two more events prove the other still
        // receives them while the one that left does not, because a reply and the events
        // around it arrive in order on one socket.
        await first.client.unsubscribe(one);
        const left = first.received[NOTIFY_EVENT].length;
        await second.beyond(NOTIFY_EVENT, second.received[NOTIFY_EVENT].length + 1);
        expect(first.received[NOTIFY_EVENT]).toHaveLength(left);

        // Then it leaves by ending its session.
        await first.client.subscribe("person_detected", condition);
        await first.client.disconnect();
        await second.beyond(NOTIFY_EVENT, second.received[NOTIFY_EVENT].length);
      });
    });
  });

  it("C14 notify_event results equal getEventDetail", async () => {
    await session(async (live) => {
      await live.client.subscribe("person_detected", componentRef(DETECTION));
      const event = await live.next(NOTIFY_EVENT);
      expect(event.results?.map((r) => r.name)).toEqual(["number", "timestamp"]);
      expect(await live.client.getEventDetail(event.event_id)).toEqual(event.results);
    });
  });

  it("C15 notify_error reaches each client that holds the component, and getErrorDetail reads it", async () => {
    await session(async (first) => {
      await session(async (second) => {
        await first.client.bind(FAULT);
        await second.client.bind(FAULT);
        await first.client.execute([{ component_ref: FAULT, command_type: "raise_error" }]);

        const { error_id: errorId } = await first.next(NOTIFY_ERROR);
        await second.next(NOTIFY_ERROR, (p) => p.error_id === errorId);
        const detail = await first.client.getErrorDetail(errorId);
        expect(detail.find((r) => r.name === "component_ref")?.value).toBe(FAULT);

        // The error clears by itself, and the scenarios after this one need the component.
        const deadline = Date.now() + WAIT;
        const cleared = async (): Promise<boolean> => {
          try {
            await first.client.getErrorDetail(errorId);
            return false;
          } catch (error) {
            return error instanceof RoISError && error.returnCode === "BAD_PARAMETER";
          }
        };
        while (!(await cleared())) {
          expect(Date.now()).toBeLessThan(deadline);
          await sleep(100);
        }
      });
    });
  });

  it("C16 profile_changed arrives when an engine joins and when it leaves", async () => {
    const hasPeer = async (client: RoISClient): Promise<boolean> => {
      const { profile } = await client.getProfile();
      return (profile.sub_profiles ?? []).some((p) => p.identifier.code === "mock_peer");
    };
    await session(async (live) => {
      const { client } = live;
      await client.bind(FAULT);
      expect(await hasPeer(client)).toBe(false);

      await client.execute([{ component_ref: FAULT, command_type: "peer_join" }]);

      await live.beyond(PROFILE_CHANGED, 0);
      expect(await hasPeer(client)).toBe(true);
      await live.beyond(PROFILE_CHANGED, 1);
      expect(await hasPeer(client)).toBe(false);
    });
  });

  it("C17 METHOD_NOT_FOUND through the raw send reaches the caller as RpcError", async () => {
    await session(async ({ client }) => {
      const error = await client.transport.send("rois.bogus").catch((reason: unknown) => reason);
      expect(error).toBeInstanceOf(RpcError);
      expect((error as RpcError).code).toBe(-32601);
      await expect(client.search(componentRef(NAVIGATION))).resolves.toEqual([NAVIGATION]);
    });
  });

  it("C18 replies in reverse order reach the right callers", async () => {
    await session(async ({ client }) => {
      const answered: string[] = [];
      const ask = async (condition: string): Promise<string[]> => {
        const refs = await client.search(condition);
        answered.push(condition);
        return refs;
      };

      const replies = await Promise.all(["one", "two", "three"].map(ask));

      expect(replies).toEqual([["one"], ["two"], ["three"]]);
      expect(answered).toEqual(["three", "two", "one"]);
    }, `${scriptedUrl}/reverse`);
  });

  it("C19 a malformed message reaches the error listener, and the client keeps working", async () => {
    await session(async ({ client }) => {
      const errors: Error[] = [];
      client.on("error", (error) => errors.push(error));

      await expect(client.search("before")).resolves.toEqual(["before"]);

      expect(errors).toHaveLength(2);
      expect(errors.every((error) => error instanceof TransportError)).toBe(true);
      await expect(client.search("after")).resolves.toEqual(["after"]);
    }, `${scriptedUrl}/malformed`);
  });

  it("C20 a dropped connection fails pending requests and fires close", async () => {
    const client = await RoISClient.connect(`${scriptedUrl}/drop`);
    const closed = closeOf(client);

    const calls = await Promise.allSettled([
      client.search("one"),
      client.search("two"),
      client.search("three"),
    ]);

    for (const call of calls) {
      expect(call.status).toBe("rejected");
      expect((call as PromiseRejectedResult).reason).toBeInstanceOf(ConnectionError);
    }
    expect((await closed)[0]).toBe(1006);
    await expect(client.search()).rejects.toBeInstanceOf(TransportError);
  });

  it("C21 a server close reaches close with its code and reason", async () => {
    const client = await RoISClient.connect(`${scriptedUrl}/close-1001`);
    const closed = closeOf(client);

    await expect(client.search("only")).resolves.toEqual(["only"]);

    await expect(closed).resolves.toEqual([1001, "scripted close"]);
  });
});

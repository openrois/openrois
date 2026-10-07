/**
 * RoISClient sessions against a live gateway with the mock adapter behind it.
 *
 * The suite runs when OPENROIS_GATEWAY_URL names the gateway, for example after
 * `docker compose up` at the repository root:
 *
 *   OPENROIS_GATEWAY_URL=ws://127.0.0.1:8765 npx vitest run tests/gateway.test.ts
 *
 * Without it the suite is skipped. OPENROIS_MOCK_ENGINE_ID names the engine of the
 * mock adapter, `mock` by default. Starting compose with OPENROIS_MOCK_TIME_SCALE=0.1
 * makes the simulated work, and so the suite, ten times faster.
 */

import { describe, it, expect, beforeAll } from "vitest";
import { RoISClient, RoISError, componentRef, type RoISClientEvents } from "../src/rois-client";

const url = process.env.OPENROIS_GATEWAY_URL ?? "";
const engineId = process.env.OPENROIS_MOCK_ENGINE_ID ?? "mock";
const suite = url ? describe : describe.skip;

const DETECTION = `${engineId}/person_detection`;
const NAVIGATION = `${engineId}/navigation`;
const INFORMATION = `${engineId}/system_information`;

/** Long enough for a five-second detection interval at full time scale. */
const TIMEOUT = 20_000;

type Notification = "rois.command.completed" | "rois.event.notify_event";
type Params<N extends Notification> = RoISClientEvents[N][0];

/**
 * A client and every notification it received since it connected, so a test never
 * misses one that arrives together with the reply that announces it.
 */
class Session {
  private readonly received: { [N in Notification]: Params<N>[] } = {
    "rois.command.completed": [],
    "rois.event.notify_event": [],
  };
  private readonly waiters = new Set<() => void>();

  constructor(readonly client: RoISClient) {
    client.on("rois.command.completed", (params) => this.record("rois.command.completed", params));
    client.on("rois.event.notify_event", (params) => this.record("rois.event.notify_event", params));
  }

  private record<N extends Notification>(method: N, params: Params<N>): void {
    this.received[method].push(params);
    for (const wake of [...this.waiters]) {
      wake();
    }
  }

  /** The first notification of a method whose params match, waiting for it if needed. */
  next<N extends Notification>(method: N, match: (params: Params<N>) => boolean): Promise<Params<N>> {
    return new Promise((resolve, reject) => {
      const look = (): boolean => {
        const found = this.received[method].find(match);
        if (found === undefined) {
          return false;
        }
        clearTimeout(timer);
        this.waiters.delete(wake);
        resolve(found);
        return true;
      };
      const wake = () => {
        look();
      };
      const timer = setTimeout(() => {
        this.waiters.delete(wake);
        reject(new Error(`No ${method} within ${TIMEOUT} ms`));
      }, TIMEOUT);
      if (!look()) {
        this.waiters.add(wake);
      }
    });
  }

  /** Wait until a command completes, and return its status. */
  async completion(commandId: string): Promise<string> {
    const params = await this.next("rois.command.completed", (p) => p.command_id === commandId);
    return params.status;
  }
}

/** Run a session on a new client, and close it however the session ends. */
async function session(run: (session: Session) => Promise<void>): Promise<void> {
  const client = await RoISClient.connect(url);
  try {
    await run(new Session(client));
  } finally {
    await client.disconnect();
  }
}

suite("a gateway with the mock adapter", () => {
  beforeAll(async () => {
    // The adapter may still be registering right after the stack starts.
    const deadline = Date.now() + TIMEOUT;
    await session(async ({ client }) => {
      while (!(await client.search()).includes(NAVIGATION)) {
        if (Date.now() > deadline) {
          throw new Error(`${NAVIGATION} did not appear at ${url}`);
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    });
  }, TIMEOUT);

  it("lists the mock adapter as a sub profile with its component profiles", async () => {
    await session(async ({ client }) => {
      const { profile, component_profiles } = await client.getProfile();
      const engines = (profile?.sub_profiles ?? []).map((p) => p.identifier.code);
      expect(engines).toContain(engineId);
      for (const ref of [DETECTION, NAVIGATION, INFORMATION]) {
        expect(component_profiles?.[ref]).toBeDefined();
      }
      const navigation = component_profiles?.[NAVIGATION];
      expect(navigation?.function).toBe("actuation");
      expect((navigation?.command_profiles ?? []).map((c) => c.name)).toEqual([
        "start",
        "stop",
        "suspend",
        "resume",
      ]);
    });
  });

  it("answers queries of one component", async () => {
    await session(async ({ client }) => {
      const position = await client.query("robot_position", componentRef(INFORMATION));
      expect(position.map((r) => r.name)).toEqual(["position_data", "robot_ref", "timestamp"]);
      const status = await client.query("component_status", componentRef(NAVIGATION));
      expect(status[0]?.value).toMatch(/^(READY|BUSY)$/);
    });
  });

  it("drives the navigation from bind to reached_target", async () => {
    await session(async (live) => {
      const { client } = live;
      await client.bind(NAVIGATION);
      const configured = await client.setParameter(NAVIGATION, [
        { name: "target_positions", data_type_ref: "string[]", value: '["kitchen"]' },
      ]);
      expect(configured.startsWith(`${engineId}/`)).toBe(true);
      expect(await live.completion(configured)).toBe("OK");

      const subscribeId = await client.subscribe("reached_target", componentRef(NAVIGATION));
      const [commandId = ""] = await client.execute([
        { component_ref: NAVIGATION, command_type: "start" },
      ]);
      expect(await live.completion(commandId)).toBe("OK");
      const event = await live.next("rois.event.notify_event", (p) => p.subscribe_id === subscribeId);
      expect(event.results?.find((r) => r.name === "target")?.value).toBe("kitchen");
      expect(await client.getEventDetail(event.event_id)).toEqual(event.results);
      expect(await client.getCommandResult(commandId)).toEqual([]);
      await client.unsubscribe(subscribeId);
      await client.release(NAVIGATION);
    });
  }, TIMEOUT);

  it("runs a sequence item by item, a group at once", async () => {
    await session(async (live) => {
      const { client } = live;
      await client.bind(NAVIGATION);
      const ids = await client.execute([
        { component_ref: DETECTION, command_type: "start" },
        {
          command_list: [
            { component_ref: DETECTION, command_type: "suspend" },
            { component_ref: NAVIGATION, command_type: "suspend" },
          ],
        },
      ]);
      const statuses = await Promise.all(ids.map((id) => live.completion(id)));
      expect(statuses).toEqual(["OK", "OK", "OK"]);
      await client.release(NAVIGATION);
    });
  }, TIMEOUT);

  it("keeps a bound navigation for the client that bound it", async () => {
    await session(async (holder) => {
      await holder.client.bind(NAVIGATION);
      await session(async ({ client: other }) => {
        await expect(other.bind(NAVIGATION)).rejects.toThrow(RoISError);
        await expect(
          other.execute([{ component_ref: NAVIGATION, command_type: "stop" }]),
        ).rejects.toThrow(RoISError);
      });
    });
    // The binding ends with the session that held it.
    await session(async ({ client }) => {
      await client.bind(NAVIGATION);
      await client.release(NAVIGATION);
    });
  });

  it("relays the events an engine below the gateway emits", async () => {
    await session(async (live) => {
      const subscribeId = await live.client.subscribe("person_detected", componentRef(DETECTION));
      expect(subscribeId.startsWith(`${engineId}/`)).toBe(true);
      const event = await live.next("rois.event.notify_event", (p) => p.subscribe_id === subscribeId);
      expect(event.event_type).toBe("person_detected");
      expect(event.results?.map((r) => r.name)).toEqual(["number", "timestamp"]);
      await live.client.unsubscribe(subscribeId);
    });
  }, TIMEOUT);

  it("refuses a command id in the namespace of an engine", async () => {
    await session(async ({ client }) => {
      const refused = client.execute([
        { component_ref: DETECTION, command_type: "start", command_id: `${engineId}/mine` },
      ]);
      await expect(refused).rejects.toThrow(RoISError);
    });
  });
});

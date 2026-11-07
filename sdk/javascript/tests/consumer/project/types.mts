// A typed consumer with no @types/node, which is also what a browser project has. The
// tsconfig leaves skipLibCheck off and sets no lib, so the published declarations are
// checked as well, and have to bring what they need from beyond the default lib.
import {
  ConnectionError,
  RoISClient,
  RoISError,
  allOf,
  componentRef,
  like,
  type EngineProfile,
  type RoISClientEvents,
} from "@openrois/sdk";
import { WebSocketTransport, type TransportOptions } from "@openrois/sdk/transport";

const options: TransportOptions = { connectTimeout: 1000 };
const transport = new WebSocketTransport(options);
const client = await RoISClient.connect("ws://127.0.0.1:8765", { transport: options });

const profile: EngineProfile = await client.getProfile();
const refs: string[] = await client.search(allOf(like("component_ref", "mock/%"), componentRef("a")));
const ids: string[] = await client.execute([{ component_ref: "a", command_type: "start" }]);

client.on("rois.command.completed", ({ command_id, status }) => {
  const id: string = command_id;
  console.log(id, status);
});
client.on("close", (code: number, reason: string) => console.log(code, reason));
client.on("error", (error: Error) => console.log(error.message));

const params: RoISClientEvents["rois.event.notify_event"][0] | undefined = undefined;

async function closes(): Promise<void> {
  await using scoped = await RoISClient.connect("ws://127.0.0.1:8765");
  await scoped.search();
}

function fails(error: unknown): string {
  if (error instanceof RoISError) {
    return error.returnCode;
  }
  return error instanceof ConnectionError ? error.url : "";
}

// @ts-expect-error A name outside the listen names is a compile error.
client.on("reached_target", () => {});
// @ts-expect-error once is not part of the surface.
client.once("close", () => {});
// @ts-expect-error emit stays internal.
client.emit("close", 1000, "");
// @ts-expect-error A command needs a component_ref.
await client.execute([{ command_type: "start" }]);

export { closes, fails, ids, params, profile, refs, transport };

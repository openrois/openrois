import type { CommandUnitSequenceItemInput } from "@openrois/sdk";
import type { Parameter } from "@openrois/interfaces";

/**
 * The @openrois/sdk calls behind each action of the inspector, as TypeScript a
 * service application would write them. Each view shows the snippet of what it does.
 */

const q = (text: string) => JSON.stringify(text);

export function connectSnippet(url: string): string {
  return `import { RoISClient, componentRef } from "@openrois/sdk";

const client = await RoISClient.connect(${q(url)});
const { profile, component_profiles } = await client.getProfile();`;
}

export function bindSnippet(ref: string, bound: boolean): string {
  return bound ? `await client.release(${q(ref)});` : `await client.bind(${q(ref)});`;
}

export function querySnippet(ref: string, queryType: string, args: Record<string, string>): string {
  const names = Object.keys(args);
  if (names.length === 0) {
    return `const results = await client.query(${q(queryType)}, componentRef(${q(ref)}));`;
  }
  const parts = [`componentRef(${q(ref)})`, ...names.map((n) => `eq(${q(n)}, ${q(args[n])})`)];
  return `import { allOf, eq } from "@openrois/sdk";

const results = await client.query(
  ${q(queryType)},
  allOf(${parts.join(", ")}),
);`;
}

export function parameterSnippet(ref: string, parameters: Parameter[]): string {
  return `const commandId = await client.setParameter(${q(ref)}, ${JSON.stringify(parameters, null, 2)});`;
}

export function executeSnippet(list: CommandUnitSequenceItemInput[]): string {
  return `client.on("rois.command.completed", ({ command_id, status }) => {
  console.log(command_id, status);
});

const commandIds = await client.execute(${JSON.stringify(list, null, 2)});`;
}

export function subscribeSnippet(ref: string, eventType: string): string {
  return `client.on("rois.event.notify_event", (event) => console.log(event));

const subscribeId = await client.subscribe(${q(eventType)}, componentRef(${q(ref)}));`;
}

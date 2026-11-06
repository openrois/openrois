import { RoISClient, componentRef } from "@openrois/sdk";
import { WebSocketTransport } from "@openrois/sdk/transport";

const client = await RoISClient.connect("ws://127.0.0.1:8765");
console.log(await client.search(componentRef("mock/navigation")), WebSocketTransport);
await client.disconnect();

import { Engine } from './engine.js';
import { WsServer } from './ws-server.js';

const HOST = process.env.ENGINE_HOST ?? '0.0.0.0';
const PORT = Number(process.env.ENGINE_PORT ?? 8765);

const engine = new Engine(true);
const wsServer = new WsServer(engine);

wsServer.start(HOST, PORT);

console.log(`OpenRoIS Gateway ready on ws://${HOST}:${PORT}`);

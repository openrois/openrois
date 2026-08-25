import { Router } from './router.js';
import { WsServer } from './ws-server.js';

const HOST = process.env.ENGINE_HOST ?? '0.0.0.0';
const PORT = Number(process.env.ENGINE_PORT ?? 8765);

const router = new Router();
const wsServer = new WsServer(router);

wsServer.start(HOST, PORT);

console.log(`OpenRoIS Engine ready on ws://${HOST}:${PORT}`);

import type { WebSocketLike } from "@openrois/sdk/transport";

/** One JSON-RPC frame as it crossed the connection. */
export interface Frame {
  direction: "sent" | "received";
  text: string;
}

/**
 * A WebSocket factory for RoISClient that reports every frame it sends and receives.
 *
 * The SDK takes a factory in its transport options. Wrapping the browser WebSocket
 * there shows the exact JSON-RPC traffic of the session without reaching into the SDK.
 */
export function recordingWebSocket(onFrame: (frame: Frame) => void): (url: string) => WebSocketLike {
  return (url) => {
    const socket = new WebSocket(url);
    const wrapper: WebSocketLike = {
      send(data: string) {
        onFrame({ direction: "sent", text: data });
        socket.send(data);
      },
      close(code?: number, reason?: string) {
        socket.close(code, reason);
      },
      get readyState() {
        return socket.readyState;
      },
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
    };
    socket.onopen = (event) => wrapper.onopen?.({ type: event.type });
    socket.onclose = (event) =>
      wrapper.onclose?.({ code: event.code, reason: event.reason, type: event.type });
    socket.onerror = (event) => wrapper.onerror?.({ type: event.type });
    socket.onmessage = (event) => {
      if (typeof event.data === "string") {
        onFrame({ direction: "received", text: event.data });
      }
      wrapper.onmessage?.({ data: event.data, type: event.type });
    };
    return wrapper;
  };
}

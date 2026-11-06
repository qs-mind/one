// A WebSocket server just big enough for the page bridge (RFC 6455 text frames, ping, close), so the walks need no
// package: on 127.0.0.1, a random port, and only for a client that knows the one-run token (in the URL's path).
import { createHash, randomBytes } from "node:crypto";
import { createServer } from "node:http";

const GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11";

function frame(text, opcode = 1) {
  const body = Buffer.from(text, "utf8");
  const head = body.length < 126 ? Buffer.from([0x80 | opcode, body.length]) : body.length < 65536 ? Buffer.alloc(4) : Buffer.alloc(10);
  if (body.length >= 126 && body.length < 65536) {
    head[0] = 0x80 | opcode;
    head[1] = 126;
    head.writeUInt16BE(body.length, 2);
  } else if (body.length >= 65536) {
    head[0] = 0x80 | opcode;
    head[1] = 127;
    head.writeBigUInt64BE(BigInt(body.length), 2);
  }
  return Buffer.concat([head, body]);
}

/** Starts the server; `onSocket({ send, close, onMessage })` is called for each client that shows the token. */
export async function serve(onSocket) {
  const token = randomBytes(24).toString("hex");
  const server = createServer((_, res) => res.writeHead(404).end());
  const open = new Set();
  server.on("upgrade", (req, socket) => {
    open.add(socket);
    socket.on("close", () => open.delete(socket));
    const key = req.headers["sec-websocket-key"];
    if (req.url !== `/${token}` || !key || req.headers.upgrade?.toLowerCase() !== "websocket") return socket.destroy();
    const accept = createHash("sha1").update(key + GUID).digest("base64");
    socket.write(`HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Accept: ${accept}\r\n\r\n`);
    socket.setNoDelay(true);
    let buffer = Buffer.alloc(0);
    let parts = [];
    const client = {
      onMessage: () => {},
      onClose: () => {},
      send: (text) => socket.writable && socket.write(frame(text)),
      close: () => socket.end(frame("", 8)),
    };
    socket.on("data", (chunk) => {
      buffer = Buffer.concat([buffer, chunk]);
      for (;;) {
        if (buffer.length < 2) return;
        const fin = buffer[0] & 0x80;
        const opcode = buffer[0] & 0x0f;
        let length = buffer[1] & 0x7f;
        let at = 2;
        if (length === 126) {
          if (buffer.length < 4) return;
          length = buffer.readUInt16BE(2);
          at = 4;
        } else if (length === 127) {
          if (buffer.length < 10) return;
          length = Number(buffer.readBigUInt64BE(2));
          at = 10;
        }
        const masked = buffer[1] & 0x80;
        const mask = masked ? buffer.subarray(at, at + 4) : undefined;
        if (masked) at += 4;
        if (buffer.length < at + length) return;
        const body = Buffer.from(buffer.subarray(at, at + length));
        buffer = buffer.subarray(at + length);
        if (mask) for (let i = 0; i < body.length; i++) body[i] ^= mask[i % 4];
        if (opcode === 8) return socket.end(frame("", 8));
        if (opcode === 9) socket.write(frame(body.toString("utf8"), 10));
        if (opcode === 1 || opcode === 0) {
          parts.push(body);
          if (fin) {
            const text = Buffer.concat(parts).toString("utf8");
            parts = [];
            client.onMessage(text);
          }
        }
      }
    });
    socket.on("close", () => client.onClose());
    socket.on("error", () => socket.destroy());
    onSocket(client);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  const close = () => {
    for (const socket of open) socket.destroy();
    return new Promise((resolve) => server.close(() => resolve()));
  };
  return { url: `ws://127.0.0.1:${port}/${token}`, close };
}

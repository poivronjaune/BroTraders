"""
IBKR_Simulator.py

A single-file, protocol-level fake of the IBKR TWS/Gateway API socket server.

WHAT THIS IS
    ib_async (like the official ibapi) does NOT talk to TWS over HTTP. It opens
    a raw TCP socket and speaks IB's own length-prefixed, null-delimited message
    protocol: a version handshake, a "StartAPI" message, then a stream of
    request/response messages tagged by numeric message IDs. This script
    implements that protocol directly with asyncio - no ib_async, no FastAPI,
    no HTTP - so that an unmodified ib_async client can connect to it exactly
    as it would connect to real TWS.

WHAT THIS VERSION IMPLEMENTS (and nothing more)
    - The version handshake ("API\\0" + version range -> serverVersion + time)
    - StartAPI acknowledgement (nextValidId + managedAccounts)
    - The automatic startup requests ib_async's IB.connectAsync() fires right
      after a connection is marked ready: reqPositions, reqOpenOrders,
      reqCompletedOrders, reqAccountUpdates, reqAccountUpdatesMulti,
      reqExecutions, reqAutoOpenOrders. Each is answered with an empty/"end"
      response (no positions, no orders, no executions) so that ib.connect()
      returns quickly instead of hanging until its timeout expires.
    - Clean disconnect: when the client closes its socket (ib.disconnect()),
      this server detects it, logs it, and cleans up that connection.

WHAT THIS VERSION DELIBERATELY DOES NOT IMPLEMENT YET
    - Market scanner (reqScannerSubscription)
    - Historical / live bar data (reqHistoricalData)
    - Order placement, order status, fills (placeOrder, execDetails)
    - Market data snapshots (reqMktData)
    Any such request received after connection is logged as "unhandled" and
    ignored - it will not crash the server, but the calling code will hang
    waiting for a response that never comes. Those features are planned for
    later versions of this simulator.

WHY NOT FASTAPI
    FastAPI/Starlette are HTTP (ASGI) frameworks. IBKR's protocol is a raw,
    persistent TCP socket with custom binary framing - there is no HTTP
    request/response involved anywhere in the real protocol. That is why this
    file uses asyncio.start_server() directly instead.

PROTOCOL REFERENCE
    Every detail here (message IDs, field order, skip counts) was taken from
    reading ib_async 2.1.0's own source (client.py / decoder.py), since
    ib_async is open source and is the exact client this simulator needs to
    satisfy. This is not a guess at IBKR's protocol - it is read directly from
    the library that will connect to this server.

LAUNCH INSTRUCTIONS
    1. Requires only the Python standard library - no dependencies to install.
    2. Run it directly:
           py IBKR_Simulator.py
       or on macOS/Linux:
           python3 IBKR_Simulator.py
    3. By default it listens on 127.0.0.1:7497 (the same default port as TWS
       paper trading), so no config changes are needed in BroTraders/brotoolsv2
       to point at it - just make sure real TWS is NOT also running on that
       port at the same time.
    4. To use a different port (e.g. to run side-by-side with real TWS),
       edit the PORT constant below.
    5. Stop with Ctrl+C.
    6. Point brotoolsv2/config.py (or any ib_async script) at IBKR_HOST/IBKR_PORT
       matching this server and connect with any clientId - only clientId 0
       triggers the extra (silently ignored) reqAutoOpenOrders call, both
       clientId 0 and non-zero work fine against this simulator.

KNOWN LIMITATION
    Only one simulated account ("DU1234567") and one simulated connection at a
    time have been tested. Multiple concurrent client connections are
    accepted (asyncio.start_server handles them independently) but have not
    been exercised together.
"""

import asyncio
import logging
import struct
from datetime import datetime

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
HOST = "127.0.0.1"
PORT = 7497                # same default as TWS paper trading port
SERVER_VERSION = 176       # within ib_async 2.1.0's MinClientVersion(157)..MaxClientVersion(178)
ACCOUNT_ID = "DU1234567"   # fake paper-trading account id returned as managedAccounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("IBKR_Simulator")


# ---------------------------------------------------------------------------
# Wire-format helpers
# ---------------------------------------------------------------------------
def encode_frame(*fields) -> bytes:
    """
    Encode fields the same way ib_async's Client.send() does: each field is
    stringified and null-terminated, and the whole payload is prefixed with
    its length as a 4-byte big-endian unsigned int.
    """
    payload = ("\0".join(str(f) for f in fields) + "\0").encode()
    return struct.pack(">I", len(payload)) + payload


async def read_frame(reader: asyncio.StreamReader) -> list[str]:
    """
    Read one length-prefixed, null-delimited message frame and return it as
    a list of string fields (mirrors ib_async's own _onSocketHasData parsing).
    Raises asyncio.IncompleteReadError if the client closes mid-read.
    """
    length_bytes = await reader.readexactly(4)
    length = struct.unpack(">I", length_bytes)[0]
    payload = await reader.readexactly(length)
    text = payload.decode(errors="backslashreplace")
    fields = text.split("\0")
    fields.pop()  # drop the trailing empty element from the final \0
    return fields


# ---------------------------------------------------------------------------
# Per-connection handling
# ---------------------------------------------------------------------------
async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    peer = writer.get_extra_info("peername")
    logger.info(f"Client connected: {peer}")

    try:
        await do_handshake(reader, writer)
        client_id = await do_start_api(reader, writer)
        logger.info(f"Client {peer} (clientId={client_id}) is now READY")

        # Main loop: answer whatever startup / feature requests arrive.
        while True:
            fields = await read_frame(reader)
            await dispatch_request(writer, fields)
            await writer.drain()

    except asyncio.IncompleteReadError:
        logger.info(f"Client disconnected (closed socket): {peer}")
    except ConnectionResetError:
        logger.info(f"Client connection reset: {peer}")
    except Exception as e:
        logger.error(f"Error handling client {peer}: {type(e).__name__}: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info(f"Connection closed: {peer}")


async def do_handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    """
    Client sends: b"API\\0" + 4-byte length + b"v<min>..<max>[ options]"
    Server replies: a single frame with exactly 2 fields: serverVersion, connectionTime.
    That 2-field frame is what ib_async's client recognizes as concluding the handshake.
    """
    prefix = await reader.readexactly(4)
    if prefix != b"API\0":
        raise ValueError(f"Unexpected handshake prefix: {prefix!r} (expected b'API\\0')")

    version_len = struct.unpack(">I", await reader.readexactly(4))[0]
    version_payload = await reader.readexactly(version_len)
    version_str = version_payload.decode(errors="backslashreplace")
    logger.info(f"Received version handshake: {version_str!r}")

    conn_time = datetime.now().strftime("%Y%m%d %H:%M:%S EST")
    writer.write(encode_frame(SERVER_VERSION, conn_time))
    await writer.drain()
    logger.info(f"Sent handshake response: serverVersion={SERVER_VERSION}, connectionTime={conn_time!r}")


async def do_start_api(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> str:
    """
    Client sends StartAPI (msgId=71): fields = [71, "2", clientId, optCapab].
    Server must reply with nextValidId (msgId=9) and managedAccounts (msgId=15) -
    ib_async's client considers the connection "ready" only once both have
    arrived, in either order.
    """
    fields = await read_frame(reader)
    logger.info(f"Received StartAPI: {fields}")

    client_id = fields[2] if len(fields) > 2 else "?"

    writer.write(encode_frame(9, 1, 1))              # nextValidId: next order id = 1
    writer.write(encode_frame(15, 1, ACCOUNT_ID))     # managedAccounts
    await writer.drain()
    logger.info(f"Sent nextValidId=1 and managedAccounts={ACCOUNT_ID!r}")

    return client_id


async def dispatch_request(writer: asyncio.StreamWriter, fields: list[str]) -> None:
    """
    Handle one incoming request frame from an already-connected client.

    Only the requests that ib_async's IB.connectAsync() automatically fires
    right after connecting are answered for real. Everything else (scanner,
    historical data, orders, market data) is logged as unhandled and ignored -
    that is out of scope for this version of the simulator.
    """
    if not fields:
        return

    msg_id = fields[0]

    if msg_id == "61":  # reqPositions -> no positions
        writer.write(encode_frame(62, 1))
        logger.info("  -> reqPositions: replied positionEnd (no positions)")

    elif msg_id == "5":  # reqOpenOrders -> no open orders
        writer.write(encode_frame(53, 1))
        logger.info("  -> reqOpenOrders: replied openOrderEnd (no open orders)")

    elif msg_id == "99":  # reqCompletedOrders -> no completed orders
        writer.write(encode_frame(102))
        logger.info("  -> reqCompletedOrders: replied completedOrdersEnd")

    elif msg_id == "6":  # reqAccountUpdates -> nothing to report
        # fields = [msgId, version, subscribe, acctCode] - account is fields[3]
        account = fields[3] if len(fields) > 3 else ACCOUNT_ID
        writer.write(encode_frame(54, 1, account))
        logger.info(f"  -> reqAccountUpdates: replied accountDownloadEnd for {account!r}")

    elif msg_id == "76":  # reqAccountUpdatesMulti -> nothing to report
        req_id = fields[2] if len(fields) > 2 else "1"
        writer.write(encode_frame(74, 1, req_id))
        logger.info(f"  -> reqAccountUpdatesMulti: replied accountUpdateMultiEnd (reqId={req_id})")

    elif msg_id == "7":  # reqExecutions -> no executions
        req_id = fields[2] if len(fields) > 2 else "1"
        writer.write(encode_frame(55, 1, req_id))
        logger.info(f"  -> reqExecutions: replied execDetailsEnd (reqId={req_id})")

    elif msg_id == "15":  # reqAutoOpenOrders -> fire-and-forget, no response expected
        logger.info("  -> reqAutoOpenOrders received (no response required)")

    else:
        logger.warning(
            f"  -> Unhandled request msgId={msg_id} fields={fields} "
            f"(not implemented in this version of IBKR_Simulator - caller will hang/time out)"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    server = await asyncio.start_server(handle_client, HOST, PORT)
    addr = server.sockets[0].getsockname()
    logger.info(f"IBKR_Simulator listening on {addr[0]}:{addr[1]} (Ctrl+C to stop)")
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("IBKR_Simulator stopped by user (Ctrl+C)")

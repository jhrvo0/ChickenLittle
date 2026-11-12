"""Testa o relay somente no loopback, sem abrir porta na rede local."""
import asyncio
import ipaddress

from ops.iot.lan_relay import relay


def test_relay_transports_bytes_and_rejects_other_ips():
    async def exercise():
        async def echo(reader, writer):
            try:
                while data := await reader.read(4096):
                    writer.write(data)
                    await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0)
        upstream_port = upstream.sockets[0].getsockname()[1]
        slots = asyncio.Semaphore(8)

        async def start_proxy(network):
            return await asyncio.start_server(
                lambda reader, writer: relay(reader, writer, upstream_port, network, slots),
                "127.0.0.1", 0,
            )

        allowed = await start_proxy(ipaddress.ip_network("127.0.0.1/32"))
        rejected = await start_proxy(ipaddress.ip_network("127.0.0.2/32"))
        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", allowed.sockets[0].getsockname()[1])
            payload = b"\x16\x03\x03\x00\x10" + bytes(range(256)) * 500
            writer.write(payload)
            await writer.drain()
            assert await asyncio.wait_for(reader.readexactly(len(payload)), 5) == payload
            writer.close()
            await writer.wait_closed()

            reader, writer = await asyncio.open_connection("127.0.0.1", rejected.sockets[0].getsockname()[1])
            assert await asyncio.wait_for(reader.read(), 5) == b""
            writer.close()
            await writer.wait_closed()
        finally:
            for server in (allowed, rejected, upstream):
                server.close()
                await server.wait_closed()

    asyncio.run(exercise())

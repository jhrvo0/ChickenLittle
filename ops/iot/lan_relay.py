"""Encaminha TCP da LAN privada ao Mosquitto no loopback do Windows/WSL.

O TLS passa intacto até o broker. Este processo não lê credenciais nem termina TLS.
É necessário informar explicitamente o endereço local e a rede de clientes permitida.
"""
from __future__ import annotations

import argparse
import asyncio
import ipaddress


async def relay(reader, writer, upstream_port, allowed_network, slots):
    peer = writer.get_extra_info("peername")
    if not peer or ipaddress.ip_address(peer[0]) not in allowed_network or slots.locked():
        writer.close()
        await writer.wait_closed()
        return

    async with slots:
        upstream_writer = None
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", upstream_port), timeout=5
            )

            async def pipe(source, destination):
                while data := await asyncio.wait_for(source.read(65536), timeout=120):
                    destination.write(data)
                    await destination.drain()
                if destination.can_write_eof():
                    destination.write_eof()

            await asyncio.gather(pipe(reader, upstream_writer), pipe(upstream_reader, writer))
        except (OSError, asyncio.TimeoutError):
            pass
        finally:
            writer.close()
            if upstream_writer:
                upstream_writer.close()
            await asyncio.gather(
                writer.wait_closed(),
                *( [upstream_writer.wait_closed()] if upstream_writer else [] ),
                return_exceptions=True,
            )


async def serve(address, listen_port, upstream_port, allowed_network):
    slots = asyncio.Semaphore(8)
    server = await asyncio.start_server(
        lambda reader, writer: relay(reader, writer, upstream_port, allowed_network, slots),
        str(address), listen_port,
    )
    async with server:
        print(f"Relay TCP em {address}:{listen_port}; clientes {allowed_network}; "
              f"broker 127.0.0.1:{upstream_port}", flush=True)
        await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--listen-address", required=True, type=ipaddress.IPv4Address)
    parser.add_argument("--allow-network", required=True, type=ipaddress.IPv4Network,
                        help="Rede privada IPv4 permitida, por exemplo 192.168.15.0/24")
    parser.add_argument("--listen-port", type=int, default=8883)
    parser.add_argument("--upstream-port", type=int, default=8883)
    args = parser.parse_args()
    if args.listen_address.is_unspecified or not args.listen_address.is_private:
        parser.error("O endereço de escuta deve ser um IPv4 privado específico.")
    if not args.allow_network.is_private:
        parser.error("A rede permitida deve ser privada.")
    if not all(1 <= port <= 65535 for port in (args.listen_port, args.upstream_port)):
        parser.error("Portas devem estar entre 1 e 65535.")
    try:
        asyncio.run(serve(args.listen_address, args.listen_port, args.upstream_port, args.allow_network))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

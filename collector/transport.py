"""A one-origin CONNECT proxy that dials only an already vetted IP address."""

import asyncio


MAX_TUNNEL_BYTES = 8 * 1024 * 1024


class PinnedProxy:
    def __init__(self, authority, addresses, port):
        self.authority = authority.encode('ascii')
        self.addresses = addresses
        self.port = port
        self.connections = set()
        self.server = None

    async def __aenter__(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0, limit=8192)
        return f"http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}"

    async def __aexit__(self, *_):
        self.server.close()
        await self.server.wait_closed()
        for task in self.connections:
            task.cancel()
        await asyncio.gather(*self.connections, return_exceptions=True)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.connections.add(task)
        try:
            await asyncio.wait_for(self.tunnel(reader, writer), 8)
        except (OSError, asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            pass
        finally:
            writer.close()
            self.connections.discard(task)

    async def tunnel(self, reader, writer):
        head = await asyncio.wait_for(reader.readuntil(b'\r\n\r\n'), 2)
        command = head.split(b'\r\n', 1)[0].split(b' ')
        if len(command) != 3 or command[:2] != [b'CONNECT', self.authority]:
            writer.write(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n')
            await writer.drain()
            return
        remote_reader, remote_writer = await self.connect()
        try:
            writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            await writer.drain()
            upstream = asyncio.create_task(self.relay(reader, remote_writer))
            downstream = asyncio.create_task(self.relay(remote_reader, writer))
            try:
                await asyncio.wait((upstream, downstream), return_when=asyncio.FIRST_COMPLETED)
            finally:
                upstream.cancel()
                downstream.cancel()
                await asyncio.gather(upstream, downstream, return_exceptions=True)
        finally:
            remote_writer.close()

    async def connect(self):
        for address in self.addresses:
            try:
                return await asyncio.wait_for(asyncio.open_connection(address, self.port), 1)
            except (OSError, asyncio.TimeoutError):
                continue
        raise OSError('approved destination unavailable')

    @staticmethod
    async def relay(reader, writer):
        remaining = MAX_TUNNEL_BYTES
        while remaining:
            chunk = await reader.read(min(remaining, 65536))
            if not chunk:
                return
            writer.write(chunk)
            await writer.drain()
            remaining -= len(chunk)

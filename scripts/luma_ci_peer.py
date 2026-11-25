"""Loopback-only Telnet peer for the delivered LUMA beta acceptance test."""
import argparse
import asyncio
import json
from pathlib import Path

from ma2panel.mock import MockMA2


async def serve(port, trace):
    mock = MockMA2("luma-ci", None)
    server = await asyncio.start_server(mock._handle, "127.0.0.1", port)
    # Store only synthetic QA traffic. Replace atomically for Chromium's reader.
    temporary = trace.with_suffix(".tmp")
    received = None
    async with server:
        while True:
            if received != len(mock.received):
                received = len(mock.received)
                temporary.write_text(json.dumps(mock.received), encoding="utf-8")
                # Windows can refuse a replace while Chromium reads the old file.
                for attempt in range(10):
                    try:
                        temporary.replace(trace)
                        break
                    except PermissionError:
                        if attempt == 9:
                            raise
                        await asyncio.sleep(.02)
            await asyncio.sleep(.03)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", type=int)
    parser.add_argument("trace", type=Path)
    args = parser.parse_args()
    asyncio.run(serve(args.port, args.trace))


if __name__ == "__main__":
    main()

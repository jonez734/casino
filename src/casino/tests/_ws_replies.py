"""Shared helpers for tests that read replies from a raw WebSocket test client.

A table create sends an unsolicited ``owns_tables`` push to the creator's socket,
after its ``table_created`` reply. A test that reads one reply at a time must skip
that push, the same way the casino client handles it as a flag update.
"""


async def receive_reply(client):
    """The next reply, skipping any owns_tables push."""
    while True:
        msg = await client.receive()
        if msg.get("type") != "owns_tables":
            return msg


async def receive_until(client, predicate, timeout: float = 10.0):
    """The first message that satisfies ``predicate``, within ``timeout`` seconds.

    The server sends a table broadcast and the player's own reply in no fixed order, and a
    fixed batch can close before the reply arrives. This waits for the message the test
    needs, up to a deadline, and skips everything else, including ``owns_tables`` pushes.
    Raises ``AssertionError`` with the messages seen if none matches.
    """
    import asyncio

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    seen = []
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise AssertionError(f"no matching message within {timeout}s; saw: {seen}")
        try:
            msg = await asyncio.wait_for(client._message_queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            raise AssertionError(f"no matching message within {timeout}s; saw: {seen}")
        if msg.get("type") == "owns_tables":
            continue
        seen.append(msg.get("type"))
        if predicate(msg):
            return msg

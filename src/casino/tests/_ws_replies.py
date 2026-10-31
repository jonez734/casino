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

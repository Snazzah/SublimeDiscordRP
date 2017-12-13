# This file is currently unused

import time

DISCORD_EPOCH = 1420070400000


def generate():
    """Generate some snowflake from the current time."""
    return from_time(time.time())


def from_time(unix_seconds, high=False):
    """Returns a numeric snowflake pretending to be created at the given date."""
    discord_millis = int(unix_seconds * 1000 - DISCORD_EPOCH)
    return (discord_millis << 22) + (2**22 - 1 if high else 0)


def to_time(snowflake):
    """Returns the snowflake creation date in seconds since the epoch (not discord epoch)."""
    return ((int(snowflake) >> 22) + DISCORD_EPOCH) / 1000

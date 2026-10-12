"""Per-user personal assistant Agent: one owner phone number per instance.

Each assistant is both a Partner (another assistant hands it a message and it
delivers to its owner's phone) and a Leader (its owner asks it to send something,
so it discovers the recipient's assistant and calls it).
"""

__all__ = ["config", "agent"]

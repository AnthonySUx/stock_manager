"""Complete array elements from JSON text that arrives in pieces (#65).

Explore streams `{"ideas": [{...}, {...}]}` from the AI. `ArrayItemStream`
hands back each element of the `ideas` array as soon as it is complete, so
it can be validated and sent on its own. It never returns a partial element.

Recognized shapes: an object whose top-level `key` holds an array (the first
such key), or a top-level array. Text before the JSON (a ``` fence) and after
it is ignored. Anything else leaves `found` False, and the caller validates
the whole parsed reply instead.
"""
import json


class ArrayItemStream:
    def __init__(self, key: str = "ideas"):
        self.key = key
        self._text = ""
        self._pos = 0
        self._stack: list[str] = []
        self._in_string = False
        self._escape = False
        self._key_start = None  # start of a string in the top-level object
        self._last_key = None
        self._array_depth = None  # stack depth inside the target array
        self._item_start = None
        self._done = False  # the top-level value closed
        self.found = False  # the target array was opened
        self.closed = False  # ... and closed
        self.count = 0  # elements returned

    def _take(self, end: int):
        raw = self._text[self._item_start:end].strip()
        self._item_start = None
        self.count += 1
        try:
            return json.loads(raw)
        except ValueError:
            return raw  # malformed element: the caller rejects a non-object

    def _in_target(self) -> bool:
        return (self._array_depth is not None and not self.closed
                and len(self._stack) == self._array_depth)

    def feed(self, chunk: str) -> list:
        """Add text; return the elements completed by it, in order."""
        self._text += chunk
        items = []
        text = self._text
        while self._pos < len(text):
            i = self._pos
            ch = text[i]
            self._pos += 1
            if self._in_string:
                if self._escape:
                    self._escape = False
                elif ch == "\\":
                    self._escape = True
                elif ch == '"':
                    self._in_string = False
                    if self._key_start is not None:
                        try:
                            self._last_key = json.loads(text[self._key_start:i + 1])
                        except ValueError:
                            self._last_key = None
                        self._key_start = None
                continue
            if self._done or (not self._stack and ch not in "{["):
                continue  # before the JSON, or after it ended
            if self._in_target() and self._item_start is None and ch not in " \t\r\n,]":
                self._item_start = i
            if ch == '"':
                self._in_string = True
                if self._stack == ["{"]:
                    # A key, or a value that a key will replace: a "[" at
                    # this level always comes right after its own key.
                    self._key_start = i
            elif ch in "{[":
                target = ch == "[" and self._array_depth is None and (
                    not self._stack or (self._stack == ["{"] and self._last_key == self.key)
                )
                self._stack.append(ch)
                if target:
                    self._array_depth = len(self._stack)
                    self.found = True
            elif ch in "}]":
                if self._in_target():  # the target array itself closes
                    if self._item_start is not None:
                        items.append(self._take(i))  # a last scalar element
                    self.closed = True
                if self._stack:
                    self._stack.pop()
                if self._in_target() and self._item_start is not None:
                    items.append(self._take(i + 1))  # an object / array element closed
                if not self._stack:
                    self._done = True
            elif ch == ",":
                if self._in_target() and self._item_start is not None:
                    items.append(self._take(i))  # a scalar element
        return items

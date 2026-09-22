"""Pins the output-encoder defects the move to the shared craig-ai-tooling/axi-py
`toon()` fixed (lm-91). No network, no credentials.

Before: a cell containing `"` was quoted without doubling the inner quote, so the
row did not parse, and an empty table printed `  (none)` on its own line instead
of on the header line. Rendered through `cli.show_items`, the real verb path, not
a hand-rolled call into the encoder.
"""
import io
import unittest
from contextlib import redirect_stdout

from monday_axi import cli


def _capture(fn, *args, **kwargs):
    buf = io.StringIO()
    with redirect_stdout(buf):
        fn(*args, **kwargs)
    return buf.getvalue()


class QuoteAndCommaRoundTripTest(unittest.TestCase):
    def test_a_name_with_both_comma_and_quote_is_one_correctly_quoted_cell(self):
        item = {"id": "1", "date": "2026-09-22", "status": "Done", "activity": "PoV",
                "name": 'Acme, Inc. - "kickoff"'}
        out = _capture(cli.show_items, [item], "items")
        lines = out.splitlines()
        self.assertEqual(lines[0], "items[1]{id,date,status,activity,name}:")
        # one field, not split by the embedded comma; the inner quote is doubled
        # per the row-parses-back-out contract, not silently dropped.
        self.assertEqual(lines[1], '  1,2026-09-22,Done,PoV,"Acme, Inc. - ""kickoff"""')


class EmptyTableTest(unittest.TestCase):
    def test_empty_result_prints_none_on_the_header_line(self):
        out = _capture(cli.show_items, [], "items")
        self.assertEqual(out, "items[0]{id,date,status,activity,name}: (none)\n")


if __name__ == "__main__":
    unittest.main()

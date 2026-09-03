import tempfile
import unittest
from pathlib import Path

from sync_docs import digest


class DigestTests(unittest.TestCase):
    def test_digest_is_independent_of_line_endings(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lf = root / "lf.md"
            crlf = root / "crlf.md"
            cr = root / "cr.md"
            lf.write_bytes(b"first\nsecond\n")
            crlf.write_bytes(b"first\r\nsecond\r\n")
            cr.write_bytes(b"first\rsecond\r")
            self.assertEqual(digest(lf), digest(crlf))
            self.assertEqual(digest(lf), digest(cr))


if __name__ == "__main__":
    unittest.main()

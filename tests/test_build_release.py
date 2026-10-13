import unittest

from tools.build_release import sanitize_embedded_windows_profile_paths


class DenoPathSanitizationTests(unittest.TestCase):
    def test_ascii_and_utf16_profile_paths_are_rewritten_without_changing_size(self):
        prefix = b"C:\\Users\\ciworker\\.cargo\\registry\\source.rs"
        wide_prefix = "C:\\Users\\ciworker\\.cargo\\registry\\source.rs".encode("utf-16le")
        original = b"before " + prefix + b" middle " + wide_prefix + b" after"

        sanitized, ascii_count, wide_count = sanitize_embedded_windows_profile_paths(original)

        self.assertEqual((ascii_count, wide_count), (1, 1))
        self.assertEqual(len(sanitized), len(original))
        self.assertNotIn(b"C:\\Users\\ciworker", sanitized)
        self.assertNotIn("C:\\Users\\ciworker".encode("utf-16le"), sanitized)
        self.assertIn(b"C:\\Build\\agent___", sanitized)


if __name__ == "__main__":
    unittest.main()

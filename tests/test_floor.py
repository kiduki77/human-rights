import unittest

import helpers
from runtime.config import parse_simple_yaml


class QuotedKeysTest(unittest.TestCase):
    def test_quoted_glob_keys_parse_without_pyyaml(self):
        text = '# owner rules\n"**/secrets/*": L3\n\'migrations/**\': L2   # keep\nplain/**: L1\n'
        self.assertEqual(parse_simple_yaml(text), {"**/secrets/*": "L3", "migrations/**": "L2", "plain/**": "L1"})


if __name__ == "__main__":
    unittest.main()

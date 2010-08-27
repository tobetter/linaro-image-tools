from StringIO import StringIO

from testtools import TestCase

from hwpack.config import Config, HwpackConfigError


class ConfigTests(TestCase):

    def test_create(self):
        config = Config(StringIO())

    def test_validate_no_hwpack_section(self):
        config = Config(StringIO())
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("No [hwpack] section", str(e))

    def test_validate_no_name(self):
        config = Config(StringIO("[hwpack]\n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("No name in the [hwpack] section", str(e))

    def test_validate_invalid_name(self):
        config = Config(StringIO("[hwpack]\nname = ~~\n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("Invalid name: ~~", str(e))

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

    def test_validate_empty_name(self):
        config = Config(StringIO("[hwpack]\nname =  \n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("Empty value for name", str(e))

    def test_validate_invalid_name(self):
        config = Config(StringIO("[hwpack]\nname = ~~\n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("Invalid name: ~~", str(e))

    def test_validate_invalid_include_debs(self):
        config = Config(StringIO(
                "[hwpack]\nname = ahwpack\n"
                "include-debs = if you don't mind\n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "Invalid value for include-debs: if you don't mind", str(e))

    def test_validate_invalid_supported(self):
        config = Config(StringIO(
                "[hwpack]\nname = ahwpack\nsupport = if you pay us\n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "Invalid value for support: if you pay us", str(e))

    def test_validate_no_other_sections(self):
        config = Config(StringIO("[hwpack]\nname = ahwpack\n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "No sections other than [hwpack]", str(e))

    def test_validate_other_section_no_sources_entry(self):
        config = Config(StringIO(
                "[hwpack]\nname = ahwpack\n\n[ubuntu]\n"))
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "No sources-entry in the [ubuntu] section", str(e))

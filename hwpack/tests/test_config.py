from StringIO import StringIO

from testtools import TestCase

from hwpack.config import Config, HwpackConfigError


class ConfigTests(TestCase):

    def test_create(self):
        config = Config(StringIO())

    def get_config(self, contents):
        return Config(StringIO(contents))

    def test_validate_no_hwpack_section(self):
        config = self.get_config("")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("No [hwpack] section", str(e))

    def test_validate_no_name(self):
        config = self.get_config("[hwpack]\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("No name in the [hwpack] section", str(e))

    def test_validate_empty_name(self):
        config = self.get_config("[hwpack]\nname =  \n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("Empty value for name", str(e))

    def test_validate_invalid_name(self):
        config = self.get_config("[hwpack]\nname = ~~\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual("Invalid name: ~~", str(e))

    def test_validate_invalid_include_debs(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n"
                "include-debs = if you don't mind\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "Invalid value for include-debs: if you don't mind", str(e))

    def test_validate_invalid_supported(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\nsupport = if you pay us\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "Invalid value for support: if you pay us", str(e))

    def test_validate_no_other_sections(self):
        config = self.get_config("[hwpack]\nname = ahwpack\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "No sections other than [hwpack]", str(e))

    def test_validate_other_section_no_sources_entry(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n[ubuntu]\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "No sources-entry in the [ubuntu] section", str(e))

    def test_validate_other_section_empty_sources_entry(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry =  \n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "The sources-entry in the [ubuntu] section is missing the URI",
            str(e))

    def test_validate_other_section_only_uri_in_sources_entry(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry =  foo\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "The sources-entry in the [ubuntu] section is missing the "
            "distribution", str(e))

    def test_validate_other_section_sources_entry_starting_with_deb(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry =  deb http://example.org/ "
                "foo main\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "The sources-entry in the [ubuntu] section shouldn't start "
            "with 'deb'", str(e))

    def test_validate_other_section_sources_entry_starting_with_deb_src(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry =  deb-src http://example.org/ "
                "foo main\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "The sources-entry in the [ubuntu] section shouldn't start "
            "with 'deb'", str(e))

    def test_validate_other_section_no_packages(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry = foo bar\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "No packages in the [ubuntu] section", str(e))

    def test_validate_other_section_empty_packages(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry = foo bar\npackages = \n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "The packages in the [ubuntu] section is empty",
            str(e))

    def test_validate_other_section_invalid_package_name(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry = foo bar\n"
                "packages = foo  ~~ bar\n")
        e = self.assertRaises(HwpackConfigError, config.validate)
        self.assertEqual(
            "Invalid value in packages in the [ubuntu] section: ~~",
            str(e))

    def test_validate_valid_config(self):
        config = self.get_config(
                "[hwpack]\nname = ahwpack\n\n"
                "[ubuntu]\nsources-entry = foo bar\n"
                "packages = foo  bar\n")
        self.assertEqual(None, config.validate())

    def test_name(self):
        config = self.get_config("[hwpack]\nname = ahwpack\n")
        self.assertEqual("ahwpack", config.name)

    def test_include_debs(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\ninclude-debs = false\n")
        self.assertEqual(False, config.include_debs)

    def test_include_debs_defaults_true(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\n")
        self.assertEqual(True, config.include_debs)

    def test_include_debs_defaults_true_on_empty(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\ninclude-debs = \n")
        self.assertEqual(True, config.include_debs)

    def test_origin(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\norigin = linaro\n")
        self.assertEqual("linaro", config.origin)

    def test_origin_default_None(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\n")
        self.assertEqual(None, config.origin)

    def test_origin_None_on_empty(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\norigin =  \n")
        self.assertEqual(None, config.origin)

    def test_maintainer(self):
        maintainer = "Linaro Developers <linaro-dev@lists.linaro.org>"
        config = self.get_config(
            "[hwpack]\nname = ahwpack\nmaintainer = %s\n" % maintainer)
        self.assertEqual(maintainer, config.maintainer)

    def test_maintainer_default_None(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\n")
        self.assertEqual(None, config.maintainer)

    def test_maintainer_None_on_empty(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\nmaintainer =  \n")
        self.assertEqual(None, config.maintainer)

    def test_support_supported(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\nsupport = supported\n")
        self.assertEqual("supported", config.support)

    def test_support_unsupported(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\nsupport = unsupported\n")
        self.assertEqual("unsupported", config.support)

    def test_support_default_None(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\n")
        self.assertEqual(None, config.support)

    def test_support_None_on_empty(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\nsupport =  \n")
        self.assertEqual(None, config.support)

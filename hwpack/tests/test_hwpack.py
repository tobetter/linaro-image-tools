from testtools import TestCase

from hwpack.hwpack import HardwarePack


class HardwarePackTests(TestCase):

    def test_format_is_1_0(self):
        hwpack = HardwarePack("ahwpack", "3")
        self.assertEqual("1.0", hwpack.FORMAT)

    def test_name(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual("ahwpack", hwpack.name)

    def test_version(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual("4", hwpack.version)

    def test_default_origin_is_None(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual(None, hwpack.origin)

    def test_origin(self):
        hwpack = HardwarePack("ahwpack", "4", origin="linaro")
        self.assertEqual("linaro", hwpack.origin)

    def test_default_maintainer_is_None(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual(None, hwpack.maintainer)

    def test_maintainer(self):
        hwpack = HardwarePack("ahwpack", "4", maintainer="Some maintainer")
        self.assertEqual("Some maintainer", hwpack.maintainer)

    def test_default_support_is_None(self):
        hwpack = HardwarePack("ahwpack", "4")
        self.assertEqual(None, hwpack.support)

    def test_support(self):
        hwpack = HardwarePack("ahwpack", "4", support="supported")
        self.assertEqual("supported", hwpack.support)

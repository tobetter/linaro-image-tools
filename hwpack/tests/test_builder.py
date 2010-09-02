import os

from hwpack.builder import HardwarePackBuilder
from hwpack.config import HwpackConfigError
from hwpack.hardwarepack import Metadata
from hwpack.testing import (
    AptSourceFixture,
    ChdirToTempdirFixture,
    ConfigFileFixture,
    DummyFetchedPackage,
    IsHardwarePack,
    TestCaseWithFixtures,
    )


class HardwarePackBuilderTests(TestCaseWithFixtures):

    def setUp(self):
        super(HardwarePackBuilderTests, self).setUp()
        self.useFixture(ChdirToTempdirFixture())

    def test_validates_configuration(self):
        config = self.useFixture(ConfigFileFixture(''))
        self.assertRaises(
            HwpackConfigError, HardwarePackBuilder, config.filename, "1.0")

    def test_builds_one_pack_per_arch(self):
        available_package = DummyFetchedPackage("foo", "1.1")
        source = self.useFixture(AptSourceFixture([available_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=ahwpack\npackages=foo\narchitectures=i386 armel\n'
            '\n[ubuntu]\nsources-entry=%s\n' % source.sources_entry))
        builder = HardwarePackBuilder(config.filename, "1.0")
        builder.build()
        self.assertTrue(os.path.isfile("hwpack_ahwpack_1.0_i386.tar.gz"))
        self.assertTrue(os.path.isfile("hwpack_ahwpack_1.0_armel.tar.gz"))

    def test_builds_correct_contents(self):
        hwpack_name = "ahwpack"
        hwpack_version = "1.0"
        architecture = "armel"
        package_name = "foo"
        source_id = "ubuntu"
        available_package = DummyFetchedPackage(
            package_name, "1.1", architecture=architecture)
        source = self.useFixture(AptSourceFixture([available_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=%s\npackages=%s\narchitectures=%s\n'
            '\n[%s]\nsources-entry=%s\n'
            % (hwpack_name, package_name, architecture,
                source_id, source.sources_entry)))
        builder = HardwarePackBuilder(config.filename, hwpack_version)
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (hwpack_name, hwpack_version,
                architecture),
            IsHardwarePack(
                metadata, [available_package],
                {source_id: source.sources_entry}))

import os
import tarfile

from testtools import TestCase

from hwpack.builder import ConfigFileMissing, HardwarePackBuilder
from hwpack.config import HwpackConfigError
from hwpack.hardwarepack import Metadata
from hwpack.packages import (
    FetchedPackage,
    PackageMaker,
    )
from hwpack.tarfile_matchers import TarfileHasFile
from hwpack.testing import (
    AptSourceFixture,
    ChdirToTempdirFixture,
    ConfigFileFixture,
    ContextManagerFixture,
    DummyFetchedPackage,
    IsHardwarePack,
    Not,
    TestCaseWithFixtures,
    )


class ConfigFileMissingTests(TestCase):

    def test_str(self):
        exc = ConfigFileMissing("path")
        self.assertEqual("No such config file: 'path'", str(exc))


class HardwarePackBuilderTests(TestCaseWithFixtures):

    def setUp(self):
        super(HardwarePackBuilderTests, self).setUp()
        self.useFixture(ChdirToTempdirFixture())

    def test_raises_on_missing_configuration(self):
        e = self.assertRaises(
            ConfigFileMissing, HardwarePackBuilder, "nonexistant", "1.0", [])
        self.assertEqual("nonexistant", e.filename)

    def test_validates_configuration(self):
        config = self.useFixture(ConfigFileFixture(''))
        self.assertRaises(
            HwpackConfigError, HardwarePackBuilder, config.filename, "1.0",
            [])

    def test_builds_one_pack_per_arch(self):
        available_package = DummyFetchedPackage("foo", "1.1")
        source = self.useFixture(AptSourceFixture([available_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=ahwpack\npackages=foo\narchitectures=i386 armel\n'
            '\n[ubuntu]\nsources-entry=%s\n' % source.sources_entry))
        builder = HardwarePackBuilder(config.filename, "1.0", [])
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
        builder = HardwarePackBuilder(config.filename, hwpack_version, [])
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (hwpack_name, hwpack_version,
                architecture),
            IsHardwarePack(
                metadata, [available_package],
                {source_id: source.sources_entry},
                package_spec=package_name))

    def test_builds_correct_contents_multiple_packages(self):
        hwpack_name = "ahwpack"
        hwpack_version = "1.0"
        architecture = "armel"
        package_name1 = "foo"
        package_name2 = "goo"
        source_id = "ubuntu"
        available_package1 = DummyFetchedPackage(
            package_name1, "1.1", architecture=architecture)
        available_package2 = DummyFetchedPackage(
            package_name2, "1.2", architecture=architecture)
        source = self.useFixture(
            AptSourceFixture([available_package1, available_package2]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=%s\npackages=%s %s\narchitectures=%s\n'
            '\n[%s]\nsources-entry=%s\n'
            % (hwpack_name, package_name1, package_name2, architecture,
                source_id, source.sources_entry)))
        builder = HardwarePackBuilder(config.filename, hwpack_version, [])
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        hwpack_filename = "hwpack_%s_%s_%s.tar.gz" % (
            hwpack_name, hwpack_version, architecture)
        self.assertThat(
            hwpack_filename,
            IsHardwarePack(
                metadata, [available_package1, available_package2],
                {source_id: source.sources_entry},
                package_spec='%s, %s' % (package_name1, package_name2)))
        self.assertThat(
            hwpack_filename,
            IsHardwarePack(
                metadata, [available_package2, available_package1],
                {source_id: source.sources_entry},
                package_spec='%s, %s' % (package_name1, package_name2)))

    def test_obeys_include_debs(self):
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
            'include-debs=no\n\n[%s]\nsources-entry=%s\n'
            % (hwpack_name, package_name, architecture,
                source_id, source.sources_entry)))
        builder = HardwarePackBuilder(config.filename, hwpack_version, [])
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (hwpack_name, hwpack_version,
                architecture),
            IsHardwarePack(
                metadata, [available_package],
                {source_id: source.sources_entry},
                packages_without_content=[available_package],
                package_spec=package_name))

    def test_obeys_assume_installed(self):
        hwpack_name = "ahwpack"
        hwpack_version = "1.0"
        architecture = "armel"
        package_name = "foo"
        assume_installed = "bar"
        source_id = "ubuntu"
        available_package = DummyFetchedPackage(
            package_name, "1.1", architecture=architecture,
            depends=assume_installed)
        dependency_package = DummyFetchedPackage(
            assume_installed, "1.1", architecture=architecture)
        source = self.useFixture(
            AptSourceFixture([available_package, dependency_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=%s\npackages=%s\narchitectures=%s\n'
            'assume-installed=%s\n\n[%s]\nsources-entry=%s\n'
            % (hwpack_name, package_name, architecture, assume_installed,
                source_id, source.sources_entry)))
        builder = HardwarePackBuilder(config.filename, hwpack_version, [])
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        filename = "hwpack_%s_%s_%s.tar.gz" % (hwpack_name, hwpack_version,
                architecture)
        self.assertThat(
            filename,
            IsHardwarePack(
                metadata, [available_package],
                {source_id: source.sources_entry},
                package_spec=package_name))
        tf = tarfile.open(filename, mode="r:gz")
        try:
            self.assertThat(
                tf,
                Not(TarfileHasFile("pkgs/%s" % dependency_package.filename)))
        finally:
            tf.close()

    def test_includes_local_debs(self):
        hwpack_name = "ahwpack"
        hwpack_version = "1.0"
        architecture = "armel"
        package_name = "foo"
        source_id = "ubuntu"
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        local_path = maker.make_package(
            package_name, "1.2", {}, architecture=architecture)
        available_package = FetchedPackage.from_deb(local_path)
        source = self.useFixture(AptSourceFixture([]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=%s\npackages=%s\narchitectures=%s\n'
            '\n[%s]\nsources-entry=%s\n'
            % (hwpack_name, package_name, architecture,
                source_id, source.sources_entry)))
        builder = HardwarePackBuilder(
            config.filename, hwpack_version, [local_path])
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (hwpack_name, hwpack_version,
                architecture),
            IsHardwarePack(
                metadata, [available_package],
                {source_id: source.sources_entry},
                package_spec=package_name))

    def test_prefers_local_debs(self):
        hwpack_name = "ahwpack"
        hwpack_version = "1.0"
        architecture = "armel"
        package_name = "foo"
        source_id = "ubuntu"
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        # The point here is that remote_package has a later version than
        # local_package, but local_package is still preferred.
        remote_package = DummyFetchedPackage(
            package_name, "1.1", architecture=architecture)
        local_path = maker.make_package(
            package_name, "1.0", {}, architecture=architecture)
        local_package = FetchedPackage.from_deb(local_path)
        source = self.useFixture(AptSourceFixture([remote_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=%s\npackages=%s\narchitectures=%s\n'
            '\n[%s]\nsources-entry=%s\n'
            % (hwpack_name, package_name, architecture,
                source_id, source.sources_entry)))
        builder = HardwarePackBuilder(
            config.filename, hwpack_version, [local_path])
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (hwpack_name, hwpack_version,
                architecture),
            IsHardwarePack(
                metadata, [local_package],
                {source_id: source.sources_entry},
                package_spec=package_name))

    def test_includes_local_debs_even_if_not_in_config(self):
        hwpack_name = "ahwpack"
        hwpack_version = "1.0"
        architecture = "armel"
        package_name = "foo"
        local_name = "bar"
        source_id = "ubuntu"
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        remote_package = DummyFetchedPackage(
            package_name, "1.1", architecture=architecture)
        local_path = maker.make_package(
            local_name, "1.0", {}, architecture=architecture)
        local_package = FetchedPackage.from_deb(local_path)
        source = self.useFixture(AptSourceFixture([remote_package]))
        config = self.useFixture(ConfigFileFixture(
            '[hwpack]\nname=%s\npackages=%s\narchitectures=%s\n'
            '\n[%s]\nsources-entry=%s\n'
            % (hwpack_name, package_name, architecture,
               source_id, source.sources_entry)))
        builder = HardwarePackBuilder(
            config.filename, hwpack_version, [local_path])
        builder.build()
        metadata = Metadata(hwpack_name, hwpack_version, architecture)
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (hwpack_name, hwpack_version,
                architecture),
            IsHardwarePack(
                metadata, [remote_package, local_package],
                {source_id: source.sources_entry},
                package_spec=package_name))

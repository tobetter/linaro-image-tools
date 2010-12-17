import os
import tarfile

from testtools import TestCase
from testtools.matchers import Equals

from hwpack.builder import (
    ConfigFileMissing,
    HardwarePackBuilder,
    logger as builder_logger,
    )
from hwpack.config import HwpackConfigError
from hwpack.hardwarepack import Metadata
from hwpack.packages import (
    FetchedPackage,
    PackageMaker,
    )
from hwpack.tarfile_matchers import TarfileHasFile
from hwpack.testing import (
    AppendingHandler,
    AptSourceFixture,
    ChdirToTempdirFixture,
    ConfigFileFixture,
    ContextManagerFixture,
    DummyFetchedPackage,
    EachOf,
    IsHardwarePack,
    MatchesStructure,
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

    def makeMetaDataAndConfigFixture(
            self, packages, sources, hwpack_name="ahwpack",
            hwpack_version="1.0", architecture="armel", extra_config={}):
        config_text = (
            '[hwpack]\n'
            'name=%s\n'
            'packages=%s\n'
            'architectures=%s\n'
            % (hwpack_name, ' '.join(packages), architecture))
        for key, value in extra_config.iteritems():
            config_text += '%s=%s\n' % (key, value)
        config_text += '\n'
        for source_id, source in sources.iteritems():
            config_text += '\n'
            config_text += '[%s]\n' % source_id
            config_text += 'sources-entry=%s\n' % source
        config = self.useFixture(ConfigFileFixture(config_text))
        return Metadata(hwpack_name, hwpack_version, architecture), config

    def sourcesDictForPackages(self, packages):
        source = self.useFixture(AptSourceFixture(packages))
        return {'ubuntu': source.sources_entry}

    def test_builds_correct_contents(self):
        package_name = "foo"
        available_package = DummyFetchedPackage(package_name, "1.1")
        sources_dict = self.sourcesDictForPackages([available_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict)
        builder = HardwarePackBuilder(config.filename, metadata.version, [])
        builder.build()
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (
                metadata.name, metadata.version, metadata.architecture),
            IsHardwarePack(
                metadata, [available_package],
                sources_dict, package_spec=package_name))

    def test_builds_correct_contents_multiple_packages(self):
        package_name1 = "foo"
        package_name2 = "goo"
        available_package1 = DummyFetchedPackage(package_name1, "1.1")
        available_package2 = DummyFetchedPackage(package_name2, "1.2")
        sources_dict = self.sourcesDictForPackages(
            [available_package1, available_package2])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name1, package_name2], sources_dict)
        builder = HardwarePackBuilder(config.filename, metadata.version, [])
        builder.build()
        hwpack_filename = "hwpack_%s_%s_%s.tar.gz" % (
                metadata.name, metadata.version, metadata.architecture)
        self.assertThat(
            hwpack_filename,
            IsHardwarePack(
                metadata, [available_package1, available_package2],
                sources_dict,
                package_spec='%s, %s' % (package_name1, package_name2)))
        self.assertThat(
            hwpack_filename,
            IsHardwarePack(
                metadata, [available_package2, available_package1],
                sources_dict,
                package_spec='%s, %s' % (package_name1, package_name2)))

    def test_obeys_include_debs(self):
        package_name = "foo"
        available_package = DummyFetchedPackage(package_name, "1.1")
        sources_dict = self.sourcesDictForPackages([available_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict, extra_config={'include-debs': 'no'})
        builder = HardwarePackBuilder(config.filename, metadata.version, [])
        builder.build()
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (
                metadata.name, metadata.version, metadata.architecture),
            IsHardwarePack(
                metadata, [available_package],
                sources_dict, packages_without_content=[available_package],
                package_spec=package_name))

    def test_obeys_assume_installed(self):
        package_name = "foo"
        assume_installed = "bar"
        available_package = DummyFetchedPackage(
            package_name, "1.1", depends=assume_installed)
        dependency_package = DummyFetchedPackage(assume_installed, "1.1")
        sources_dict = self.sourcesDictForPackages(
            [available_package, dependency_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict,
            extra_config={'assume-installed': assume_installed})
        builder = HardwarePackBuilder(config.filename, metadata.version, [])
        builder.build()
        filename = "hwpack_%s_%s_%s.tar.gz" % (
            metadata.name, metadata.version, metadata.architecture)
        self.assertThat(
            filename,
            IsHardwarePack(
                metadata, [available_package],
                sources_dict, package_spec=package_name))
        tf = tarfile.open(filename, mode="r:gz")
        try:
            self.assertThat(
                tf,
                Not(TarfileHasFile("pkgs/%s" % dependency_package.filename)))
        finally:
            tf.close()

    def test_includes_local_debs(self):
        package_name = "foo"
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        local_path = maker.make_package(package_name, "1.2", {})
        available_package = FetchedPackage.from_deb(local_path)
        sources_dict = self.sourcesDictForPackages([])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict)
        builder = HardwarePackBuilder(
            config.filename, metadata.version, [local_path])
        builder.build()
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (
                metadata.name, metadata.version, metadata.architecture),
            IsHardwarePack(
                metadata, [available_package],
                sources_dict,
                package_spec=package_name))

    def test_prefers_local_debs(self):
        package_name = "foo"
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        # The point here is that remote_package has a later version than
        # local_package, but local_package is still preferred.
        remote_package = DummyFetchedPackage(package_name, "1.1")
        local_path = maker.make_package(package_name, "1.0", {})
        local_package = FetchedPackage.from_deb(local_path)
        sources_dict = self.sourcesDictForPackages([remote_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict)
        builder = HardwarePackBuilder(
            config.filename, metadata.version, [local_path])
        builder.build()
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (
                metadata.name, metadata.version, metadata.architecture),
            IsHardwarePack(
                metadata, [local_package],
                sources_dict,
                package_spec=package_name))

    def test_includes_local_debs_even_if_not_in_config(self):
        package_name = "foo"
        local_name = "bar"
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        remote_package = DummyFetchedPackage(package_name, "1.1")
        local_path = maker.make_package(local_name, "1.0", {})
        local_package = FetchedPackage.from_deb(local_path)
        sources_dict = self.sourcesDictForPackages([remote_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict)
        builder = HardwarePackBuilder(
            config.filename, metadata.version, [local_path])
        builder.build()
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (
                metadata.name, metadata.version, metadata.architecture),
            IsHardwarePack(
                metadata, [remote_package, local_package],
                sources_dict,
                package_spec=package_name))

    def test_warn_if_not_including_local_deb(self):
        package_name = "foo"
        local_name = "bar"
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))
        remote_package = DummyFetchedPackage(package_name, "1.1")
        local_path = maker.make_package(local_name, "1.0", {})
        sources_dict = self.sourcesDictForPackages([remote_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict,
            extra_config={'assume-installed': local_name})
        builder = HardwarePackBuilder(
            config.filename, metadata.version, [local_path])

        handler = AppendingHandler()
        builder_logger.addHandler(handler)
        self.addCleanup(builder_logger.removeHandler, handler)

        builder.build()
        self.assertThat(
            "hwpack_%s_%s_%s.tar.gz" % (
                metadata.name, metadata.version, metadata.architecture),
            IsHardwarePack(
                metadata, [remote_package],
                sources_dict,
                package_spec=package_name))
        self.assertThat(
            handler.messages,
            EachOf([MatchesStructure(levelname=Equals('WARNING'))]))
        self.assertThat(
            handler.messages[0].getMessage(),
            Equals("Local package 'bar' not included"))

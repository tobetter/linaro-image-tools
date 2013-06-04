# Copyright (C) 2010, 2011 Linaro
#
# Author: James Westby <james.westby@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import os
import tarfile

from testtools import TestCase
from testtools.matchers import Equals

from linaro_image_tools.hwpack.builder import (
    ConfigFileMissing,
    HardwarePackBuilder,
    logger as builder_logger,
)
from linaro_image_tools.hwpack.package_unpacker import PackageUnpacker
from linaro_image_tools.hwpack.config import HwpackConfigError
from linaro_image_tools.hwpack.hardwarepack import Metadata
from linaro_image_tools.hwpack.packages import (
    FetchedPackage,
    PackageMaker,
)
from linaro_image_tools.hwpack.tarfile_matchers import TarfileHasFile
from linaro_image_tools.hwpack.testing import (
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
)
from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import (
    MockSomethingFixture,
    MockCmdRunnerPopenFixture,
)


class ConfigFileMissingTests(TestCase):

    def test_str(self):
        exc = ConfigFileMissing("path")
        self.assertEqual("No such config file: 'path'", str(exc))


class PackageUnpackerTests(TestCaseWithFixtures):

    def test_creates_tempdir(self):
        with PackageUnpacker() as package_unpacker:
            self.assertTrue(os.path.exists(package_unpacker.tempdir))

    def test_tempfiles_are_removed(self):
        tempdir = None
        with PackageUnpacker() as package_unpacker:
            tempdir = package_unpacker.tempdir
        self.assertFalse(os.path.exists(tempdir))

    def test_unpack_package(self):
        fixture = MockCmdRunnerPopenFixture(assert_child_finished=False)
        self.useFixture(fixture)
        package_file_name = "package-to-unpack"
        with PackageUnpacker() as package_unpacker:
            package_unpacker.unpack_package(package_file_name)
            package_dir = package_unpacker.get_path(package_file_name)
        self.assertEquals(
            ["tar -C %s -xf -" % package_dir,
             "dpkg --fsys-tarfile %s" % package_file_name],
            fixture.mock.commands_executed)

    def test_get_file_returns_tempfile(self):
        package = 'package'
        file = 'dummyfile'
        with PackageUnpacker() as package_unpacker:
            self.useFixture(MockSomethingFixture(
                package_unpacker, 'unpack_package', lambda package: None))
            self.useFixture(MockSomethingFixture(
                os.path, 'exists', lambda file: True))
            tempfile = package_unpacker.get_file(package, file)
            self.assertEquals(tempfile,
                              os.path.join(package_unpacker.get_path(package),
                                           file))

    def test_get_file_raises(self):
        package = 'package'
        file = 'dummyfile'
        with PackageUnpacker() as package_unpacker:
            self.useFixture(MockSomethingFixture(
                package_unpacker, 'unpack_package', lambda package: None))
            self.assertRaises(AssertionError, package_unpacker.get_file,
                              package, file)

    def test_get_file_no_clash(self):
        # Test that PackageUnpacker, asked to get the same file path
        # from 2 different packages, return reference to *different*
        # temporary files
        package1 = 'package1'
        package2 = 'package2'
        file = 'dummyfile'
        with PackageUnpacker() as package_unpacker:
            self.useFixture(MockSomethingFixture(
                package_unpacker, 'unpack_package', lambda package: None))
            self.useFixture(MockSomethingFixture(
                os.path, 'exists', lambda file: True))
            tempfile1 = package_unpacker.get_file(package1, file)
            tempfile2 = package_unpacker.get_file(package2, file)
            self.assertNotEquals(tempfile1, tempfile2)


class HardwarePackBuilderTests(TestCaseWithFixtures):
    config_v3 = "\n".join(["format: 3.0",
                           "name: ahwpack",
                           "architectures: armel",
                           "serial_tty: ttySAC1",
                           "partition_layout:",
                           " - bootfs_rootfs",
                           "boot_script: boot.scr",
                           "mmc_id: 0:1",
                           "kernel_file: boot/vmlinuz-*-linaro-omap",
                           "initrd_file: boot/initrd.img-*-linaro-omap",
                           "dtb_file: boot/dt-*-linaro-omap/omap4-panda.dtb",
                           "packages:",
                           " - %s",
                           " - %s",
                           ""])
    bootloader_config = "\n".join(["  package: %s",
                                   "  in_boot_part: %s",
                                   ""])

    def setUp(self):
        super(HardwarePackBuilderTests, self).setUp()
        self.useFixture(ChdirToTempdirFixture())
        self.extra_config = {
            'format': '2.0',
            'u-boot-package': 'wanted-package',
            'u-boot-file': 'wanted-file',
            'partition_layout': 'bootfs_rootfs',
            'x_loader_package': 'x-loader-omap4-panda',
            'x_loader_file': 'usr/lib/x-loader/omap4430panda/MLO',
            'kernel_file': 'boot/vmlinuz-3.0.0-1002-linaro-omap',
            'initrd_file': 'boot/initrd.img-3.0.0-1002-linaro-omap',
            'boot_script': 'boot.scr',
            'mmc_id': '0:1',
            'u_boot_in_boot_part': 'no'}

    def test_raises_on_missing_configuration(self):
        e = self.assertRaises(
            ConfigFileMissing, HardwarePackBuilder, "nonexistant", "1.0", [])
        self.assertEqual("nonexistant", e.filename)

    def test_validates_configuration(self):
        config = self.useFixture(ConfigFileFixture(''))
        self.assertRaises(
            HwpackConfigError, HardwarePackBuilder, config.filename, "1.0",
            [])

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

    def test_find_fetched_package_finds(self):
        package_name = "dummy-package"
        wanted_package_name = "wanted-package"
        available_package = DummyFetchedPackage(package_name, "1.1")
        wanted_package = DummyFetchedPackage(wanted_package_name, "1.1")

        sources_dict = self.sourcesDictForPackages([available_package,
                                                    wanted_package])
        _, config = self.makeMetaDataAndConfigFixture(
            [package_name, wanted_package_name], sources_dict,
            extra_config=self.extra_config)
        builder = HardwarePackBuilder(config.filename, "1.0", [])
        found_package = builder.find_fetched_package(
            [available_package, wanted_package], wanted_package_name)
        self.assertEquals(wanted_package, found_package)

    def test_find_fetched_package_raises(self):
        package_name = "dummy-package"
        wanted_package_name = "wanted-package"
        available_package = DummyFetchedPackage(package_name, "1.1")

        sources_dict = self.sourcesDictForPackages([available_package])
        _, config = self.makeMetaDataAndConfigFixture(
            [package_name], sources_dict,
            extra_config=self.extra_config)
        builder = HardwarePackBuilder(config.filename, "1.0", [])
        packages = [available_package]
        self.assertRaises(AssertionError, builder.find_fetched_package,
                          packages, wanted_package_name)

    def test_creates_external_manifest(self):
        available_package = DummyFetchedPackage("foo", "1.1")
        sources_dict = self.sourcesDictForPackages([available_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            ["foo"], sources_dict)
        builder = HardwarePackBuilder(config.filename, "1.0", [])
        builder.build()
        self.assertTrue(
            os.path.isfile("hwpack_ahwpack_1.0_armel.manifest.txt"))

    def sourcesDictForPackages(self, packages):
        source = self.useFixture(AptSourceFixture(packages))
        return {'ubuntu': source.sources_entry}

    def test_builds_one_pack_per_arch(self):
        available_package = DummyFetchedPackage("foo", "1.1")
        sources_dict = self.sourcesDictForPackages([available_package])
        metadata, config = self.makeMetaDataAndConfigFixture(
            ["foo"], sources_dict, architecture="i386 armel")
        builder = HardwarePackBuilder(config.filename, "1.0", [])
        builder.build()
        self.assertTrue(os.path.isfile("hwpack_ahwpack_1.0_i386.tar.gz"))
        self.assertTrue(os.path.isfile("hwpack_ahwpack_1.0_armel.tar.gz"))

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

    def test_global_and_board_bootloader(self):
        package_names = ['package0', 'package1', 'package2', 'package3']
        files = {
            package_names[0]:
            ["usr/lib/u-boot/omap4_panda/u-boot.img",
             "usr/share/doc/u-boot-linaro-omap4-panda/copyright"],
            package_names[1]:
            ["usr/lib/u-boot/omap4_panda/u-boot.img",
             "some/path/file"],
            package_names[2]: [],
            package_names[3]: [],
        }

        config_v3 = self.config_v3 + "\n".join([
            "bootloaders:",
            " u_boot:",
            self.bootloader_config,
            "  file: " + files[package_names[0]][0],
            "  copy_files:",
            "    " + package_names[2] + ":",
            "      - some_file",
            "boards:",
            " board1:",
            "  bootloaders:",
            "   u_boot:",
            "    package: %s",
            "    file: " + files[package_names[1]][0],
            "    copy_files:",
            "      " + package_names[3] + ":",
            "       - some_file",
            "    in_boot_part: true",
            "sources:",
            " ubuntu: %s"])

        # Generate some test packages
        available_packages = []
        maker = PackageMaker()
        self.useFixture(ContextManagerFixture(maker))

        for package_name in package_names:
            # The files parameter to make_package is a list of files to create.
            # These files are text files containing package_name and their
            # path. Since package_name is different for each package, this
            # gives each file a unique content.
            deb_file_path = maker.make_package(package_name, '1.0', {},
                                               files=files[package_name])
            dummy_package = DummyFetchedPackage(
                package_name, "1.0", content=open(deb_file_path).read())
            available_packages.append(dummy_package)

        source = self.useFixture(AptSourceFixture(available_packages))

        # Generate a V3 config
        config_v3 = config_v3 % (package_names[0], package_names[1],
                                 package_names[0], "True",
                                 package_names[1],
                                 source.sources_entry)

        config_file_fixture = self.useFixture(ConfigFileFixture(config_v3))

        # Build a hardware pack
        builder = HardwarePackBuilder(
            config_file_fixture.filename, "1.0",
            [os.path.join(source.rootdir, package.filepath)
             for package in available_packages])

        builder.build()
        stored_package_names = [p.name for p in builder.packages]
        for package_name in package_names:
            self.assertIn(package_name, stored_package_names)

        # Read the contents of the hardware pack, making sure it is as expected
        tf = tarfile.open("hwpack_ahwpack_1.0_armel.tar.gz", mode="r:gz")

        # We check the content of each file when content != None. For our test
        # files this is "<package_name> <originating path>" so they can be
        # uniquely identified.
        expected_files = [
            ("u_boot/" + files[package_names[0]][0],
             package_names[0] + " " + files[package_names[0]][0]),
            ("board1/u_boot/" + files[package_names[1]][0],
             package_names[1] + " " + files[package_names[1]][0])]

        for expected_file, contents in expected_files:
            self.assertThat(
                tf, TarfileHasFile(expected_file, content=contents))

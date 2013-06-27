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

from StringIO import StringIO
import re
import tarfile

from testtools import TestCase
from testtools.matchers import Equals, MismatchError

from linaro_image_tools.hwpack.hardwarepack import HardwarePack, Metadata
from linaro_image_tools.hwpack.packages import get_packages_file
from linaro_image_tools.hwpack.testing import (
    DummyFetchedPackage,
    HardwarePackHasFile,
    MatchesAsPackagesFile,
    MatchesAsPackageContent,
    MatchesPackageRelationshipList,
    MatchesStructure,
    Not,
)
from linaro_image_tools.hwpack.hardwarepack_format import (
    HardwarePackFormatV1,
    HardwarePackFormatV2,
    HardwarePackFormatV3,
)


class MetadataTests(TestCase):
    def setUp(self):
        super(MetadataTests, self).setUp()
        self.metadata = Metadata("ahwpack", "3", "armel")

    def test_name(self):
        self.assertEqual("ahwpack", self.metadata.name)

    def test_version(self):
        self.assertEqual("3", self.metadata.version)

    def test_version_with_whitespace(self):
        self.assertRaises(
            AssertionError, Metadata, "ahwpack", "3 (with extras)", "armel")

    def test_architecture(self):
        self.assertEqual("armel", self.metadata.architecture)

    def test_default_origin_is_None(self):
        self.assertEqual(None, self.metadata.origin)

    def test_origin(self):
        metadata = Metadata("ahwpack", "4", "armel", origin="linaro")
        self.assertEqual("linaro", metadata.origin)

    def test_default_maintainer_is_None(self):
        metadata = Metadata("ahwpack", "4", "armel")
        self.assertEqual(None, metadata.maintainer)

    def test_maintainer(self):
        metadata = Metadata(
            "ahwpack", "4", "armel", maintainer="Some maintainer")
        self.assertEqual("Some maintainer", metadata.maintainer)

    def test_default_support_is_None(self):
        metadata = Metadata("ahwpack", "4", "armel")
        self.assertEqual(None, metadata.support)

    def test_support(self):
        metadata = Metadata("ahwpack", "4", "armel", support="supported")
        self.assertEqual("supported", metadata.support)

    def test_str(self):
        metadata = Metadata("ahwpack", "4", "armel")
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_origin(self):
        metadata = Metadata("ahwpack", "4", "armel", origin="linaro")
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "ORIGIN=linaro\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_maintainer(self):
        metadata = Metadata(
            "ahwpack", "4", "armel", maintainer="Some Maintainer")
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "MAINTAINER=Some Maintainer\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_support(self):
        metadata = Metadata("ahwpack", "4", "armel", support="unsupported")
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "SUPPORT=unsupported\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_serial_tty(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(serial_tty='ttyO2')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "SERIAL_TTY=ttyO2\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_kernel_addr(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(kernel_addr='0x80000000')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "KERNEL_ADDR=0x80000000\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_initrd_addr(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(initrd_addr='0x80000000')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "INITRD_ADDR=0x80000000\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_load_addr(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(load_addr='0x80000000')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "LOAD_ADDR=0x80000000\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_dtb_addr(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(dtb_addr='0x80000000')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "DTB_ADDR=0x80000000\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_wired_interfaces(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(wired_interfaces=['eth0', 'usb0'])
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "WIRED_INTERFACES=eth0 usb0\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_wireless_interfaces(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(wireless_interfaces=['wlan0', 'wl0'])
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "WIRELESS_INTERFACES=wlan0 wl0\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_partition_layout(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(partition_layout='bootfs_rootfs')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "PARTITION_LAYOUT=bootfs_rootfs\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_mmc_id(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(mmc_id='1')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "MMC_ID=1\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_boot_min_size(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(boot_min_size='50')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "BOOT_MIN_SIZE=50\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_root_min_size(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(root_min_size='100')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "ROOT_MIN_SIZE=100\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_loader_min_size(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(loader_min_size='1')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "LOADER_MIN_SIZE=1\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_kernel_file(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(vmlinuz='boot/vmlinuz-3.0.0-1002-linaro-omap')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "KERNEL_FILE=boot/vmlinuz-3.0.0-1002-linaro-omap\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_initrd_file(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(initrd='boot/initrd.img-3.0.0-1002-linaro-omap')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "INITRD_FILE=boot/initrd.img-3.0.0-1002-linaro-omap\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_dtb_file(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(
            dtb_file='boot/dt-3.0.0-1002-linaro-omap/omap4-panda.dtb')
        expected_out = ("NAME=ahwpack\nVERSION=4\n"
                        "ARCHITECTURE=armel\nDTB_FILE="
                        "boot/dt-3.0.0-1002-linaro-omap/omap4-panda.dtb\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_boot_script(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(boot_script='boot.scr')
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "BOOT_SCRIPT=boot.scr\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_extra_boot_options(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(
            extra_boot_options=(
                'earlyprintk fixrtc nocompcache vram=48M omapfb.vram=0:24M '
                'mem=456M@0x80000000 mem=512M@0xA0000000'))
        expected_out = ("NAME=ahwpack\nVERSION=4\nARCHITECTURE=armel\n"
                        "EXTRA_BOOT_OPTIONS=earlyprintk fixrtc nocompcache "
                        "vram=48M omapfb.vram=0:24M "
                        "mem=456M@0x80000000 mem=512M@0xA0000000\n")
        self.assertEqual(expected_out, str(metadata))

    def test_str_with_extra_serial_options(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV2())
        metadata.add_v2_config(
            extra_serial_options='console=tty0 console=ttyO2,115200n8')
        expected_out = ("NAME=ahwpack\nVERSION=4\n"
                        "ARCHITECTURE=armel\nEXTRA_SERIAL_OPTIONS="
                        "console=tty0 console=ttyO2,115200n8\n")
        self.assertEqual(expected_out, str(metadata))

    def test_from_config(self):
        class Config:
            name = "foo"
            origin = "linaro"
            maintainer = "someone"
            support = "supported"
            format = HardwarePackFormatV1()
        config = Config()
        metadata = Metadata.from_config(config, "2.0", "i386")
        self.assertEqual(config.name, metadata.name)
        self.assertEqual(config.origin, metadata.origin)
        self.assertEqual(config.maintainer, metadata.maintainer)
        self.assertEqual(config.support, metadata.support)
        self.assertEqual("2.0", metadata.version)
        self.assertEqual("i386", metadata.architecture)


class NewMetadataTests(TestCase):

    def setUp(self):
        super(NewMetadataTests, self).setUp()

    def test_format(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV3())
        # Need to call also this one!
        metadata.add_v2_config()
        metadata.add_v3_config(bootloaders=None)
        expected_out = ("format: '3.0'\nname: ahwpack\nversion: '4'\n"
                        "architecture: armel\n")
        self.assertEqual(expected_out, str(metadata))

    def test_section_bootloaders(self):
        bootloaders = {'u_boot': {'file': 'a_file'}}
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV3())
        # Need to call also this one!
        metadata.add_v2_config()
        metadata.add_v3_config(bootloaders=bootloaders)
        expected_out = ("format: '3.0'\nname: ahwpack\nversion: '4'\n"
                        "architecture: armel\nbootloaders:\n  u_boot:\n"
                        "    file: a_file\n")
        self.assertEqual(expected_out, str(metadata))

    def test_section_wireless(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV3())
        wireless_list = ['wlan0', 'wl0']
        # Need to call also this one!
        metadata.add_v2_config(wireless_interfaces=wireless_list)
        metadata.add_v3_config(bootloaders=None)
        expected_out = ("format: '3.0'\nname: ahwpack\nversion: '4'\n"
                        "architecture: armel\nwireless_interfaces: wlan0 "
                        "wl0\n")
        self.assertEqual(expected_out, str(metadata))

    def test_section_wired(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV3())
        wired_list = ['eth0', 'usb0']
        # Need to call also this one!
        metadata.add_v2_config(wired_interfaces=wired_list)
        metadata.add_v3_config(bootloaders=None)
        expected_out = ("format: '3.0'\nname: ahwpack\nversion: '4'\n"
                        "architecture: armel\nwired_interfaces: eth0 usb0\n")
        self.assertEqual(expected_out, str(metadata))

    def test_section_extra_serial_options(self):
        metadata = Metadata("ahwpack", "4", "armel",
                            format=HardwarePackFormatV3())
        options = ['option1', 'option2,option3']
        # Need to call also this one!
        metadata.add_v2_config(extra_serial_options=options)
        metadata.add_v3_config(bootloaders=None)
        expected_out = ("format: '3.0'\nname: ahwpack\nversion: '4'\n"
                        "architecture: armel\nextra_serial_options: option1 "
                        "option2,option3\n")
        self.assertEqual(expected_out, str(metadata))


class HardwarePackTests(TestCase):

    def setUp(self):
        super(HardwarePackTests, self).setUp()
        self.metadata = Metadata("ahwpack", "4", "armel")

    def test_format_is_correct(self):
        format = '1.0'
        hwpack = HardwarePack(self.metadata)
        self.assertEqual(format, hwpack.format.__str__())

    def test_format_has_no_spaces(self):
        hwpack = HardwarePack(self.metadata)
        self.assertIs(None, re.search('\s', hwpack.format.__str__()),
                      "hwpack.format contains spaces.")

    def test_filename(self):
        hwpack = HardwarePack(self.metadata)
        self.assertEqual("hwpack_ahwpack_4_armel.tar.gz", hwpack.filename())

    def test_filename_with_support(self):
        metadata = Metadata("ahwpack", "4", "armel", support="supported")
        hwpack = HardwarePack(metadata)
        self.assertEqual(
            "hwpack_ahwpack_4_armel_supported.tar.gz", hwpack.filename())

    def test_filename_with_extension(self):
        hwpack = HardwarePack(self.metadata)
        self.assertEqual(
            "hwpack_ahwpack_4_armel.txt", hwpack.filename('.txt'))

    def get_tarfile(self, hwpack):
        fileobj = StringIO()
        hwpack.to_file(fileobj)
        fileobj.seek(0)
        tf = tarfile.open(mode="r:gz", fileobj=fileobj)
        self.addCleanup(tf.close)
        return tf

    def test_creates_FORMAT_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("FORMAT",
                                content=hwpack.format.__str__() + "\n"))

    def test_creates_metadata_file(self):
        metadata = Metadata(
            "ahwpack", "4", "armel", origin="linaro",
            maintainer="Some Maintainer", support="unsupported")
        hwpack = HardwarePack(metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("metadata", content=str(metadata)))

    def test_creates_manifest_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("manifest"))

    def test_manifest_file_empty_with_no_packages(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("manifest", content=""))

    def test_manifest_contains_package_info(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.2")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("manifest", content="foo=1.1\nbar=1.2\n"))

    def test_creates_pkgs_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs", type=tarfile.DIRTYPE))

    def test_adds_packages(self):
        package = DummyFetchedPackage("foo", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package.filename,
                                content=package.content.read()))

    def test_adds_multiple_packages_at_once(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package1.filename,
                                content=package1.content.read()))
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package2.filename,
                                content=package2.content.read()))

    def test_adds_multiple_in_multiple_steps(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1])
        hwpack.add_packages([package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package1.filename,
                                content=package1.content.read()))
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/%s" % package2.filename,
                                content=package2.content.read()))

    def test_add_packages_without_content_leaves_out_debs(self):
        package1 = DummyFetchedPackage("foo", "1.1", no_content=True)
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            Not(HardwarePackHasFile("pkgs/%s" % package1.filename)))

    def test_add_dependency_package_adds_package(self):
        hwpack = HardwarePack(self.metadata)
        hwpack.add_dependency_package([])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile(
                "pkgs/%s_%s_%s.deb" % (
                    'hwpack-' + self.metadata.name, self.metadata.version,
                    self.metadata.architecture),
                content_matcher=MatchesAsPackageContent(
                    MatchesStructure(
                        name=Equals('hwpack-' + self.metadata.name),
                        architecture=Equals(self.metadata.architecture),
                        depends=Equals(None),
                        version=Equals(self.metadata.version)))))

    def test_add_dependency_package_adds_package_with_dependency(self):
        hwpack = HardwarePack(self.metadata)
        hwpack.add_dependency_package(["foo", "bar (= 1.0)"])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile(
                "pkgs/%s_%s_%s.deb" % (
                    'hwpack-' + self.metadata.name, self.metadata.version,
                    self.metadata.architecture),
                content_matcher=MatchesAsPackageContent(
                    MatchesStructure(
                        name=Equals('hwpack-' + self.metadata.name),
                        architecture=Equals(self.metadata.architecture),
                        depends=MatchesPackageRelationshipList(
                            [Equals("foo"), Equals("bar (= 1.0)")]),
                        version=Equals(self.metadata.version)))))

    def test_add_dependency_package_adds_package_to_Packages(self):
        hwpack = HardwarePack(self.metadata)
        hwpack.add_dependency_package(["foo", "bar (= 1.0)"])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile(
                "pkgs/Packages",
                content_matcher=MatchesAsPackagesFile(
                    MatchesStructure(
                        name=Equals('hwpack-' + self.metadata.name),
                        architecture=Equals(self.metadata.architecture),
                        depends=MatchesPackageRelationshipList(
                            [Equals("foo"), Equals("bar (= 1.0)")]),
                        version=Equals(self.metadata.version)))))

    def test_creates_Packages_file(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs/Packages"))

    def test_Packages_file_empty_with_no_packages(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(tf, HardwarePackHasFile("pkgs/Packages", content=""))

    def test_Packages_file_correct_contents_with_packages(self):
        package1 = DummyFetchedPackage("foo", "1.1")
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile(
                "pkgs/Packages",
                content=get_packages_file([package1, package2])))

    def test_Packages_file_empty_with_no_deb_content(self):
        package1 = DummyFetchedPackage("foo", "1.1", no_content=True)
        package2 = DummyFetchedPackage("bar", "1.1", no_content=True)
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("pkgs/Packages", content=""))

    def test_Packages_file_correct_content_with_some_deb_content(self):
        package1 = DummyFetchedPackage("foo", "1.1", no_content=True)
        package2 = DummyFetchedPackage("bar", "1.1")
        hwpack = HardwarePack(self.metadata)
        hwpack.add_packages([package1, package2])
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile(
                "pkgs/Packages",
                content=get_packages_file([package2])))

    def test_creates_sources_list_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d", type=tarfile.DIRTYPE))

    def test_adds_sources_list_file(self):
        hwpack = HardwarePack(self.metadata)
        source = 'http://example.org/ ubuntu'
        hwpack.add_apt_sources({'ubuntu': source})
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/ubuntu.list",
                                    content="deb " + source + "\n"))

    def test_adds_multiple_sources_list_files(self):
        hwpack = HardwarePack(self.metadata)
        source1 = 'http://example.org/ ubuntu main universe'
        source2 = 'http://example.org/ linaro'
        hwpack.add_apt_sources({'ubuntu': source1, 'linaro': source2})
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/ubuntu.list",
                                    content="deb " + source1 + "\n"))
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/linaro.list",
                                    content="deb " + source2 + "\n"))

    def test_overwrites_sources_list_file(self):
        hwpack = HardwarePack(self.metadata)
        old_source = 'http://example.org/ ubuntu'
        hwpack.add_apt_sources({'ubuntu': old_source})
        new_source = 'http://example.org/ ubuntu main universe'
        hwpack.add_apt_sources({'ubuntu': new_source})
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf, HardwarePackHasFile("sources.list.d/ubuntu.list",
                                    content="deb " + new_source + "\n"))

    def test_creates_sources_list_gpg_dir(self):
        hwpack = HardwarePack(self.metadata)
        tf = self.get_tarfile(hwpack)
        self.assertThat(
            tf,
            HardwarePackHasFile("sources.list.d.gpg", type=tarfile.DIRTYPE))

    def test_password_removed_from_urls(self):
        hwpack = HardwarePack(self.metadata)

        url = "https://username:password@hostname/url precise main"
        hwpack.add_apt_sources({"protected": url})

        tf = self.get_tarfile(hwpack)
        try:
            self.assertThat(
                tf, HardwarePackHasFile("sources.list.d/protected.list",
                                        content="deb " + url + "\n"))
        except MismatchError:
            pass  # Expect to not find the password protected URL
        else:
            self.assertTrue(False, "Found password protected URL in hwpack")

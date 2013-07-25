# Copyright (C) 2010 - 2012 Linaro
#
# Author: James Tunnicliffe <james.tunnicliffe@linaro.org>
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

import re
from StringIO import StringIO
from testtools import TestCase

from linaro_image_tools.hwpack.config import Config, HwpackConfigError
from linaro_image_tools.hwpack.hwpack_fields import (
    DEFINED_PARTITION_LAYOUTS,
    SAMSUNG_BL1_LEN_FIELD,
    SAMSUNG_BL1_START_FIELD,
    SAMSUNG_BL2_LEN_FIELD,
    SAMSUNG_BL2_START_FIELD,
    SAMSUNG_ENV_LEN_FIELD,
    SAMSUNG_ENV_START_FIELD,
)


class ConfigTests(TestCase):

    valid_start = (
        "name: ahwpack\npackages: foo\narchitectures: armel\n")
    valid_start_v3 = valid_start + "format: 3.0\n"
    valid_complete_v3 = (valid_start_v3 +
                         "serial_tty: ttySAC1\n"
                         "partition_layout:\n"
                         " - bootfs_rootfs\n"
                         "boot_script: boot.scr\n"
                         "extra_serial_options:\n"
                         "  - console=tty0\n"
                         "  - console=ttyO2,115200n8\n"
                         "mmc_id: 0:1\n"
                         "kernel_file: boot/vmlinuz-*-linaro-omap\n"
                         "initrd_file: boot/initrd.img-*-linaro-omap\n"
                         "dtb_file: boot/dt-*-linaro-omap/omap4-panda.dtb\n"
                         "bootloaders:\n"
                         " u_boot:\n"
                         "  package: u-boot-linaro-s5pv310\n"
                         "  file: usr/lib/u-boot/smdkv310/u-boot.bin\n"
                         "  spl_package: x-loader-omap4-panda\n"
                         "  spl_file: usr/lib/x-loader/omap4430panda/MLO\n"
                         "  in_boot_part: True\n"
                         "  extra_boot_options:\n"
                         "   - earlyprintk\n"
                         "   - fixrtc\n"
                         "   - nocompcache\n"
                         "   - vram=48M\n"
                         "   - omapfb.vram=0:24M\n"
                         "   - mem=456M@0x80000000\n"
                         "   - mem=512M@0xA0000000\n")
    valid_end = "sources:\n    sources-entry: foo bar\n"

    def test_create(self):
        config = Config(StringIO())
        self.assertTrue(config is not None)

    def get_config(self, contents):
        if not re.search("\s*format\s*:", contents):
            contents = "format: 3.0\n" + contents
        return Config(StringIO(contents), bootloader="u_boot")

    def assertConfigError(self, contents, f, *args, **kwargs):
        e = self.assertRaises(HwpackConfigError, f, *args, **kwargs)
        self.assertEqual(contents, str(e))

    def assertValidationError(self, contents, validate_function):
        self.assertConfigError(contents, validate_function)

    def test_validate_empty_name(self):
        config = self.get_config("name:  ")
        self.assertValidationError("Empty value for name",
                                   config._validate_name)

    def test_validate_invalid_name(self):
        config = self.get_config("name: ~~\n")
        self.assertValidationError("Invalid name: ~~",
                                   config._validate_name)

    def test_validate_invalid_include_debs(self):
        config = self.get_config(
            "name: ahwpack\n"
            "include_debs: if you don't mind\n")
        self.assertValidationError(
            "Invalid value for include-debs: if you don't mind",
            config._validate_include_debs)

    def test_validate_invalid_supported(self):
        config = self.get_config(
            "name: ahwpack\nsupport: if you pay us\n")
        self.assertValidationError(
            "Invalid value for support: if you pay us",
            config._validate_support)

    def test_validate_no_packages(self):
        config = self.get_config(
            "name: ahwpack\n\n")
        self.assertValidationError(
            "No packages found in the metadata", config._validate_packages)

    def test_validate_empty_packages(self):
        config = self.get_config(
            "name: ahwpack\npackages:  \n")
        self.assertValidationError(
            "No packages found in the metadata", config._validate_packages)

    def test_validate_invalid_package_name(self):
        config = self.get_config(
            "name: ahwpack\npackages: foo  ~~ bar\n")
        self.assertValidationError(
            "Invalid value in packages in the metadata: ~~",
            config._validate_packages)

    def test_validate_no_architectures(self):
        config = self.get_config(
            "name: ahwpack\npackages: foo\n")
        self.assertValidationError(
            "No architectures found in the metadata",
            config._validate_architectures)

    def test_validate_empty_architectures(self):
        config = self.get_config(
            "name: ahwpack\npackages: foo\n"
            "architectures: \n")
        self.assertValidationError(
            "No architectures found in the metadata",
            config._validate_architectures)

    def test_validate_invalid_package_name_in_assume_installed(self):
        config = self.get_config(
            "name: ahwpack\npackages: foo\n"
            "architectures: armel\nassume_installed:\n - bar\n - ~~\n")
        self.assertValidationError(
            "Invalid value in assume-installed in the metadata: ~~",
            config._validate_assume_installed)

    def test_validate_other_section_empty_sources_entry(self):
        config = self.get_config(
            self.valid_start + "sources:\n ubuntu:  \n")
        self.assertValidationError(
            "The sources-entry, ubuntu is missing the URI",
            config._validate_sources)

    def test_validate_other_section_only_uri_in_sources_entry(self):
        config = self.get_config(
            self.valid_start + "sources:\n ubuntu: foo\n")
        self.assertValidationError(
            "The sources-entry, ubuntu is missing the distribution",
            config._validate_sources)

    def test_validate_other_section_sources_entry_starting_with_deb(self):
        config = self.get_config(
            self.valid_start +
            "sources:\n ubuntu: deb http://example.org/ foo main\n")
        self.assertValidationError(
            "The sources-entry, ubuntu shouldn't start with 'deb'",
            config._validate_sources)

    def test_validate_other_section_sources_entry_starting_with_deb_src(self):
        config = self.get_config(
            self.valid_start +
            "sources:\n ubuntu: deb-src http://example.org/ foo main\n")
        self.assertValidationError(
            "The sources-entry, ubuntu shouldn't start with 'deb'",
            config._validate_sources)

    def test_validate_valid_config(self):
        config = self.get_config(self.valid_complete_v3)
        self.assertEqual(None, config.validate())

    def test_validate_supported_format(self):
        config = self.get_config(self.valid_start + "format: 0.9\n")
        self.assertValidationError(
            "Format version '0.9' is not supported.", config._validate_format)

    def test_validate_invalid_u_boot_package_name(self):
        config = self.get_config(self.valid_start_v3 +
                                 "bootloaders:\n"
                                 " u_boot:\n"
                                 "  package: ~~\n")
        self.assertValidationError(
            "Invalid value in u_boot_package in the metadata: ~~",
            config._validate_bootloader_package)

    def test_validate_invalid_bootloader_file(self):
        config = self.get_config(self.valid_start_v3 +
                                 "bootloaders:\n"
                                 " u_boot:\n"
                                 "  file: ~~\n")
        self.assertValidationError("Invalid path: ~~",
                                   config._validate_bootloader_file)

    def test_validate_invalid_kernel_file(self):
        config = self.get_config(self.valid_start_v3 +
                                 "kernel_file: ~~\n")
        self.assertValidationError("Invalid path: ~~",
                                   config._validate_vmlinuz)

    def test_validate_empty_kernel_file(self):
        config = self.get_config(self.valid_start_v3 +
                                 "kernel_file:  \n")
        self.assertValidationError("No kernel_file found in the metadata",
                                   config._validate_vmlinuz)

    def test_validate_invalid_initrd_file(self):
        config = self.get_config(self.valid_start_v3 +
                                 "initrd_file: ~~\n")
        self.assertValidationError("Invalid path: ~~", config._validate_initrd)

    def test_validate_empty_initrd_file(self):
        config = self.get_config(self.valid_start_v3 +
                                 "kernel_file:  \n")
        self.assertValidationError("No initrd_file found in the metadata",
                                   config._validate_initrd)

    def test_validate_invalid_boot_script(self):
        config = self.get_config(self.valid_start_v3 + "boot_script: ~~")
        self.assertValidationError("Invalid path: ~~",
                                   config._validate_boot_script)

    def test_validate_invalid_dtb_file(self):
        config = self.get_config(self.valid_start_v3 +
                                 "dtb_file: ~~\n")
        self.assertValidationError("Invalid path: ~~",
                                   config._validate_dtb_file)

    def test_validate_invalid_spl_package_name(self):
        config = self.get_config(self.valid_start_v3 +
                                 "bootloaders:\n"
                                 " u_boot:\n"
                                 "  spl_package: ~~\n")
        config.board = "panda"
        self.assertValidationError(
            "Invalid value in spl_package in the metadata: ~~",
            config._validate_spl_package)

    def test_validate_invalid_spl_file(self):
        config = self.get_config(self.valid_start_v3 +
                                 "boards:\n"
                                 " panda:\n"
                                 "  bootloaders:\n"
                                 "   u_boot:\n"
                                 "    spl_file: ~~\n")
        config.board = "panda"
        self.assertValidationError("Invalid path: ~~",
                                   config._validate_spl_file)

    def test_validate_partition_layout(self):
        partition_layout = 'apafs_bananfs'
        config = self.get_config(self.valid_start_v3 +
                                 "partition_layout: " + partition_layout)
        self.assertValidationError(
            "Undefined partition layout %s. "
            "Valid partition layouts are %s."
            % (partition_layout,
               ", ".join(DEFINED_PARTITION_LAYOUTS)),
            config._validate_partition_layout)

    def test_validate_wired_interfaces(self):
        self.assertTrue("XXX What is an invalid interface name?")

    def test_validate_wireless_interfaces(self):
        self.assertTrue("XXX What is an invalid interface name?")

    def test_validate_bootloader_in_boot_part_bool(self):
        config = self.get_config(
            self.valid_start_v3 +
            "bootloaders:\n"
            "   u_boot:\n"
            "    in_boot_part: Nope\n")
        self.assertValidationError(
            "Invalid value for bootloader_in_boot_part: Nope",
            config._validate_bootloader_file_in_boot_part)

    def test_find_board_specific_variable(self):
        config = self.get_config(
            self.valid_start_v3 +
            "boards:\n"
            " panda:\n"
            "  bootloaders:\n"
            "   u_boot:\n"
            "    in_boot_part: Yes\n")

        config.bootloader = "u_boot"
        config.board = "panda"

        config._validate_bootloader_file_in_boot_part()
        self.assertEqual(config.bootloader_file_in_boot_part, "yes")

    def test_board_specific_overwrites_global(self):
        config = self.get_config(
            self.valid_start_v3 +
            "bootloaders:\n"
            " u_boot:\n"
            "  in_boot_part: No\n"
            "boards:\n"
            " panda:\n"
            "  bootloaders:\n"
            "   u_boot:\n"
            "    in_boot_part: Yes\n")

        config.bootloader = "u_boot"
        config.board = "panda"

        config._validate_bootloader_file_in_boot_part()
        self.assertEqual(config.bootloader_file_in_boot_part, "yes")

    def test_multiple_bootloaders(self):
        config = self.get_config(
            self.valid_start_v3 +
            "bootloaders:\n"
            " u_boot:\n"
            "  in_boot_part: No\n"
            " anotherboot:\n"
            "  in_boot_part: Yes\n")

        config.bootloader = "u_boot"
        config._validate_bootloader_file_in_boot_part()
        self.assertEqual(config.bootloader_file_in_boot_part, "no")

        config.bootloader = "anotherboot"
        config._validate_bootloader_file_in_boot_part()
        self.assertEqual(config.bootloader_file_in_boot_part, "yes")

    def test_validate_serial_tty(self):
        config = self.get_config(self.valid_start_v3 + "serial_tty: tty\n")
        self.assertValidationError("Invalid serial tty: tty",
                                   config._validate_serial_tty)

        config = self.get_config(self.valid_start_v3 + "serial_tty: ttxSAC1\n")
        self.assertValidationError("Invalid serial tty: ttxSAC1",
                                   config._validate_serial_tty)

    def test_validate_mmc_id_wrong(self):
        # The mmc_id value, if coming from a yaml file, has to be quoted.
        # Make sure the test does not accept a valid-unquoted value.
        config = self.get_config(self.valid_complete_v3 +
                                 "mmc_id: 1:1\n")
        self.assertRaises(HwpackConfigError, config._validate_mmc_id)

    def test_validate_mmc_id(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "mmc_id: x\n")
        self.assertValidationError("Invalid mmc_id x", config._validate_mmc_id)

    def test_validate_boot_min_size(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "boot_min_size: x\n")
        self.assertValidationError("Invalid boot min size x",
                                   config._validate_boot_min_size)

    def test_validate_root_min_size(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "root_min_size: x\n")
        self.assertValidationError("Invalid root min size x",
                                   config._validate_root_min_size)

    def test_validate_loader_min_size(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "loader_min_size: x\n")
        self.assertValidationError("Invalid loader min size x",
                                   config._validate_loader_min_size)

    def test_validate_kernel_addr(self):
        # V3 change: All numerical inputs are good addresses (since YAML
        # converts them to ingegers and we convert them back to the correct
        # format). We don't need 8 digit hex values for addresses.
        config = self.get_config(self.valid_complete_v3 +
                                 "kernel_addr: 0x8000000\n")
        config._validate_kernel_addr()
        config = self.get_config(self.valid_complete_v3 +
                                 "kernel_addr: 0x8000000x\n")
        self.assertValidationError(
            "Invalid kernel address: 0x8000000x", config._validate_kernel_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "kernel_addr: 80000000\n")
        config._validate_kernel_addr()

    def test_validate_initrd_addr(self):
        # V3 change: All numerical inputs are good addresses (since YAML
        # converts them to ingegers and we convert them back to the correct
        # format). We don't need 8 digit hex values for addresses.
        config = self.get_config(self.valid_complete_v3 +
                                 "initrd_addr: 0x8000000\n")
        config._validate_initrd_addr()
        config = self.get_config(self.valid_complete_v3 +
                                 "initrd_addr: 0x8000000x\n")
        self.assertValidationError(
            "Invalid initrd address: 0x8000000x", config._validate_initrd_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "initrd_addr: 80000000\n")
        config._validate_initrd_addr()

    def test_validate_load_addr(self):
        # V3 change: All numerical inputs are good addresses (since YAML
        # converts them to ingegers and we convert them back to the correct
        # format). We don't need 8 digit hex values for addresses.
        config = self.get_config(self.valid_complete_v3 +
                                 "load_addr: 0x8000000\n")
        config._validate_load_addr()
        config = self.get_config(self.valid_complete_v3 +
                                 "load_addr: 0x8000000x\n")
        self.assertValidationError("Invalid load address: 0x8000000x",
                                   config._validate_load_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "load_addr: 80000000\n")
        config._validate_load_addr()

    def test_validate_dtb_addr(self):
        # V3 change: All numerical inputs are good addresses (since YAML
        # converts them to ingegers and we convert them back to the correct
        # format). We don't need 8 digit hex values for addresses.
        config = self.get_config(self.valid_complete_v3 +
                                 "dtb_addr: 0x8000000\n")
        config._validate_dtb_addr()
        config = self.get_config(self.valid_complete_v3 +
                                 "dtb_addr: 0x8000000x\n")
        self.assertValidationError("Invalid dtb address: 0x8000000x",
                                   config._validate_dtb_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "dtb_addr: 80000000\n")
        config._validate_dtb_addr()

    def test_wired_interfaces(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "wired_interfaces:\n - eth0\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["eth0"], config.wired_interfaces)
        config = self.get_config(self.valid_complete_v3 +
                                 "wired_interfaces:\n"
                                 " - eth0\n"
                                 " - eth1\n"
                                 " - usb2\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["eth0", "eth1", "usb2"], config.wired_interfaces)

    def test_wireless_interfaces(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "wireless_interfaces:\n"
                                 " - wlan0\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["wlan0"], config.wireless_interfaces)
        config = self.get_config(self.valid_complete_v3 +
                                 "wireless_interfaces:\n"
                                 " - wlan0\n"
                                 " - wl1\n"
                                 " - usb2\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["wlan0", "wl1", "usb2"], config.wireless_interfaces)

    def test_partition_layout(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("bootfs_rootfs",
                         config.partition_layout)

    def test_bootloader_file(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("usr/lib/u-boot/smdkv310/u-boot.bin",
                         config.bootloader_file)

    def test_u_boot_package(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("u-boot-linaro-s5pv310",
                         config.bootloader_package)

    def test_spl_file(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("usr/lib/x-loader/omap4430panda/MLO",
                         config.spl_file)

    def test_kernel_file(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("boot/vmlinuz-*-linaro-omap",
                         config.vmlinuz)

    def test_initrd_file(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("boot/initrd.img-*-linaro-omap",
                         config.initrd)

    def test_dtb_file(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("boot/dt-*-linaro-omap/omap4-panda.dtb",
                         config.dtb_file)

    def test_extra_boot_options(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual(
            "earlyprintk fixrtc nocompcache vram=48M "
            "omapfb.vram=0:24M mem=456M@0x80000000 mem=512M@0xA0000000",
            config.extra_boot_options)

    def test_extra_serial_options(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual('console=tty0 console=ttyO2,115200n8',
                         config.extra_serial_options)

    def test_boot_script(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("boot.scr",
                         config.boot_script)

    def test_u_boot_in_boot_part(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("yes",
                         config.bootloader_file_in_boot_part)

    def test_spl_package(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("x-loader-omap4-panda",
                         config.spl_package)

    def test_serial_tty(self):
        config = self.get_config(self.valid_complete_v3 + self.valid_end)
        config.validate()
        self.assertEqual("ttySAC1", config.serial_tty)

    def test_mmc_id(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "mmc_id: 0:1\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0:1", config.mmc_id)

    def test_boot_min_size(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "boot_min_size: 50\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("50", config.boot_min_size)

    def test_root_min_size(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "root_min_size: 50\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("50", config.root_min_size)

    def test_loader_min_size(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "loader_min_size: 2\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("2", config.loader_min_size)

    def test_kernel_addr(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "kernel_addr: 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.kernel_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "kernel_addr: 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8abcdeff", config.kernel_addr)

    def test_initrd_addr(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "initrd_addr: 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.initrd_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "initrd_addr: 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8abcdeff", config.initrd_addr)

    def test_load_addr(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "load_addr: 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.load_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "load_addr: 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8abcdeff", config.load_addr)

    def test_dtb_addr(self):
        config = self.get_config(self.valid_complete_v3 +
                                 "dtb_addr: 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.dtb_addr)
        config = self.get_config(self.valid_complete_v3 +
                                 "dtb_addr: 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8abcdeff", config.dtb_addr)

    def test_name(self):
        config = self.get_config(
            "name: ahwpack\n"
            "packages: foo\n"
            "architectures: armel\n")
        self.assertEqual("ahwpack", config.name)

    def test_include_debs(self):
        config = self.get_config(self.valid_start + "include_debs: false\n")
        self.assertEqual(False, config.include_debs)

    def test_include_debs_defaults_true(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(True, config.include_debs)

    def test_include_debs_defaults_true_on_empty(self):
        config = self.get_config(self.valid_start + "include_debs: \n")
        self.assertEqual(True, config.include_debs)

    def test_origin(self):
        config = self.get_config(self.valid_start + "origin: linaro\n")
        self.assertEqual("linaro", config.origin)

    def test_origin_default_None(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(None, config.origin)

    def test_origin_None_on_empty(self):
        config = self.get_config(self.valid_start + "origin:  \n")
        self.assertEqual(None, config.origin)

    def test_maintainer(self):
        maintainer = "Linaro Developers <linaro-dev@lists.linaro.org>"
        config = self.get_config(
            self.valid_start
            + "maintainer: %s\n" % maintainer)
        self.assertEqual(maintainer, config.maintainer)

    def test_maintainer_default_None(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(None, config.maintainer)

    def test_maintainer_None_on_empty(self):
        config = self.get_config(self.valid_start + "maintainer:  \n")
        self.assertEqual(None, config.maintainer)

    def test_support_supported(self):
        config = self.get_config(self.valid_start + "support: supported\n")
        self.assertEqual("supported", config.support)

    def test_support_unsupported(self):
        config = self.get_config(self.valid_start + "support: unsupported\n")
        self.assertEqual("unsupported", config.support)

    def test_support_default_None(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(None, config.support)

    def test_support_None_on_empty(self):
        config = self.get_config(self.valid_start + "support:  \n")
        self.assertEqual(None, config.support)

    def test_packages(self):
        config = self.get_config(
            "name: ahwpack\n"
            "packages:\n"
            " - foo\n"
            " - bar\n"
            "architectures: armel\n")
        self.assertEqual(["foo", "bar"], config.packages)

    def test_packages_filters_duplicates(self):
        config = self.get_config(
            "name: ahwpack\n"
            "packages:\n"
            " - foo\n"
            " - bar\n"
            " - foo\n"
            "architectures: armel\n")
        self.assertEqual(["foo", "bar"], config.packages)

    def test_sources_single(self):
        config = self.get_config(
            self.valid_start
            + "sources:\n"
              " ubuntu: http://example.org foo\n")
        self.assertEqual({"ubuntu": "http://example.org foo"}, config.sources)

    def test_sources_multiple(self):
        config = self.get_config(
            self.valid_start
            + "sources:\n"
              " ubuntu: http://example.org foo\n"
              " linaro: http://example.org bar\n")
        self.assertEqual(
            {"ubuntu": "http://example.org foo",
             "linaro": "http://example.org bar"},
            config.sources)

    def test_architectures(self):
        config = self.get_config(
            "name: ahwpack\n"
            "packages: foo\n"
            "architectures:\n"
            " - foo\n"
            " - bar\n")
        self.assertEqual(["foo", "bar"], config.architectures)

    def test_architectures_filters_duplicates(self):
        config = self.get_config(
            "name: ahwpack\n"
            "packages: foo\n"
            "architectures:\n"
            " - foo\n"
            " - bar\n"
            " - foo\n")
        self.assertEqual(["foo", "bar"], config.architectures)

    def test_assume_installed(self):
        config = self.get_config(
            "name: ahwpack\n"
            "packages:\n"
            " - foo\n"
            "architectures:\n"
            " - armel\n"
            "assume_installed:\n"
            " - foo\n"
            " - bar\n")
        self.assertEqual(["foo", "bar"], config.assume_installed)

    def test_assume_installed_filters_duplicates(self):
        config = self.get_config(
            "name: ahwpack\n"
            "packages:\n"
            " - foo\n"
            "architectures:\n"
            " - armel\n"
            "assume_installed:\n"
            " - foo\n"
            " - bar\n"
            " - foo\n")
        self.assertEqual(["foo", "bar"], config.assume_installed)

    def test_invalid_key_in_root(self):
        config = self.get_config("foo: bar")
        self.assertValidationError("Unknown key in metadata: 'foo'",
                                   config._validate_keys)

    def test_invalid_key_value_root(self):
        config = self.get_config("bootloaders: bar")
        self.assertValidationError("Invalid structure in metadata. Expected "
                                   "key: value pairs, found: 'bootloaders: "
                                   "bar'",
                                   config._validate_keys)

    def test_invalid_key_value_bootloaders(self):
        config = self.get_config("\n".join([
            "bootloaders:",
            " u_boot:",
            "  foo: bar"
        ]))
        self.assertValidationError("Unknown key in metadata: 'bootloaders: "
                                   "u_boot: foo'",
                                   config._validate_keys)

    def test_invalid_key_in_board(self):
        config = self.get_config("\n".join([
            "boards:",
            " pandaboard:",
            "  foo: bar"
        ]))
        self.assertValidationError("Unknown key in metadata: "
                                   "'boards: pandaboard: foo'",
                                   config._validate_keys)

    def test_invalid_key_in_board_2(self):
        config = self.get_config("\n".join([
            "boards:",
            " pandaboard:",
            "  name: bar",
            " snowball:",
            "  foo: bar",
        ]))
        self.assertValidationError("Unknown key in metadata: "
                                   "'boards: snowball: foo'",
                                   config._validate_keys)

    def test_valid_samsung_bl1_len_field(self):
        config = self.get_config(self.valid_start_v3 +
                                 SAMSUNG_BL1_LEN_FIELD + ': 1\n')
        self.assertEqual(None, config._validate_keys())

    def test_valid_samsung_bl1_start_field(self):
        config = self.get_config(self.valid_start_v3 +
                                 SAMSUNG_BL1_START_FIELD + ': 1\n')
        self.assertEqual(None, config._validate_keys())

    def test_valid_samsung_bl2_len_field(self):
        config = self.get_config(self.valid_start_v3 +
                                 SAMSUNG_BL2_LEN_FIELD + ': 1\n')
        self.assertEqual(None, config._validate_keys())

    def test_valid_samsung_bl2_start_field(self):
        config = self.get_config(self.valid_start_v3 +
                                 SAMSUNG_BL2_START_FIELD + ': 1\n')
        self.assertEqual(None, config._validate_keys())

    def test_valid_samsung_env_len_field(self):
        config = self.get_config(self.valid_start_v3 +
                                 SAMSUNG_ENV_LEN_FIELD + ': 1\n')
        self.assertEqual(None, config._validate_keys())

    def test_valid_samsung_env_start_field(self):
        config = self.get_config(self.valid_start_v3 +
                                 SAMSUNG_ENV_START_FIELD + ': 1\n')
        self.assertEqual(None, config._validate_keys())

    def test_samsung_field_wrong(self):
        config = self.get_config(self.valid_start_v3 +
                                 'samsung_wrong_field: 1\n')
        self.assertRaises(HwpackConfigError, config._validate_keys)

    # Tests for dtb_files support
    def test_dtb_files(self):
        dtb_files = ('dtb_files:\n' +
                     ' - adest.dtb : boot/dt-*-linaro-omap/omap4-panda.dtb\n' +
                     ' - bdest.dtb : ' +
                     'boot/dt-*-linaro-omap2/omap4-panda2.dtb\n')
        expected = [{'adest.dtb': 'boot/dt-*-linaro-omap/omap4-panda.dtb'},
                    {'bdest.dtb': 'boot/dt-*-linaro-omap2/omap4-panda2.dtb'}]
        config = self.get_config(self.valid_complete_v3 + dtb_files)
        config.validate()
        self.assertEqual(expected, config.dtb_files)

    def test_dtb_files_one_wrong(self):
        dtb_files = ('dtb_files:\n' +
                     ' - adest.dtb : boot/dt-*-linaro-omap/omap4-panda.dtb\n' +
                     ' - bdest.dtb : ~~~\n')
        config = self.get_config(self.valid_start_v3 + dtb_files)
        self.assertRaises(HwpackConfigError, config._validate_dtb_files)

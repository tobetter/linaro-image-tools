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

from testtools import TestCase

from linaro_image_tools.hwpack.config import Config, HwpackConfigError
from linaro_image_tools.hwpack.hwpack_fields import (
    DEFINED_PARTITION_LAYOUTS,
)


class ConfigTests(TestCase):

    valid_start = (
        "[hwpack]\nname = ahwpack\npackages = foo\narchitectures = armel\n")
    valid_start_v2 = valid_start + "format = 2.0\n"
    valid_complete_v2 = (valid_start_v2 +
                         "u_boot_package = u-boot-linaro-s5pv310\n"
                         "u_boot_file = usr/lib/u-boot/smdkv310/"
                         "u-boot.bin\nserial_tty=ttySAC1\n"
                         "partition_layout = bootfs_rootfs\n"
                         "spl_package = x-loader-omap4-panda\n"
                         "spl_file = usr/lib/x-loader/omap4430panda/MLO\n"
                         "kernel_file = boot/vmlinuz-*-linaro-omap\n"
                         "initrd_file = boot/initrd.img-*-linaro-omap\n"
                         "dtb_file = boot/dt-*-linaro-omap/omap4-panda.dtb\n"
                         "boot_script = boot.scr\n" +
                         ("extra_serial_options = console=tty0 "
                          "console=ttyO2,115200n8\n") +
                         ("extra_boot_options = earlyprintk fixrtc "
                          "nocompcache vram=48M omapfb.vram=0:24M "
                          "mem=456M@0x80000000 mem=512M@0xA0000000\n") +
                         "boot_script = boot.scr\n"
                         "mmc_id = 0:1\n"
                         "u_boot_in_boot_part = Yes\n")
    valid_end = "[ubuntu]\nsources-entry = foo bar\n"

    def test_create(self):
        config = Config(StringIO())
        self.assertTrue(config is not None)

    def get_config(self, contents):
        return Config(StringIO(contents))

    def assertConfigError(self, contents, f, *args, **kwargs):
        e = self.assertRaises(HwpackConfigError, f, *args, **kwargs)
        self.assertEqual(contents, str(e))

    def assertValidationError(self, contents, config, function="validate"):
        self.assertConfigError(contents, config.get_option(function))

    def test_validate_no_hwpack_section(self):
        config = self.get_config("")
        self.assertValidationError("No [hwpack] section", config)

    def test_validate_no_name(self):
        config = self.get_config("[hwpack]\n")
        self.assertValidationError("Empty value for name", config)

    def test_validate_empty_name(self):
        config = self.get_config("[hwpack]\nname =  \n")
        self.assertValidationError("Empty value for name", config)

    def test_validate_invalid_name(self):
        config = self.get_config("[hwpack]\nname = ~~\n")
        self.assertValidationError("Invalid name: ~~", config)

    def test_validate_invalid_include_debs(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\n"
            "include-debs = if you don't mind\n")
        self.assertValidationError(
            "Invalid value for include-debs: Not a boolean: if you don't mind",
            config)

    def test_validate_invalid_supported(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\nsupport = if you pay us\n")
        self.assertValidationError(
            "Invalid value for support: if you pay us", config)

    def test_validate_no_packages(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\n\n")
        self.assertValidationError(
            "No packages in the [hwpack] section", config)

    def test_validate_empty_packages(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\npackages =  \n")
        self.assertValidationError(
            "No packages in the [hwpack] section", config)

    def test_validate_invalid_package_name(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\npackages = foo  ~~ bar\n")
        self.assertValidationError(
            "Invalid value in packages in the [hwpack] section: ~~",
            config)

    def test_validate_no_architectures(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\npackages = foo\n")
        self.assertValidationError(
            "No architectures in the [hwpack] section", config)

    def test_validate_empty_architectures(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\npackages = foo\n"
            "architectures = \n")
        self.assertValidationError(
            "No architectures in the [hwpack] section", config)

    def test_validate_invalid_package_name_in_assume_installed(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\npackages = foo\n"
            "architectures = armel\nassume-installed = bar ~~\n")
        self.assertValidationError(
            "Invalid value in assume-installed in the [hwpack] section: ~~",
            config)

    def test_validate_no_other_sections(self):
        config = self.get_config(self.valid_start + "\n")
        self.assertValidationError(
            "No sections other than [hwpack]", config)

    def test_validate_other_section_no_sources_entry(self):
        config = self.get_config(self.valid_start + "\n[ubuntu]\n")
        self.assertValidationError(
            "No sources-entry in the [ubuntu] section", config)

    def test_validate_other_section_empty_sources_entry(self):
        config = self.get_config(
            self.valid_start + "\n[ubuntu]\nsources-entry =  \n")
        self.assertValidationError(
            "The sources-entry in the [ubuntu] section is missing the URI",
            config)

    def test_validate_other_section_only_uri_in_sources_entry(self):
        config = self.get_config(
            self.valid_start + "\n[ubuntu]\nsources-entry =  foo\n")
        self.assertValidationError(
            "The sources-entry in the [ubuntu] section is missing the "
            "distribution", config)

    def test_validate_other_section_sources_entry_starting_with_deb(self):
        config = self.get_config(
            self.valid_start
            + "\n[ubuntu]\nsources-entry =  deb http://example.org/ "
            "foo main\n")
        self.assertValidationError(
            "The sources-entry in the [ubuntu] section shouldn't start "
            "with 'deb'", config)

    def test_validate_other_section_sources_entry_starting_with_deb_src(self):
        config = self.get_config(
            self.valid_start
            + "\n[ubuntu]\nsources-entry =  deb-src http://example.org/ "
            "foo main\n")
        self.assertValidationError(
            "The sources-entry in the [ubuntu] section shouldn't start "
            "with 'deb'", config)

    def test_validate_valid_config(self):
        config = self.get_config(
            self.valid_start
            + "\n[ubuntu]\nsources-entry = foo bar\n")
        self.assertEqual(None, config.validate())

    def test_validate_valid_config_with_dash_in_package_name(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\n"
            "packages = u-boot\n"
            "architectures = armel\n\n"
            "[ubuntu]\nsources-entry = foo bar\n")
        self.assertEqual(None, config.validate())

    def test_validate_supported_format(self):
        contents = self.valid_start + "format = 0.9\n"
        config = Config(StringIO(contents))
        self.assertRaises(HwpackConfigError, config.validate)

    def test_validate_invalid_u_boot_package_name(self):
        config = self.get_config(
            self.valid_start_v2 + "u_boot_package = ~~\n")
        self.assertValidationError(
            "Invalid value in u_boot_package in the [hwpack] section: ~~",
            config)

    def test_validate_invalid_u_boot_file(self):
        config = self.get_config(self.valid_start_v2 +
                                 "u_boot_package = u-boot-linaro-s5pv310\n"
                                 "u_boot_file = ~~\n")
        self.assertValidationError("Invalid path: ~~", config)

    def test_validate_invalid_kernel_file(self):
        config = self.get_config(self.valid_start_v2 +
                                 "u-boot-package = u-boot-linaro-s5pv310\n"
                                 "u-boot-file = u-boot.bin\n"
                                 "partition_layout = bootfs_rootfs\n"
                                 "kernel_file = ~~\n")
        self.assertValidationError("Invalid path: ~~", config,
                                   "_validate_vmlinuz")

    def test_validate_empty_kernel_file(self):
        config = self.get_config(self.valid_start_v2 +
                                 "u-boot-package = u-boot-linaro-s5pv310\n"
                                 "u-boot-file = u-boot.bin\n"
                                 "partition_layout = bootfs_rootfs\n"
                                 "kernel_file = \n")
        self.assertValidationError("No kernel_file in the [hwpack] section",
                                   config, "_validate_vmlinuz")

    def test_validate_invalid_initrd_file(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u-boot-package = u-boot-linaro-s5pv310\n"
            "u-boot-file = u-boot.bin\n"
            "partition_layout = bootfs_rootfs\n"
            "kernel_file = boot/vmlinuz-3.0.0-1002-linaro-omap\n"
            "initrd_file = ~~\n")
        self.assertValidationError("Invalid path: ~~", config,
                                   "_validate_initrd")

    def test_validate_empty_initrd_file(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u-boot-package = u-boot-linaro-s5pv310\n"
            "u-boot-file = u-boot.bin\n"
            "partition_layout = bootfs_rootfs\n"
            "kernel_file = boot/vmlinuz-3.0.0-1002-linaro-omap\n"
            "initrd_file = \n")
        self.assertValidationError("No initrd_file in the [hwpack] section",
                                   config, "_validate_initrd")

    def test_validate_invalid_boot_script(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u-boot-package = u-boot-linaro-s5pv310\n"
            "mmc_id = 0:1\n"
            "u-boot-file = u-boot.bin\n"
            "partition_layout = bootfs_rootfs\n"
            "kernel_file = boot/vmlinuz-3.0.0-1002-linaro-omap\n"
            "initrd_file = boot/initrd.img-3.0.0-1002-linaro-omap\n"
            "u_boot_in_boot_part = No\n"
            "boot_script = ~~\n")
        self.assertValidationError("Invalid path: ~~", config)

    def test_validate_invalid_dtb_file(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u-boot-package = u-boot-linaro-s5pv310\n"
            "u-boot-file = u-boot.bin\n"
            "partition_layout = bootfs_rootfs\n"
            "kernel_file = boot/vmlinuz-3.0.0-1002-linaro-omap\n"
            "initrd_file = boot/initrd.img-3.0.0-1002-linaro-omap\n"
            "boot_script = boot.scr\n"
            "u_boot_in_boot_part = No\n"
            "mmc_id = 0:1\n"
            "dtb_file = ~~\n")
        self.assertValidationError("Invalid path: ~~", config)

    def test_validate_invalid_spl_package_name(self):
        config = self.get_config(
            self.valid_start_v2 + "u-boot-package = u-boot-linaro-s5pv310\n"
            "u-boot-file = usr/bin/version/MLO\n"
            "partition_layout = bootfs_rootfs\n"
            "mmc_id = 0:1\n"
            "spl_package = ~~\n")
        self.assertValidationError(
            "Invalid value in spl_package in the [hwpack] section: ~~",
            config)

    def test_validate_invalid_spl_file(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u-boot-package = u-boot-linaro-s5pv310\n"
            "u-boot-file = usr/bin/version/MLO\n"
            "partition_layout = bootfs_rootfs\n"
            "spl_package = x-loader--linaro-s5pv310\n"
            "spl_file = ~~\n")
        self.assertValidationError("Invalid path: ~~", config)

    def test_validate_partition_layout(self):
        partition_layout = 'apafs_bananfs'
        config = self.get_config(self.valid_start_v2 + "u_boot_package = "
                                 "u-boot-linaro-s5pv310\nu_boot_file = "
                                 "u-boot.bin\npartition_layout = %s\n" %
                                 partition_layout)
        self.assertValidationError(
            "Undefined partition layout %s in the [%s] section. "
            "Valid partition layouts are %s."
            % (partition_layout, 'hwpack',
               ", ".join(DEFINED_PARTITION_LAYOUTS)), config,
            "_validate_partition_layout")

    def test_validate_wired_interfaces(self):
        self.assertTrue("XXX What is an invalid interface name?")

    def test_validate_wireless_interfaces(self):
        self.assertTrue("XXX What is an invalid interface name?")

    def test_validate_u_boot_in_boot_part(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u-boot-package = u-boot-linaro-s5pv310\n"
            "u-boot-file = u-boot.bin\n"
            "partition_layout = bootfs_rootfs\n"
            "kernel_file = boot/vmlinuz-3.0.0-1002-linaro-omap\n"
            "initrd_file = boot/initrd.img-3.0.0-1002-linaro-omap\n"
            "boot_script = boot.scr\n"
            "mmc_id = 0:1\n"
            "u_boot_in_boot_part = Nope\n")
        self.assertValidationError(
            "Invalid value for u_boot_in_boot_part: Nope", config)

    def test_validate_u_boot_in_boot_part_bool(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u-boot-package = u-boot-linaro-s5pv310\n"
            "u-boot-file = u-boot.bin\n"
            "partition_layout = bootfs_rootfs\n"
            "kernel_file = boot/vmlinuz-3.0.0-1002-linaro-omap\n"
            "initrd_file = boot/initrd.img-3.0.0-1002-linaro-omap\n"
            "boot_script = boot.scr\n"
            "mmc_id = 0:1\n"
            "u_boot_in_boot_part = True\n")
        self.assertValidationError(
            "Invalid value for u_boot_in_boot_part: True", config)

    def test_validate_serial_tty(self):
        config = self.get_config(
            self.valid_start_v2 +
            "u_boot_package = u-boot-linaro-s5pv310\n"
            "u_boot_file = u-boot.bin\nserial_tty=tty\n")
        self.assertValidationError("Invalid serial tty: tty", config,
                                   "_validate_serial_tty")
        config = self.get_config(
            self.valid_start_v2 +
            "u_boot_package = u-boot-linaro-s5pv310\n"
            "u_boot_file = u-boot.bin\n"
            "serial_tty=ttxSAC1\n")
        self.assertValidationError("Invalid serial tty: ttxSAC1", config,
                                   "_validate_serial_tty")

    def test_validate_mmc_id(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "mmc_id = x\n")
        self.assertValidationError("Invalid mmc_id x", config)

    def test_validate_boot_min_size(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "boot_min_size = x\n")
        self.assertValidationError("Invalid boot min size x", config)

    def test_validate_root_min_size(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "root_min_size = x\n")
        self.assertValidationError("Invalid root min size x", config)

    def test_validate_loader_min_size(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "loader_min_size = x\n")
        self.assertValidationError("Invalid loader min size x", config)

    def test_validate_kernel_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "kernel_addr = 0x8000000\n")
        self.assertValidationError("Invalid kernel address: 0x8000000", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "kernel_addr = 0x8000000x\n")
        self.assertValidationError(
            "Invalid kernel address: 0x8000000x", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "kernel_addr = 80000000\n")
        self.assertValidationError("Invalid kernel address: 80000000", config)

    def test_validate_initrd_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "initrd_addr = 0x8000000\n")
        self.assertValidationError("Invalid initrd address: 0x8000000", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "initrd_addr = 0x8000000x\n")
        self.assertValidationError(
            "Invalid initrd address: 0x8000000x", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "initrd_addr = 80000000\n")
        self.assertValidationError("Invalid initrd address: 80000000", config)

    def test_validate_load_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "load_addr = 0x8000000\n")
        self.assertValidationError("Invalid load address: 0x8000000", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "load_addr = 0x8000000x\n")
        self.assertValidationError("Invalid load address: 0x8000000x", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "load_addr = 80000000\n")
        self.assertValidationError("Invalid load address: 80000000", config)

    def test_validate_dtb_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "dtb_addr = 0x8000000\n")
        self.assertValidationError("Invalid dtb address: 0x8000000", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "dtb_addr = 0x8000000x\n")
        self.assertValidationError("Invalid dtb address: 0x8000000x", config)
        config = self.get_config(self.valid_complete_v2 +
                                 "dtb_addr = 80000000\n")
        self.assertValidationError("Invalid dtb address: 80000000", config)

    def test_wired_interfaces(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "wired_interfaces = eth0\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["eth0"], config.wired_interfaces)
        config = self.get_config(self.valid_complete_v2 +
                                 "wired_interfaces = eth0 eth1 usb2\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["eth0", "eth1", "usb2"], config.wired_interfaces)

    def test_wireless_interfaces(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "wireless_interfaces = wlan0\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["wlan0"], config.wireless_interfaces)
        config = self.get_config(self.valid_complete_v2 +
                                 "wireless_interfaces = wlan0 wl1 usb2\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual(["wlan0", "wl1", "usb2"], config.wireless_interfaces)

    def test_partition_layout(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("bootfs_rootfs",
                         config.partition_layout)

    def test_u_boot_file(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("usr/lib/u-boot/smdkv310/u-boot.bin",
                         config.bootloader_file)

    def test_u_boot_package(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("u-boot-linaro-s5pv310",
                         config.bootloader_package)

    def test_spl_file(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("usr/lib/x-loader/omap4430panda/MLO",
                         config.spl_file)

    def test_kernel_file(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("boot/vmlinuz-*-linaro-omap",
                         config.vmlinuz)

    def test_initrd_file(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("boot/initrd.img-*-linaro-omap",
                         config.initrd)

    def test_dtb_file(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("boot/dt-*-linaro-omap/omap4-panda.dtb",
                         config.dtb_file)

    def test_extra_boot_options(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual(
            "earlyprintk fixrtc nocompcache vram=48M "
            "omapfb.vram=0:24M mem=456M@0x80000000 mem=512M@0xA0000000",
            config.extra_boot_options)

    def test_extra_serial_options(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("console=tty0 console=ttyO2,115200n8",
                         config.extra_serial_options)

    def test_boot_script(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("boot.scr",
                         config.boot_script)

    def test_u_boot_in_boot_part(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("Yes",
                         config.bootloader_file_in_boot_part)

    def test_spl_package(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("x-loader-omap4-panda",
                         config.spl_package)

    def test_serial_tty(self):
        config = self.get_config(self.valid_complete_v2 + self.valid_end)
        config.validate()
        self.assertEqual("ttySAC1", config.serial_tty)

    def test_mmc_id(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "mmc_id = 0:1\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0:1", config.mmc_id)

    def test_boot_min_size(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "boot_min_size = 50\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("50", config.boot_min_size)

    def test_root_min_size(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "root_min_size = 50\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("50", config.root_min_size)

    def test_loader_min_size(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "loader_min_size = 2\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("2", config.loader_min_size)

    def test_kernel_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "kernel_addr = 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.kernel_addr)
        config = self.get_config(self.valid_complete_v2 +
                                 "kernel_addr = 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8aBcdEFf", config.kernel_addr)

    def test_initrd_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "initrd_addr = 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.initrd_addr)
        config = self.get_config(self.valid_complete_v2 +
                                 "initrd_addr = 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8aBcdEFf", config.initrd_addr)

    def test_load_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "load_addr = 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.load_addr)
        config = self.get_config(self.valid_complete_v2 +
                                 "load_addr = 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8aBcdEFf", config.load_addr)

    def test_dtb_addr(self):
        config = self.get_config(self.valid_complete_v2 +
                                 "dtb_addr = 0x80000000\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x80000000", config.dtb_addr)
        config = self.get_config(self.valid_complete_v2 +
                                 "dtb_addr = 0x8aBcdEFf\n" +
                                 self.valid_end)
        config.validate()
        self.assertEqual("0x8aBcdEFf", config.dtb_addr)

    def test_name(self):
        config = self.get_config(
            "[hwpack]\nname = ahwpack\npackages = foo\n"
            "architectures = armel\n")
        self.assertEqual("ahwpack", config.name)

    def test_include_debs(self):
        config = self.get_config(self.valid_start + "include-debs = false\n")
        self.assertEqual(False, config.include_debs)

    def test_include_debs_defaults_true(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(True, config.include_debs)

    def test_include_debs_defaults_true_on_empty(self):
        config = self.get_config(self.valid_start + "include-debs = \n")
        self.assertEqual(True, config.include_debs)

    def test_origin(self):
        config = self.get_config(self.valid_start + "origin = linaro\n")
        self.assertEqual("linaro", config.origin)

    def test_origin_default_None(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(None, config.origin)

    def test_origin_None_on_empty(self):
        config = self.get_config(self.valid_start + "origin =  \n")
        self.assertEqual(None, config.origin)

    def test_maintainer(self):
        maintainer = "Linaro Developers <linaro-dev@lists.linaro.org>"
        config = self.get_config(
            self.valid_start
            + "maintainer = %s\n" % maintainer)
        self.assertEqual(maintainer, config.maintainer)

    def test_maintainer_default_None(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(None, config.maintainer)

    def test_maintainer_None_on_empty(self):
        config = self.get_config(self.valid_start + "maintainer =  \n")
        self.assertEqual(None, config.maintainer)

    def test_support_supported(self):
        config = self.get_config(self.valid_start + "support = supported\n")
        self.assertEqual("supported", config.support)

    def test_support_unsupported(self):
        config = self.get_config(self.valid_start + "support = unsupported\n")
        self.assertEqual("unsupported", config.support)

    def test_support_default_None(self):
        config = self.get_config(self.valid_start)
        self.assertEqual(None, config.support)

    def test_support_None_on_empty(self):
        config = self.get_config(self.valid_start + "support =  \n")
        self.assertEqual(None, config.support)

    def test_packages(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo  bar\n"
            "architectures=armel\n")
        self.assertEqual(["foo", "bar"], config.packages)

    def test_packages_with_newline(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo\n bar\n"
            "architectures=armel\n")
        self.assertEqual(["foo", "bar"], config.packages)

    def test_packages_filters_duplicates(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo bar foo\n"
            "architectures=armel\n")
        self.assertEqual(["foo", "bar"], config.packages)

    def test_sources_single(self):
        config = self.get_config(
            self.valid_start
            + "\n[ubuntu]\nsources-entry = http://example.org foo\n")
        self.assertEqual({"ubuntu": "http://example.org foo"}, config.sources)

    def test_sources_multiple(self):
        config = self.get_config(
            self.valid_start
            + "\n[ubuntu]\nsources-entry = http://example.org foo\n"
            + "\n[linaro]\nsources-entry = http://example.org bar\n")
        self.assertEqual(
            {"ubuntu": "http://example.org foo",
             "linaro": "http://example.org bar"},
            config.sources)

    def test_architectures(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo\narchitectures=foo  bar\n")
        self.assertEqual(["foo", "bar"], config.architectures)

    def test_architectures_with_newline(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo\narchitectures=foo\n bar\n")
        self.assertEqual(["foo", "bar"], config.architectures)

    def test_architectures_filters_duplicates(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo\n"
            "architectures=foo bar foo\n")
        self.assertEqual(["foo", "bar"], config.architectures)

    def test_assume_installed(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo\narchitectures=armel\n"
            "assume-installed=foo  bar\n")
        self.assertEqual(["foo", "bar"], config.assume_installed)

    def test_assume_installed_with_newline(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo\narchitectures=armel\n"
            "assume-installed=foo\n bar\n")
        self.assertEqual(["foo", "bar"], config.assume_installed)

    def test_assume_installed_filters_duplicates(self):
        config = self.get_config(
            "[hwpack]\nname=ahwpack\npackages=foo\narchitectures=armel\n"
            "assume-installed=foo bar foo\n")
        self.assertEqual(["foo", "bar"], config.assume_installed)

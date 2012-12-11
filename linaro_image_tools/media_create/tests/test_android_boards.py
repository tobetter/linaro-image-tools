# Copyright (C) 2010, 2011 Linaro
#
# Author: Milo Casagrande <milo.casagrande@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from StringIO import StringIO
from testtools import TestCase

from linaro_image_tools.media_create.boards import (
    BoardConfigException,
    )

from linaro_image_tools.media_create.android_boards import (
    AndroidBeagleConfig,
    get_board_config,
    )


class TestAndroidBoards(TestCase):
    """Class to test small things in android_boards."""

    def test_get_board_config(self):
        instance = get_board_config('beagle')
        self.assertIsInstance(instance, AndroidBeagleConfig)

    def test_get_board_config_wrong(self):
        self.assertRaises(BoardConfigException, get_board_config, 'notadevice')


class TestAndroidBoardsHwpack(TestCase):
    """Class to test the new Android hwpack configuration file."""

    def setUp(self):
        super(TestAndroidBoardsHwpack, self).setUp()
        # Pick a default board.
        self.config = get_board_config('beagle')
        self.hwpack_base = "format: 3.0\n"
        self.fake_hwpack = (self.hwpack_base + "dtb_name: a_name\n"
                            "fdt_high: '0xFFFFFFFF'\nfat_size: 16\n")

    def test_read_from_file(self):
        conf = self.config.from_file(StringIO(self.fake_hwpack))
        expected = {'format': 3.0, 'dtb_name': 'a_name',
                    'fdt_high': '0xFFFFFFFF', 'fat_size': 16}
        self.assertEqual(expected, conf)

    def test_android_specific_args(self):
        """The field android_specific_args should be a concatenated string."""
        specific_args = ("android_specific_args:\n - init=/init\n "
                         "- androidboot.console=ttyO2")
        hwpack_config = self.hwpack_base + specific_args
        self.config.from_file(StringIO(hwpack_config))
        expected = 'init=/init androidboot.console=ttyO2'
        self.assertEqual(expected, self.config.android_specific_args)

    def test_extra_serial_opts(self):
        """The field extra_serial_opts should be a concatenated string."""
        extra_serial_opts = ("extra_serial_opts:\n - console=tty0\n "
                             "- console=ttyO2,115200n8")
        hwpack_config = self.hwpack_base + extra_serial_opts
        self.config.from_file(StringIO(hwpack_config))
        expected = 'console=tty0 console=ttyO2,115200n8'
        self.assertEqual(expected, self.config.extra_serial_opts)

    def test_extra_boot_args_options(self):
        """The field extra_boot_args_options should be a concatenated string.
        Testing presence of a field defined in the parent class."""
        extra_boot_args_options = ("extra_boot_args_options:\n "
                                   "- earlyprintk\n - mem=128M@0\n "
                                   "- mali.mali_mem=64M@128M\n")
        hwpack_config = self.hwpack_base + extra_boot_args_options
        self.config.from_file(StringIO(hwpack_config))
        expected = 'earlyprintk mem=128M@0 mali.mali_mem=64M@128M'
        self.assertEqual(expected, self.config.extra_boot_args_options)

    def test_android_mx6(self):
        android_mx6_config = (self.hwpack_base + "bootloader_flavor: "
            "mx6qsabrelite\nextra_boot_args_options:\n - earlyprintk\n"
            " - rootdelay=1\n - fixrtc\n - nocompcache\n - di1_primary\n"
            " - tve\nextra_serial_opts:\n - console=%s,115200n8\n"
            "android_specific_args:\n - init=/init\n - "
            "androidboot.console=%s\nkernel_addr: '0x10000000'\n"
            "initrd_addr: '0x12000000'\nload_addr: '0x10008000'\ndtb_addr:"
            " '0x11ff0000'\ndtb_name: board.dtb")
        expected = {
            'bootargs': 'console=ttymxc0,115200n8 '
                        'rootwait ro earlyprintk rootdelay=1 fixrtc '
                        'nocompcache di1_primary tve init=/init '
                        'androidboot.console=ttymxc0',
            'bootcmd': 'fatload mmc 0:2 0x10000000 uImage; '
                       'fatload mmc 0:2 0x12000000 uInitrd; '
                       'fatload mmc 0:2 0x11ff0000 board.dtb; '
                       'bootm 0x10000000 0x12000000 0x11ff0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        config = get_board_config('mx6qsabrelite')
        config.from_file(StringIO(android_mx6_config))
        self.assertBootEnv(config, expected)

    def test_panda(self):
        panda_config = (self.hwpack_base + "bootloader_flavor: omap4_panda\n"
                        "dtb_addr: '0x815f0000'\ndtb_name: board.dtb\n"
                        "extra_serial_opts:\n - console=ttyO2,115200n8\n"
                        "extra_boot_args_options:\n - earlyprintk\n"
                        " - fixrtc\n - nocompcache\n - vram=48M\n"
                        " - omapfb.vram=0:24M,1:24M\n - mem=456M@0x80000000\n"
                        " - mem=512M@0xA0000000\nandroid_specific_args:\n"
                        " - init=/init\n - androidboot.console=ttyO2")
        # XXX: To fix bug 697824 we have to change class attributes of our
        # OMAP board configs, and some tests do that so to make sure they
        # don't interfere with us we'll reset that before doing anything.
        config = get_board_config('panda')
        config.from_file(StringIO(panda_config))
        expected = {
            'bootargs': 'console=ttyO2,115200n8 '
                        'rootwait ro earlyprintk fixrtc '
                        'nocompcache vram=48M omapfb.vram=0:24M,1:24M '
                        'mem=456M@0x80000000 mem=512M@0xA0000000 '
                        'init=/init androidboot.console=ttyO2',
            'bootcmd': 'fatload mmc 0:1 0x80200000 uImage; '
                       'fatload mmc 0:1 0x81600000 uInitrd; '
                       'fatload mmc 0:1 0x815f0000 board.dtb; '
                       'bootm 0x80200000 0x81600000 0x815f0000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertBootEnv(config, expected)

    def test_android_snowball_sd(self):
        snowball_config = (self.hwpack_base + "boot_script: boot.scr\n"
            "fdt_high: '0x05000000'\ninitrd_addr: '0x05000000'\n"
            "initrd_high: '0x06000000'\nextra_boot_args_options:\n "
            "- earlyprintk\n - mem=128M@0\n - mali.mali_mem=64M@128M\n "
            "- hwmem=168M@192M\n - mem=22M@360M\n - mem_issw=1M@383M\n "
            "- mem=640M@384M\n - vmalloc=500M\nextra_serial_opts:\n"
            " - console=ttyAMA2,115200n8\nandroid_specific_args:\n "
            "- init=/init\n - androidboot.console=ttyAMA2\n"
            "dtb_name: board.dtb\ndtb_addr: '0x8000000'")
        config = get_board_config('snowball_sd')
        config.from_file(StringIO(snowball_config))
        expected = {
            'bootargs': 'console=ttyAMA2,115200n8 '
                        'rootwait ro earlyprintk '
                        'mem=128M@0 mali.mali_mem=64M@128M hwmem=168M@192M '
                        'mem=22M@360M mem_issw=1M@383M mem=640M@384M '
                        'vmalloc=500M init=/init androidboot.console=ttyAMA2',
            'bootcmd': 'fatload mmc 1:1 0x00100000 uImage; '
                       'fatload mmc 1:1 0x05000000 uInitrd; '
                       'fatload mmc 1:1 0x8000000 board.dtb; '
                       'bootm 0x00100000 0x05000000 0x8000000',
            'fdt_high': '0x05000000',
            'initrd_high': '0x06000000'}
        self.assertBootEnv(config, expected)

    def test_android_snowball_emmc(self):
        snowball_config = (self.hwpack_base + "boot_script: boot.scr\n"
            "fdt_high: '0x05000000'\ninitrd_addr: '0x05000000'\n"
            "initrd_high: '0x06000000'\nextra_boot_args_options:\n "
            "- earlyprintk\n - mem=128M@0\n - mali.mali_mem=64M@128M\n "
            "- hwmem=168M@192M\n - mem=22M@360M\n - mem_issw=1M@383M\n "
            "- mem=640M@384M\n - vmalloc=500M\nextra_serial_opts:\n"
            " - console=ttyAMA2,115200n8\nandroid_specific_args:\n "
            "- init=/init\n - androidboot.console=ttyAMA2\n"
            "dtb_name: board.dtb\ndtb_addr: '0x8000000'\nmmc_option: '0:2'")
        config = get_board_config('snowball_emmc')
        config.from_file(StringIO(snowball_config))
        expected = {
            'bootargs': 'console=ttyAMA2,115200n8 '
                        'rootwait ro earlyprintk '
                        'mem=128M@0 mali.mali_mem=64M@128M hwmem=168M@192M '
                        'mem=22M@360M mem_issw=1M@383M mem=640M@384M '
                        'vmalloc=500M init=/init androidboot.console=ttyAMA2',
            'bootcmd': 'fatload mmc 0:2 0x00100000 uImage; '
                       'fatload mmc 0:2 0x05000000 uInitrd; '
                       'fatload mmc 0:2 0x8000000 board.dtb; '
                       'bootm 0x00100000 0x05000000 0x8000000',
            'fdt_high': '0x05000000',
            'initrd_high': '0x06000000'}
        self.assertBootEnv(config, expected)

    def test_android_origen(self):
        origen_config = (self.hwpack_base + "extra_serial_opts:\n "
            "- console=tty0\n - console=ttySAC2,115200n8\n"
            "android_specific_args:\n - init=/init\n "
            "- androidboot.console=ttySAC2")
        config = get_board_config('origen')
        config.from_file(StringIO(origen_config))
        expected = {
            'bootargs': 'console=tty0 console=ttySAC2,115200n8 '
                        'rootwait ro init=/init androidboot.console=ttySAC2',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
                       'fatload mmc 0:2 0x42000000 uInitrd; '
                       'bootm 0x40007000 0x42000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertBootEnv(config, expected)

    def test_android_vexpress(self):
        vexpress_config = (self.hwpack_base + "extra_serial_opts:\n "
            "- console=tty0\n - console=ttyAMA0,38400n8\n"
            "android_specific_args:\n - init=/init\n "
            "- androidboot.console=ttyAMA0")
        config = get_board_config('vexpress')
        config.from_file(StringIO(vexpress_config))
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA0,38400n8 '
                        'rootwait ro init=/init androidboot.console=ttyAMA0',
            'bootcmd': 'fatload mmc 0:1 0x60000000 uImage; '
                       'fatload mmc 0:1 0x62000000 uInitrd; '
                       'bootm 0x60000000 0x62000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertBootEnv(config, expected)

    def test_android_mx5(self):
        mx5_config = (self.hwpack_base + "extra_boot_args_options:\n "
            "- earlyprintk\n - rootdelay=1\n - fixrtc\n - nocompcache\n "
            "- di1_primary\n - tve\nextra_serial_opts:\n"
            " - console=%s,115200n8\nandroid_specific_args:\n "
            "- init=/init\n - androidboot.console=%s")
        config = get_board_config('mx53loco')
        config.from_file(mx5_config)
        expected = {
            'bootargs': 'console=ttymxc0,115200n8 '
                        'rootwait ro earlyprintk rootdelay=1 fixrtc '
                        'nocompcache di1_primary tve init=/init '
                        'androidboot.console=ttymxc0',
            'bootcmd': 'fatload mmc 0:2 0x70000000 uImage; '
                       'fatload mmc 0:2 0x72000000 uInitrd; '
                       'bootm 0x70000000 0x72000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertBootEnv(config, expected)

    def assertBootEnv(self, config, expected):
        self.assertEqual(expected, config._get_boot_env(consoles=[]))

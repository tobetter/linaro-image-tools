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

from testtools import TestCase

from linaro_image_tools.media_create.boards import (
    BoardConfigException,
)

from linaro_image_tools.media_create.android_boards import (
    AndroidBeagleConfig,
    get_board_config,
)

from linaro_image_tools.testing import TestCaseWithFixtures
from linaro_image_tools.tests.fixtures import CreateTempFileFixture


class TestAndroidBoards(TestCase):
    """Class to test small things in android_boards."""

    def test_get_board_config(self):
        instance = get_board_config('beagle')
        self.assertIsInstance(instance, AndroidBeagleConfig)

    def test_get_board_config_wrong(self):
        self.assertRaises(BoardConfigException, get_board_config, 'notadevice')

    def test_hwpack_not_exists(self):
        instance = get_board_config('beagle')
        self.assertRaises(BoardConfigException, instance.from_file, 'a_file')


class TestAndroidBoardsHwpack(TestCaseWithFixtures):
    """Class to test the new Android hwpack configuration file."""

    # All the necessary Android hwpack fields for the tests.
    hwpack_format = 'format: 3.0\n'
    hwpack_dtb_name = 'dtb_name: %(dtb_name)s\n'
    hwpack_fdt_high = "fdt_high: '%(fdt_high)s'\n"
    hwpack_fat_size = 'fat_size: 16\n'
    hwpack_android_args = 'android_specific_args: %(android_specific_args)s\n'
    hwpack_extra_serial = 'extra_serial_options: %(extra_serial_options)s\n'
    hwpack_extra_boot = ('extra_boot_args_options: '
                         '%(extra_boot_args_options)s\n')
    hwpack_bootloader_flavor = 'bootloader_flavor: %(bootloader_flavor)s\n'
    hwpack_initrd_addr = 'initrd_addr: \'%(initrd_addr)s\'\n'
    hwpack_initrd_high = 'initrd_high: \'%(initrd_high)s\'\n'
    hwpack_kernel_addr = 'kernel_addr: \'%(kernel_addr)s\'\n'
    hwpack_load_addr = 'load_addr: \'%(load_addr)s\'\n'
    hwpack_dtb_addr = 'dtb_addr: \'%(dtb_addr)s\'\n'
    hwpack_boot_script = 'boot_script: %(boot_script)s\n'
    hwpack_mmc_option = 'mmc_option: \'%(mmc_option)s\'\n'

    # Some defaults YAML-like strings to use for the tests.
    android_hwpack_base = (hwpack_format + hwpack_dtb_name)
    android_hwpack_simple = (android_hwpack_base + hwpack_fdt_high +
                             hwpack_fat_size)
    android_hwpack_android_args = (android_hwpack_base + hwpack_android_args)
    android_hwpack_extra_serial = (android_hwpack_base + hwpack_extra_serial)
    android_hwpack_extra_boot = (android_hwpack_base + hwpack_extra_boot)

    android_hwpack_panda = (
        hwpack_format + hwpack_android_args + hwpack_bootloader_flavor +
        hwpack_dtb_addr + hwpack_dtb_name + hwpack_extra_boot +
        hwpack_extra_serial
    )

    android_hwpack_mx6 = (
        android_hwpack_panda + hwpack_initrd_addr + hwpack_kernel_addr +
        hwpack_load_addr
    )

    android_hwpack_snowball_sd = (
        hwpack_android_args + hwpack_boot_script + hwpack_dtb_addr +
        hwpack_dtb_name + hwpack_extra_boot + hwpack_extra_serial +
        hwpack_fdt_high + hwpack_format + hwpack_initrd_addr
    )

    android_hwpack_snowball_emmc = (
        android_hwpack_snowball_sd + hwpack_initrd_high + hwpack_mmc_option)

    def setUp(self):
        super(TestAndroidBoardsHwpack, self).setUp()
        # Pick a default board.
        self.config = get_board_config('beagle')

    def _get_tmp_file_name(self, content=None):
        name = self.useFixture(CreateTempFileFixture(content)).get_file_name()
        return name

    def assertBootEnv(self, expected, config=None, board='beagle'):
        """Helper function the boot env parameters.

        :param config: The string containing the YAML configuration.
        :type str
        :param expected: The expected configuration.
        :type dict
        :param board: The name of the board to test. Defaults to beagle.
        :type str
        """
        board_conf = get_board_config(board)
        if config:
            name = self.useFixture(CreateTempFileFixture(config)).\
                get_file_name()
            board_conf.from_file(name)
        self.assertEqual(expected, board_conf._get_boot_env(consoles=[]))

    def test_read_from_file(self):
        values = {'fdt_high': '0xFFFFFFFF', 'dtb_name': 'a_name'}
        expected = {'format': 3.0, 'dtb_name': 'a_name',
                    'fdt_high': '0xFFFFFFFF', 'fat_size': 16}
        yaml_conf = self.android_hwpack_simple % values
        name = self._get_tmp_file_name(yaml_conf)
        conf = self.config.from_file(name)
        self.assertEqual(expected, conf)

    def test_android_specific_args(self):
        """The field android_specific_args should be a concatenated string."""
        values = {'android_specific_args': ['init=/init',
                                            'androidboot.console=ttyO2'],
                  'dtb_name': 'a_name'}
        yaml_conf = self.android_hwpack_android_args % values
        name = self._get_tmp_file_name(yaml_conf)
        self.config.from_file(name)
        expected = 'init=/init androidboot.console=ttyO2'
        self.assertEqual(expected, self.config.android_specific_args)

    def test_extra_serial_options(self):
        """The field extra_serial_options should be a concatenated string."""
        values = {'dtb_name': 'a_name',
                  'extra_serial_options': ['console=tty0',
                                           'console=ttyO2,115200n8']}
        yaml_conf = self.android_hwpack_extra_serial % values
        name = self._get_tmp_file_name(yaml_conf)
        self.config.from_file(name)
        expected = 'console=tty0 console=ttyO2,115200n8'
        self.assertEqual(expected, self.config.extra_serial_options)

    def test_extra_boot_args_options(self):
        """The field extra_boot_args_options should be a concatenated string.
        Testing presence of a field defined in the parent class."""
        values = {
            'dtb_name': 'a_name',
            'extra_boot_args_options': ['earlyprintk', 'mem=128M@0',
                                        'mali.mali_mem=64M@128M']
        }
        yaml_conf = self.android_hwpack_extra_boot % values
        name = self._get_tmp_file_name(yaml_conf)
        self.config.from_file(name)
        expected = 'earlyprintk mem=128M@0 mali.mali_mem=64M@128M'
        self.assertEqual(expected, self.config.extra_boot_args_options)

    def test_android_mx6(self):
        values = {
            "android_specific_args": ["init=/init", "androidboot.console=%s"],
            "bootloader_flavor": "mx6qsabrelite",
            "dtb_addr": '0x11ff0000',
            "dtb_name": "board.dtb",
            "extra_boot_args_options": ["earlyprintk", "rootdelay=1",
                                        "fixrtc", "nocompcache",
                                        "di1_primary", "tve"],
            "extra_serial_options": ["console=%s,115200n8"],
            "initrd_addr": '0x12000000',
            "kernel_addr": '0x10000000',
            "load_addr": '0x10008000',
        }
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
        config = self.android_hwpack_mx6 % values
        self.assertBootEnv(expected, config=config, board='mx6qsabrelite')

    def test_android_mx6_old(self):
        # Old test: use the values from the class, instead of passing them.
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
        self.assertBootEnv(expected, board='mx6qsabrelite')

    def test_panda(self):
        values = {
            "android_specific_args": ["init=/init",
                                      "androidboot.console=ttyO2"],
            "bootloader_flavor": "omap4_panda",
            "dtb_addr": '0x815f0000',
            "dtb_name": "board.dtb",
            "extra_boot_args_options": ["earlyprintk", "fixrtc",
                                        "nocompcache", "vram=48M",
                                        "omapfb.vram=0:24M,1:24M",
                                        "mem=456M@0x80000000",
                                        "mem=512M@0xA0000000"],
            "extra_serial_options": ["console=ttyO2,115200n8"],
        }
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
        config = self.android_hwpack_panda % values
        self.assertBootEnv(expected, config=config, board='panda')

    def test_panda_old(self):
        # Old test: use the values from the class, instead of passing them.
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
        self.assertBootEnv(expected, board='panda')

    def test_android_snowball_sd(self):
        values = {
            "android_specific_args": ["init=/init",
                                      "androidboot.console=ttyAMA2"],
            "boot_script": "boot.scr",
            "dtb_addr": '0x8000000',
            "dtb_name": "board.dtb",
            "extra_boot_args_options": ["earlyprintk", "mem=128M@0",
                                        "mali.mali_mem=64M@128M",
                                        "hwmem=168M@192M", "mem=22M@360M",
                                        "mem_issw=1M@383M", "mem=640M@384M",
                                        "vmalloc=500M"],
            "extra_serial_options": ["console=ttyAMA2,115200n8"],
            "fdt_high": '0x05000000',
            "initrd_addr": '0x05000000',
            "initrd_high": '0x06000000',
        }
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
        config = self.android_hwpack_snowball_sd % values
        self.assertBootEnv(expected, config=config, board='snowball_sd')

    def test_android_snowball_sd_old(self):
        # Old test: use the values from the class, instead of passing them.
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
        self.assertBootEnv(expected, board='snowball_sd')

    def test_android_snowball_emmc(self):
        values = {
            "android_specific_args": ["init=/init",
                                      "androidboot.console=ttyAMA2"],
            "boot_script": "boot.scr",
            "dtb_addr": '0x8000000',
            "dtb_name": "board.dtb",
            "extra_boot_args_options": ["earlyprintk", "mem=128M@0",
                                        "mali.mali_mem=64M@128M",
                                        "hwmem=168M@192M", "mem=22M@360M",
                                        "mem_issw=1M@383M", "mem=640M@384M",
                                        "vmalloc=500M"],
            "extra_serial_options": ["console=ttyAMA2,115200n8"],
            "fdt_high": '0x05000000',
            "initrd_addr": '0x05000000',
            "initrd_high": '0x06000000',
            "mmc_option": '0:2'
        }
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
        config = self.android_hwpack_snowball_emmc % values
        self.assertBootEnv(expected, config, board='snowball_emmc')

    def test_android_snowball_emmc_old(self):
        # Old test: use the values from the class, instead of passing them.
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
        self.assertBootEnv(expected, board='snowball_emmc')

    def test_android_origen(self):
        values = {
            "extra_serial_options": ["console=tty0",
                                     "console=ttySAC2,115200n8"],
            "android_specific_args": ["init=/init",
                                      "androidboot.console=ttySAC2"]
        }
        expected = {
            'bootargs': 'console=tty0 console=ttySAC2,115200n8 '
                        'rootwait ro init=/init androidboot.console=ttySAC2',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
                       'fatload mmc 0:2 0x42000000 uInitrd; '
                       'bootm 0x40007000 0x42000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        config = ((self.hwpack_format + self.hwpack_extra_serial +
                   self.hwpack_android_args) % values)
        self.assertBootEnv(expected, config=config, board='origen')

    def test_android_origen_old(self):
        # Old test: use the values from the class, instead of passing them.
        expected = {
            'bootargs': 'console=tty0 console=ttySAC2,115200n8 '
                        'rootwait ro init=/init androidboot.console=ttySAC2',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
                       'fatload mmc 0:2 0x42000000 uInitrd; '
                       'bootm 0x40007000 0x42000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertBootEnv(expected, board='origen')

    def test_android_origen_quad(self):
        values = {
            "extra_serial_options": ["console=tty0",
                                     "console=ttySAC2,115200n8"],
            "android_specific_args": ["init=/init",
                                      "androidboot.console=ttySAC2"]
        }
        expected = {
            'bootargs': 'console=tty0 console=ttySAC2,115200n8 '
                        'rootwait ro init=/init androidboot.console=ttySAC2',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
                       'fatload mmc 0:2 0x42000000 uInitrd; '
                       'bootm 0x40007000 0x42000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        config = ((self.hwpack_format + self.hwpack_extra_serial +
                   self.hwpack_android_args) % values)
        self.assertBootEnv(expected, config=config, board='origen_quad')

    def test_android_origen_quad_old(self):
        # Old test: use the values from the class, instead of passing them.
        expected = {
            'bootargs': 'console=tty0 console=ttySAC2,115200n8 '
                        'rootwait ro init=/init androidboot.console=ttySAC2',
            'bootcmd': 'fatload mmc 0:2 0x40007000 uImage; '
                       'fatload mmc 0:2 0x42000000 uInitrd; '
                       'bootm 0x40007000 0x42000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertBootEnv(expected, board='origen_quad')

    def test_android_vexpress(self):
        values = {
            "extra_serial_options": ["console=tty0",
                                     "console=ttyAMA0,38400n8"],
            "android_specific_args": ["init=/init",
                                      "androidboot.console=ttyAMA0"]
        }
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA0,38400n8 '
                        'rootwait ro init=/init androidboot.console=ttyAMA0',
            'bootcmd': 'fatload mmc 0:1 0x60000000 uImage; '
                       'fatload mmc 0:1 0x62000000 uInitrd; '
                       'bootm 0x60000000 0x62000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        config = ((self.hwpack_format + self.hwpack_extra_serial +
                   self.hwpack_android_args) % values)
        self.assertBootEnv(expected, config=config, board='vexpress')

    def test_android_vexpress_old(self):
        # Old test: use the values from the class, instead of passing them.
        expected = {
            'bootargs': 'console=tty0 console=ttyAMA0,38400n8 '
                        'rootwait ro init=/init androidboot.console=ttyAMA0',
            'bootcmd': 'fatload mmc 0:1 0x60000000 uImage; '
                       'fatload mmc 0:1 0x62000000 uInitrd; '
                       'bootm 0x60000000 0x62000000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff'}
        self.assertBootEnv(expected, board='vexpress')

    def test_android_mx5(self):
        values = {
            "extra_boot_args_options": ["earlyprintk", "rootdelay=1",
                                        "fixrtc", "nocompcache",
                                        "di1_primary", "tve"],
            "extra_serial_options": ["console=%s,115200n8"],
            "android_specific_args": ["init=/init", "androidboot.console=%s"]
        }
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
        config = ((self.hwpack_format + self.hwpack_extra_boot +
                   self.hwpack_extra_serial + self.hwpack_android_args) %
                  values)
        self.assertBootEnv(expected, config=config, board='mx53loco')

    def test_android_mx5_old(self):
        # Old test: use the values from the class, instead of passing them.
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
        self.assertBootEnv(expected, board='mx53loco')

    def test_android_arndale_old(self):
        """Test that uses values taken directly from the class. """
        expected = {
            'bootargs': 'ttySAC2,115200n8 rootwait ro rootdelay=3 '
                        'init=/init androidboot.console=ttySAC2 '
                        'console=ttySAC2 initrd=0x41000000',
            'bootcmd': 'fatload mmc 0:1 0x40007000 uImage; fatload mmc 0:1 '
                       '0x41000000 uInitrd; fatload mmc 0:1 0x41f00000 '
                       'exynos5250-arndale.dtb; bootm 0x40007000 0x41000000 '
                       '0x41f00000',
            'fdt_high': '0xffffffff',
            'initrd_high': '0xffffffff',
        }
        self.assertBootEnv(expected, board='arndale')

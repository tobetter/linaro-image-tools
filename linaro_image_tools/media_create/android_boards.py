# Copyright (C) 2011 Linaro
#
# Author: Jeremy Chang <jeremy.chang@linaro.org>
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
# along with Linaro Image Tools.  If not, see <http://www.gnu.org/licenses/>.

"""Configuration for boards supported by linaro-android-media-create.

To add support for a new board, you need to create a subclass of
AndroidBoardConfig, create an Android hwpack as explained here:

https://wiki.linaro.org/AndroidHardwarePacksV3

and add the board to 'android_board_configs' at the end of this file.
"""

import os
import yaml
import logging

from linaro_image_tools import cmd_runner
from linaro_image_tools.hwpack.hwpack_fields import FORMAT_FIELD
from linaro_image_tools.media_create.partitions import SECTOR_SIZE
from linaro_image_tools.media_create.boards import (
    ArndaleConfig,
    ArndaleOctaConfig,
    BeagleConfig,
    BoardConfig,
    BoardConfigException,
    Mx53LoCoConfig,
    OrigenConfig,
    OrigenQuadConfig,
    PART_ALIGN_S,
    PandaConfig,
    SMDKV310Config,
    SnowballEmmcConfig,
    SnowballSdConfig,
    VexpressConfig,
    align_partition,
    align_up,
    install_mx5_boot_loader,
    make_boot_script,
    _dd,
    BoardException,
)
from linaro_image_tools.utils import DEFAULT_LOGGER_NAME

logger = logging.getLogger(DEFAULT_LOGGER_NAME)

BOOT_MIN_SIZE_S = align_up(128 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
SYSTEM_MIN_SIZE_S = align_up(768 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
CACHE_MIN_SIZE_S = align_up(256 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
USERDATA_MIN_SIZE_S = align_up(576 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
SDCARD_MIN_SIZE_S = align_up(256 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
LOADER_MIN_SIZE_S = align_up(1 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE


class AndroidBoardConfig(BoardConfig):

    def __init__(self):
        super(AndroidBoardConfig, self).__init__()
        self.dtb_name = None
        self._extra_serial_options = []
        self._android_specific_args = []
        self._extra_boot_args_options = []
        self._live_serial_options = []

    def _get_android_specific_args(self):
        android_args = self._android_specific_args
        if isinstance(android_args, list):
            android_args = ' '.join(self._android_specific_args)
        return android_args

    def _set_android_specific_args(self, value):
        self._android_specific_args = value

    android_specific_args = property(_get_android_specific_args,
                                     _set_android_specific_args)

    def _get_extra_boot_args_options(self):
        extra_boot_args = self._extra_boot_args_options
        if isinstance(extra_boot_args, list):
            extra_boot_args = ' '.join(self._extra_boot_args_options)
        return extra_boot_args

    def _set_extra_boot_args_options(self, value):
        self._extra_boot_args_options = value

    extra_boot_args_options = property(_get_extra_boot_args_options,
                                       _set_extra_boot_args_options)

    def _get_extra_serial_options(self):
        extra_serial = self._extra_serial_options
        if isinstance(extra_serial, list):
            extra_serial = ' '.join(self._extra_serial_options)
        return extra_serial

    def _set_extra_serial_options(self, value):
        self._extra_serial_options = value

    extra_serial_options = property(_get_extra_serial_options,
                                    _set_extra_serial_options)

    def _get_live_serial_options(self):
        serial_options = self._live_serial_options
        if serial_options:
            if isinstance(serial_options, list):
                serial_options = ' '.join(self._live_serial_options)
            if self._check_placeholder_presence(serial_options, '%s'):
                serial_options = serial_options % self.serial_tty
        return serial_options

    def _set_live_serial_options(self, value):
        self._live_serial_options = value

    live_serial_options = property(_get_live_serial_options,
                                   _set_live_serial_options)

    def from_file(self, hwpack):
        """Loads the Android board configuration from an Android hardware pack
        configuration file and sets the config attributes with their values.

        :param hwpack: The Android hwpack configuration file.
        :return The configuration read from the file as a dictionary.
        """
        try:
            with open(hwpack, 'r') as hw:
                config = yaml.safe_load(hw)
            self._set_attributes(config)
            return config
        except yaml.YAMLError, ex:
            logger.debug("Error loading YAML file %s" % hwpack, ex)
            raise BoardConfigException("Error reading Android hwpack %s"
                                       % hwpack)
        except IOError, ex:
            logger.debug("Error reading hwpack file %s" % hwpack, ex)
            raise BoardConfigException("Android hwpack %s could not be found"
                                       % hwpack)

    def _set_attributes(self, config):
        """Initialize the class attributes with the values read from the
        Android hardware pack configuration file.

        :param config: The config read from the Android hwpack.
        """
        for name, value in config.iteritems():
            if name == FORMAT_FIELD:
                setattr(self, 'hwpack_format', value)
            elif hasattr(self, name):
                setattr(self, name, value)
            else:
                logger.warning("Attribute '%s' does not belong to this "
                               "instance of '%s'." % (name, self.__class__))

    def _get_bootargs(self, consoles):
        """Get the bootargs for this board.

        In general subclasses should not have to override this.
        """
        boot_args_options = 'rootwait ro'
        if self.extra_boot_args_options:
            boot_args_options += ' %s' % self.extra_boot_args_options
        boot_args_options += ' %s' % self.android_specific_args
        serial_options = self.extra_serial_options
        for console in consoles:
            serial_options += ' console=%s' % console

        replacements = dict(
            serial_options=serial_options,
            boot_args_options=boot_args_options)
        return (
            "%(serial_options)s "
            "%(boot_args_options)s"
            % replacements).strip()

    def _get_boot_env(self, consoles):
        """Get the boot environment for this board.

        In general subclasses should not have to override this.
        """
        boot_env = {}
        boot_env["bootargs"] = self._get_bootargs(consoles)
        initrd = False
        if self.initrd_addr:
            initrd = True
        # On Android, the DTB file is always built as part of the kernel it
        # comes from - and lives in the same directory in the boot tarball, so
        # here we don't need to pass the whole path to it.
        boot_env["bootcmd"] = self._get_bootcmd(initrd, self.dtb_name)
        boot_env["initrd_high"] = self.initrd_high
        boot_env["fdt_high"] = self.fdt_high
        return boot_env

    def populate_boot_script(self, boot_partition, boot_disk, consoles):
        cmd_runner.run(['mkdir', '-p', boot_disk]).wait()
        # TODO: Use partition_mounted() here to make sure the partition is
        # always umounted after we're done.
        cmd_runner.run(['mount', boot_partition, boot_disk],
                       as_root=True).wait()

        boot_env = self._get_boot_env(consoles)
        cmdline_filepath = os.path.join(boot_disk, "cmdline")

        with open(cmdline_filepath, 'r') as cmdline_file:
            android_kernel_cmdline = cmdline_file.read().strip()

        boot_env['bootargs'] = boot_env['bootargs'] + ' ' + \
            android_kernel_cmdline

        boot_dir = boot_disk
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)

        try:
            cmd_runner.run(['umount', boot_disk], as_root=True).wait()
        except cmd_runner.SubcommandNonZeroReturnValue:
            pass

    def get_sfdisk_cmd(self, should_align_boot_part=False,
                       start_addr=0, extra_part=False):
        if self.fat_size == 32:
            partition_type = '0x0C'
        else:
            partition_type = '0x0E'

        # align on sector 63 for compatibility with broken versions of x-loader
        # unless align_boot_part is set
        boot_align = 63
        if should_align_boot_part:
            boot_align = PART_ALIGN_S

        # can only start on sector 1 (sector 0 is MBR / partition table)
        boot_start, boot_end, boot_len = align_partition(
            start_addr + 1, BOOT_MIN_SIZE_S, boot_align, PART_ALIGN_S)
        # apparently OMAP3 ROMs require the vfat length to be an even number
        # of sectors (multiple of 1 KiB); decrease the length if it's odd,
        # there should still be enough room
        boot_len = boot_len - boot_len % 2
        boot_end = boot_start + boot_len - 1

        system_start, _system_end, _system_len = align_partition(
            boot_end + 1, SYSTEM_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        cache_start, _cache_end, _cache_len = align_partition(
            _system_end + 1, CACHE_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        userdata_start, _userdata_end, _userdata_len = align_partition(
            _cache_end + 1, USERDATA_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        sdcard_start, _sdcard_end, _sdcard_len = align_partition(
            _userdata_end + 1, SDCARD_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        # Snowball board needs a raw partition added to the beginning of image.
        # If extra_part is True an extra primary partition will be added.
        # Due to a maximum of 4 primary partitions cache data will be placed in
        # a extended partition
        if extra_part is True:
            assert start_addr > 0, ("Not possible to add extra partition"
                                    "when boot partition starts at '0'")
            return '%s,%s,%s,*\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,%s,L\n%s,,,-' % (
                boot_start, boot_len, partition_type, system_start,
                _system_len, cache_start, cache_start, _cache_len,
                userdata_start, _userdata_len, sdcard_start)

        return '%s,%s,%s,*\n%s,%s,L\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,,,-' % (
            boot_start, boot_len, partition_type, system_start, _system_len,
            cache_start, _cache_len, userdata_start, userdata_start,
            _userdata_len, sdcard_start)

    def populate_raw_partition(self, media, boot_dir):
        super(AndroidBoardConfig, self).populate_raw_partition(media, boot_dir)

    def install_boot_loader(self, boot_partition, boot_device_or_file):
        pass


class AndroidOmapConfig(AndroidBoardConfig):
    """Placeholder class for OMAP configuration inheritance."""


class AndroidBeagleConfig(AndroidOmapConfig, BeagleConfig):
    """Placeholder class for Beagle configuration inheritance."""
    def __init__(self):
        super(AndroidBeagleConfig, self).__init__()
        self._android_specific_args = 'init=/init androidboot.console=ttyO2'
        self._extra_serial_options = 'console=tty0 console=ttyO2,115200n8'


class AndroidPandaConfig(AndroidBoardConfig, PandaConfig):
    """Placeholder class for Panda configuration inheritance."""
    def __init__(self):
        super(AndroidPandaConfig, self).__init__()
        self.dtb_name = 'board.dtb'
        self._extra_serial_options = 'console=ttyO2,115200n8'
        self._extra_boot_args_options = (
            'earlyprintk fixrtc nocompcache vram=48M '
            'omapfb.vram=0:24M,1:24M mem=456M@0x80000000 mem=512M@0xA0000000')
        self._android_specific_args = 'init=/init androidboot.console=ttyO2'
        self.dtb_addr = '0x815f0000'
        self.bootloader_flavor = 'omap4_panda'


class AndroidSnowballSdConfig(AndroidBoardConfig, SnowballSdConfig):
    """Placeholder class for Snowball Sd configuration inheritance."""
    def __init__(self):
        super(AndroidSnowballSdConfig, self).__init__()
        self.dtb_name = 'board.dtb'
        self._android_specific_args = 'init=/init androidboot.console=ttyAMA2'
        self._extra_boot_args_options = (
            'earlyprintk mem=128M@0 mali.mali_mem=64M@128M hwmem=168M@192M '
            'mem=22M@360M mem_issw=1M@383M mem=640M@384M vmalloc=500M')
        self._extra_serial_options = 'console=ttyAMA2,115200n8'
        self.boot_script = 'boot.scr'
        self.fdt_high = '0x05000000'
        self.initrd_addr = '0x05000000'
        self.initrd_high = '0x06000000'
        self.dtb_addr = '0x8000000'


class AndroidSnowballEmmcConfig(AndroidBoardConfig, SnowballEmmcConfig):
    """Class for Snowball Emmc configuration inheritance."""
    def __init__(self):
        super(AndroidSnowballEmmcConfig, self).__init__()
        self.dtb_name = 'board.dtb'
        self._extra_boot_args_options = (
            'earlyprintk mem=128M@0 mali.mali_mem=64M@128M hwmem=168M@192M '
            'mem=22M@360M mem_issw=1M@383M mem=640M@384M vmalloc=500M')
        self._extra_serial_options = 'console=ttyAMA2,115200n8'
        self._android_specific_args = 'init=/init androidboot.console=ttyAMA2'
        self.boot_script = 'boot.scr'
        self.fdt_high = '0x05000000'
        self.initrd_addr = '0x05000000'
        self.initrd_high = '0x06000000'
        self.mmc_option = '0:2'
        self.dtb_addr = '0x8000000'

    def get_sfdisk_cmd(self, should_align_boot_part=False):
        loader_start, loader_end, loader_len = align_partition(
            SnowballEmmcConfig.SNOWBALL_LOADER_START_S,
            LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        command = super(AndroidSnowballEmmcConfig, self).get_sfdisk_cmd(
            should_align_boot_part=True, start_addr=loader_end,
            extra_part=True)

        return '%s,%s,0xDA\n%s' % (
            loader_start, loader_len, command)

    def populate_raw_partition(self, media, boot_dir):
        # To avoid adding a Snowball specific command line option, we assume
        # that the user already has unpacked the startfiles to ./startupfiles
        config_files_dir = self.snowball_config(boot_dir)
        assert os.path.exists(config_files_dir), (
            "You need to unpack the Snowball startupfiles to the directory "
            "'startupfiles' in your current working directory. See "
            "igloocommunity.org for more information.")
        # We copy the u-boot files from the unpacked boot.tar.bz2
        # and put it with the startfiles.
        boot_files = ['u-boot.bin']
        for boot_file in boot_files:
            cmd_runner.run(['cp', os.path.join(boot_dir, 'boot', boot_file),
                            config_files_dir], as_root=True).wait()
        super(AndroidSnowballEmmcConfig, self).populate_raw_partition(
            media, boot_dir)

    def snowball_config(self, chroot_dir):
        # The user is expected to have unpacked the startupfiles to this subdir
        # of their working dir.
        return os.path.join('.', 'startupfiles')

    @property
    def delete_startupfiles(self):
        # The startupfiles will have been unpacked to the user's working dir
        # and should not be deleted after they have been installed.
        return False


class AndroidMx53LoCoConfig(AndroidBoardConfig, Mx53LoCoConfig):
    """Class for Mx53LoCo configuration inheritance."""
    def __init__(self):
        super(AndroidMx53LoCoConfig, self).__init__()
        self._extra_boot_args_options = (
            'earlyprintk rootdelay=1 fixrtc nocompcache di1_primary tve')
        self._extra_serial_options = 'console=%s,115200n8'
        self._android_specific_args = 'init=/init androidboot.console=%s'

    def _get_extra_serial_options(self):
        serial_options = self._extra_serial_options
        if serial_options:
            if isinstance(serial_options, list):
                serial_options = ' '.join(serial_options)
            if self._check_placeholder_presence(serial_options, '%s'):
                serial_options = serial_options % self.serial_tty
        return serial_options

    def _set_extra_serial_options(self, value):
        self._extra_serial_options = value

    extra_serial_options = property(_get_extra_serial_options,
                                    _set_extra_serial_options)

    def _get_android_specific_args(self):
        android_args = self._android_specific_args
        if android_args:
            if isinstance(android_args, list):
                android_args = ' '.join(android_args)
            if self._check_placeholder_presence(android_args, '%s'):
                android_args = android_args % self.serial_tty
        return android_args

    def _set_android_specific_args(self, value):
        self._android_specific_args = value

    android_specific_args = property(_get_android_specific_args,
                                     _set_android_specific_args)

    def get_sfdisk_cmd(self, should_align_boot_part=False):
        loader_start, loader_end, loader_len = align_partition(
            1, self.LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        command = super(AndroidMx53LoCoConfig, self).get_sfdisk_cmd(
            should_align_boot_part=True, start_addr=loader_end,
            extra_part=True)

        return '%s,%s,0xDA\n%s' % (
            loader_start, loader_len, command)

    def install_boot_loader(self, boot_partition, boot_device_or_file):
        install_mx5_boot_loader(
            os.path.join(boot_device_or_file, "u-boot.imx"),
            boot_partition, self.LOADER_MIN_SIZE_S)


class AndroidMx6QSabreliteConfig(AndroidMx53LoCoConfig):
    """Placeholder class for Mx6Q Sabrelite configuration inheritance."""
    def __init__(self):
        super(AndroidMx6QSabreliteConfig, self).__init__()
        self.dtb_name = 'board.dtb'
        self.bootloader_flavor = 'mx6qsabrelite'
        self.kernel_addr = '0x10000000'
        self.initrd_addr = '0x12000000'
        self.load_addr = '0x10008000'
        self.dtb_addr = '0x11ff0000'


class AndroidSamsungConfig(AndroidBoardConfig):
    def get_sfdisk_cmd(self, should_align_boot_part=False):
        loaders_min_len = (self.samsung_bl1_start + self.samsung_bl1_len +
                           self.samsung_bl2_len + self.samsung_env_len)

        loader_start, loader_end, loader_len = align_partition(
            1, loaders_min_len, 1, PART_ALIGN_S)

        command = super(AndroidSamsungConfig, self).get_sfdisk_cmd(
            should_align_boot_part=False, start_addr=loader_end,
            extra_part=True)

        return '%s,%s,0xDA\n%s' % (
            loader_start, loader_len, command)


class AndroidSMDKV310Config(AndroidSamsungConfig, SMDKV310Config):
    """Placeholder class for SMDKV310 configuration inheritance."""
    def __init__(self):
        super(AndroidSMDKV310Config, self).__init__()
        self._extra_serial_options = 'console=tty0 console=ttySAC1,115200n8'
        self._android_specific_args = 'init=/init androidboot.console=ttySAC1'


class AndroidOrigenConfig(AndroidSamsungConfig, OrigenConfig):
    """Placeholder class for Origen configuration inheritance."""
    def __init__(self):
        super(AndroidOrigenConfig, self).__init__()
        self._extra_serial_options = 'console=tty0 console=ttySAC2,115200n8'
        self._android_specific_args = 'init=/init androidboot.console=ttySAC2'


class AndroidOrigenQuadConfig(AndroidSamsungConfig, OrigenQuadConfig):
    def __init__(self):
        super(AndroidOrigenQuadConfig, self).__init__()
        self._extra_serial_options = 'console=tty0 console=ttySAC2,115200n8'
        self._android_specific_args = 'init=/init androidboot.console=ttySAC2'


class AndroidVexpressConfig(AndroidBoardConfig, VexpressConfig):
    """Placeholder class for Vexpress configuration inheritance."""
    def __init__(self):
        super(AndroidVexpressConfig, self).__init__()
        self._extra_serial_options = 'console=tty0 console=ttyAMA0,38400n8'
        self._android_specific_args = 'init=/init androidboot.console=ttyAMA0'


class AndroidArndaleConfig(AndroidSamsungConfig, ArndaleConfig):
    """Placeholder class for Arndale configuration inheritance."""
    def __init__(self):
        super(AndroidArndaleConfig, self).__init__()
        self.mmc_option = '0:1'
        self.kernel_addr = '0x40007000'
        self.initrd_addr = '0x41000000'
        self.dtb_addr = '0x41f00000'
        self.dtb_name = 'exynos5250-arndale.dtb'
        self._android_specific_args = (
            'init=/init androidboot.console=ttySAC2 console=ttySAC2 initrd=%s'
            % self.initrd_addr)
        self._extra_serial_options = 'ttySAC2,115200n8'
        self._extra_boot_args_options = 'rootdelay=3'

    def _get_bootcmd(self, i_img_data, d_img_data):
        """Get the bootcmd for this board.

        In general subclasses should not have to override this.
        """
        replacements = dict(
            fatload_command=self.fatload_command, uimage_path=self.uimage_path,
            mmc_option=self.mmc_option, kernel_addr=self.kernel_addr,
            initrd_addr=self.initrd_addr, dtb_addr=self.dtb_addr)
        boot_script = (
            ("%(fatload_command)s mmc %(mmc_option)s %(kernel_addr)s " +
             "%(uimage_path)suImage; ")) % replacements
        if i_img_data is not None:
            boot_script += (
                ("%(fatload_command)s mmc %(mmc_option)s %(initrd_addr)s " +
                 "%(uimage_path)suInitrd; ")) % replacements
            if d_img_data is not None:
                assert self.dtb_addr is not None, (
                    "Need a dtb_addr when passing d_img_data")
                boot_script += ("%(fatload_command)s mmc %(mmc_option)s "
                                "%(dtb_addr)s " % replacements)
                boot_script += "%s; " % d_img_data
        boot_script += (("bootm %(kernel_addr)s")) % replacements
        if i_img_data is not None:
            boot_script += ((" %(initrd_addr)s")) % replacements
            if d_img_data is not None:
                boot_script += ((" %(dtb_addr)s")) % replacements
        return boot_script

    def populate_raw_partition(self, boot_device_or_file, chroot_dir):
        boot_bin_0 = {'name': 'arndale-bl1.bin', 'seek': 1}
        boot_bin_1 = {'name': 'u-boot-mmc-spl.bin', 'seek': 17}
        boot_bin_2 = {'name': 'u-boot.bin', 'seek': 49}
        boot_bins = [boot_bin_0, boot_bin_1, boot_bin_2]

        boot_partition = 'boot'

        # Zero the env so that the boot_script will get loaded
        _dd("/dev/zero", boot_device_or_file, count=self.samsung_env_len,
            seek=self.samsung_env_start)

        for boot_bin in boot_bins:
            name = boot_bin['name']
            file_path = os.path.join(chroot_dir, boot_partition, name)
            if not os.path.exists(file_path):
                raise BoardException(
                    "File '%s' does not exists. Cannot proceed." % name)
            _dd(file_path, boot_device_or_file, seek=boot_bin['seek'])


class AndroidArndaleOctaConfig(AndroidArndaleConfig, ArndaleOctaConfig):
    """Placeholder class for Arndale-Octa configuration inheritance."""
    def __init__(self):
        super(AndroidArndaleOctaConfig, self).__init__()
        self.samsung_env_start = 1231
        self.mmc_option = '0:2'
        self.kernel_addr = '0x20007000'
        self.initrd_addr = '0x21000000'
        self.dtb_addr = '0x21f00000'
        self.dtb_name = 'exynos5420-arndale-octa.dtb'
        self._android_specific_args = (
            'init=/init androidboot.console=ttySAC3 console=ttySAC3 initrd=%s'
            % self.initrd_addr)
        self._extra_serial_options = 'ttySAC3,115200n8'
        self._extra_boot_args_options = 'rootdelay=3'

    def populate_raw_partition(self, boot_device_or_file, chroot_dir):
        boot_bin_0 = {'name': 'arndale-octa.bl1.bin', 'seek': 1}
        boot_bin_1 = {'name': 'smdk5420-spl.signed.bin', 'seek': 31}
        boot_bin_2 = {'name': 'u-boot.bin', 'seek': 63}
        boot_bin_3 = {'name': 'arndale-octa.tzsw.bin', 'seek': 719}
        boot_bins = [boot_bin_0, boot_bin_1, boot_bin_2, boot_bin_3]

        boot_partition = 'boot'

        # Zero the env so that the boot_script will get loaded
        _dd("/dev/zero", boot_device_or_file, count=self.samsung_env_len,
            seek=self.samsung_env_start)

        for boot_bin in boot_bins:
            name = boot_bin['name']
            file_path = os.path.join(chroot_dir, boot_partition, name)
            if not os.path.exists(file_path):
                raise BoardException(
                    "File '%s' does not exists. Cannot proceed." % name)
            _dd(file_path, boot_device_or_file, seek=boot_bin['seek'])

# This dictionary is composed as follows:
# <device_name>: <class>
# The <device_name> is the command line argument passed to l-a-m-c, the
# <class> is the corresponding config class in this file (not the instance).
# If a new device does not have special needs, it is possible to use the
# general AndroidBoardConfig class.
android_board_configs = {
    'arndale': AndroidArndaleConfig,
    'arndale_octa': AndroidArndaleOctaConfig,
    'beagle': AndroidBeagleConfig,
    'iMX53': AndroidMx53LoCoConfig,
    'mx53loco': AndroidMx53LoCoConfig,
    'mx6qsabrelite': AndroidMx6QSabreliteConfig,
    'origen': AndroidOrigenConfig,
    'origen_quad': AndroidOrigenQuadConfig,
    'panda': AndroidPandaConfig,
    'smdkv310': AndroidSMDKV310Config,
    'snowball_emmc': AndroidSnowballEmmcConfig,
    'snowball_sd': AndroidSnowballSdConfig,
    'vexpress': AndroidVexpressConfig,
    'vexpress-a9': AndroidVexpressConfig,
}


def get_board_config(board):
    """Get the board configuration for the specified board.

    :param board: The name of the board to get the configuration of.
    :type board: str
    """
    clazz = android_board_configs.get(board, None)
    if clazz:
        return clazz()
    else:
        raise BoardConfigException("Board name '%s' has no configuration "
                                   "available." % board)

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
AndroidBoardConfig, set appropriate values for its variables and add it to
android_board_configs at the bottom of this file.
"""

from linaro_image_tools.media_create.partitions import SECTOR_SIZE
from linaro_image_tools.media_create.boards import PART_ALIGN_S
from linaro_image_tools.media_create.boards import BeagleConfig
from linaro_image_tools.media_create.boards import PandaConfig
from linaro_image_tools.media_create.boards import Mx53LoCoConfig
from linaro_image_tools.media_create.boards import SnowballSdConfig
from linaro_image_tools.media_create.boards import SnowballEmmcConfig
from linaro_image_tools.media_create.boards import SMDKV310Config
from linaro_image_tools.media_create.boards import OrigenConfig
from linaro_image_tools.media_create.boards import VexpressConfig
from linaro_image_tools.media_create.boards import (
    align_up,
    align_partition,
    classproperty,
    make_boot_script,
    install_mx5_boot_loader,
    )

from linaro_image_tools import cmd_runner
import os


class AndroidBoardConfig(object):
    @classmethod
    def _get_bootargs(cls, consoles):
        """Get the bootargs for this board.

        In general subclasses should not have to override this.
        """
        boot_args_options = 'rootwait ro'
        if cls.extra_boot_args_options is not None:
            boot_args_options += ' %s' % cls.extra_boot_args_options
        boot_args_options += ' %s' % cls.android_specific_args
        serial_opts = cls._extra_serial_opts
        for console in consoles:
            serial_opts += ' console=%s' % console

        replacements = dict(
            serial_opts=serial_opts,
            boot_args_options=boot_args_options)
        return (
            "%(serial_opts)s "
            "%(boot_args_options)s"
             % replacements)

    @classmethod
    def _get_boot_env(cls, consoles):
        """Get the boot environment for this board.

        In general subclasses should not have to override this.
        """
        boot_env = {}
        boot_env["bootargs"] = cls._get_bootargs(consoles)
        # On Android, the DTB file is always built as part of the kernel it
        # comes from - and lives in the same directory in the boot tarball, so
        # here we don't need to pass the whole path to it.
        boot_env["bootcmd"] = cls._get_bootcmd(cls.dtb_name)
        return boot_env

    @classmethod
    def populate_boot_script(cls, boot_partition, boot_disk, consoles):
        cmd_runner.run(['mkdir', '-p', boot_disk]).wait()
        # TODO: Use partition_mounted() here to make sure the partition is
        # always umounted after we're done.
        cmd_runner.run(['mount', boot_partition, boot_disk],
            as_root=True).wait()

        boot_env = cls._get_boot_env(consoles)
        cmdline_filepath = os.path.join(boot_disk, "cmdline")
        cmdline_file = open(cmdline_filepath, 'r')
        android_kernel_cmdline = cmdline_file.read()
        boot_env['bootargs'] = boot_env['bootargs'] + ' ' + \
            android_kernel_cmdline
        cmdline_file.close()

        boot_dir = boot_disk
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)

        cmd_runner.run(['sync']).wait()
        try:
            cmd_runner.run(['umount', boot_disk], as_root=True).wait()
        except cmd_runner.SubcommandNonZeroReturnValue:
            pass

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False,
                       start_addr=0, extra_part=False):
        if cls.fat_size == 32:
            partition_type = '0x0C'
        else:
            partition_type = '0x0E'

        BOOT_MIN_SIZE_S = align_up(128 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
        SYSTEM_MIN_SIZE_S = align_up(512 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
        CACHE_MIN_SIZE_S = align_up(256 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
        USERDATA_MIN_SIZE_S = align_up(512 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
        SDCARD_MIN_SIZE_S = align_up(512 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE

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
        if extra_part == True:
            assert start_addr > 0, ("Not possible to add extra partition" \
                                    "when boot partition starts at '0'")
            return '%s,%s,%s,*\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,%s,L\n%s,,,-' % (
            boot_start, boot_len, partition_type, system_start, _system_len,
            cache_start, cache_start, _cache_len, userdata_start,
            _userdata_len, sdcard_start)

        return '%s,%s,%s,*\n%s,%s,L\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,,,-' % (
            boot_start, boot_len, partition_type, system_start, _system_len,
            cache_start, _cache_len, userdata_start, userdata_start,
            _userdata_len, sdcard_start)

    @classmethod
    def populate_raw_partition(cls, media, boot_dir):
        super(AndroidBoardConfig, cls).populate_raw_partition(media, boot_dir)

    @classmethod
    def install_boot_loader(cls, boot_partition, boot_device_or_file):
        pass


class AndroidOmapConfig(AndroidBoardConfig):
    dtb_name = None


class AndroidBeagleConfig(AndroidOmapConfig, BeagleConfig):
    _extra_serial_opts = 'console=tty0 console=ttyO2,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttyO2'
    dtb_name = None


class AndroidPandaConfig(AndroidOmapConfig, PandaConfig):
    _extra_serial_opts = 'console=ttyO2,115200n8'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=48M '
        'omapfb.vram=0:24M,1:24M mem=456M@0x80000000 mem=512M@0xA0000000')
    android_specific_args = 'init=/init androidboot.console=ttyO2'
    dtb_name = None


class AndroidSnowballSdConfig(AndroidBoardConfig, SnowballSdConfig):
    boot_script = 'boot.scr'
    initrd_addr = '0x05000000'
    extra_boot_args_options = (
        'earlyprintk mem=128M@0 mali.mali_mem=64M@128M hwmem=168M@192M mem=22M@360M mem_issw=1M@383M mem=640M@384M vmalloc=300M')
    _extra_serial_opts = 'console=ttyAMA2,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttyAMA2'
    dtb_name = None


class AndroidSnowballEmmcConfig(AndroidBoardConfig, SnowballEmmcConfig):
    boot_script = 'boot.scr'
    initrd_addr = '0x05000000'
    extra_boot_args_options = (
        'earlyprintk mem=128M@0 mali.mali_mem=64M@128M hwmem=168M@192M mem=22M@360M mem_issw=1M@383M mem=640M@384M vmalloc=300M')
    _extra_serial_opts = 'console=ttyAMA2,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttyAMA2'
    mmc_option = '0:2'
    dtb_name = None

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):

        LOADER_MIN_SIZE_S = align_up(
            1 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE

        loader_start, loader_end, loader_len = align_partition(
            SnowballEmmcConfig.SNOWBALL_LOADER_START_S,
            LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        command = super(AndroidSnowballEmmcConfig, cls).get_sfdisk_cmd(
            should_align_boot_part=True, start_addr=loader_end,
            extra_part=True)

        return '%s,%s,0xDA\n%s' % (
            loader_start, loader_len, command)

    @classmethod
    def populate_raw_partition(cls, media, boot_dir):
        # To avoid adding a Snowball specific command line option, we assume
        # that the user already has unpacked the startfiles to ./startupfiles
        config_files_dir = cls.snowball_config(boot_dir)
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
        super(AndroidSnowballEmmcConfig, cls).populate_raw_partition(
            media, boot_dir)

    @classmethod
    def snowball_config(cls, chroot_dir):        
        # The user is expected to have unpacked the startupfiles to this subdir
        # of their working dir.
        return os.path.join('.', 'startupfiles')

    @classproperty
    def delete_startupfiles(cls):
        # The startupfiles will have been unpacked to the user's working dir
        # and should not be deleted after they have been installed.
        return False


class AndroidMx53LoCoConfig(AndroidBoardConfig, Mx53LoCoConfig):
    extra_boot_args_options = (
        'earlyprintk rootdelay=1 fixrtc nocompcache di1_primary tve')
    _extra_serial_opts = 'console=%s,115200n8' % (
        Mx53LoCoConfig.serial_tty)
    android_specific_args = 'init=/init androidboot.console=%s' % (
        Mx53LoCoConfig.serial_tty)
    dtb_name = None

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):
        loader_start, loader_end, loader_len = align_partition(
            1, cls.LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        command = super(AndroidMx53LoCoConfig, cls).get_sfdisk_cmd(
            should_align_boot_part=True, start_addr=loader_end,
            extra_part=True)

        return '%s,%s,0xDA\n%s' % (
            loader_start, loader_len, command)

    @classmethod
    def install_boot_loader(cls, boot_partition, boot_device_or_file):
        install_mx5_boot_loader(os.path.join(boot_device_or_file, "u-boot.imx"), boot_partition, cls.LOADER_MIN_SIZE_S)


class AndroidMx6QSabreliteConfig(AndroidMx53LoCoConfig):
    uboot_flavor = 'mx6qsabrelite'
    kernel_addr = '0x10000000'
    initrd_addr = '0x12000000'
    load_addr = '0x10008000'
    dtb_addr = '0x11ff0000'
    dtb_name = 'board.dtb'


class AndroidSamsungConfig(AndroidBoardConfig):
    dtb_name = None

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):
        loaders_min_len = (
            cls.SAMSUNG_V310_BL2_START + cls.SAMSUNG_V310_BL2_LEN -
            cls.SAMSUNG_V310_BL1_START)

        loader_start, loader_end, loader_len = align_partition(
            1, loaders_min_len, 1, PART_ALIGN_S)

        command = super(AndroidSamsungConfig, cls).get_sfdisk_cmd(
            should_align_boot_part=False, start_addr=loader_end,
            extra_part=True)

        return '%s,%s,0xDA\n%s' % (
            loader_start, loader_len, command)


class AndroidSMDKV310Config(AndroidSamsungConfig, SMDKV310Config):
    _extra_serial_opts = 'console=tty0 console=ttySAC1,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttySAC1'
    dtb_name = None


class AndroidOrigenConfig(AndroidSamsungConfig, OrigenConfig):
    _extra_serial_opts = 'console=tty0 console=ttySAC2,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttySAC2'
    dtb_name = None


class AndroidVexpressConfig(AndroidBoardConfig, VexpressConfig):
    _extra_serial_opts = 'console=tty0 console=ttyAMA0,38400n8'
    android_specific_args = 'init=/init androidboot.console=ttyAMA0'
    dtb_name = None


android_board_configs = {
    'beagle': AndroidBeagleConfig,
    'panda': AndroidPandaConfig,
    'snowball_sd': AndroidSnowballSdConfig,
    'snowball_emmc': AndroidSnowballEmmcConfig,
    'smdkv310': AndroidSMDKV310Config,
    'mx53loco': AndroidMx53LoCoConfig,
    'iMX53': AndroidMx53LoCoConfig,
    'mx6qsabrelite': AndroidMx6QSabreliteConfig,
    'origen': AndroidOrigenConfig,
    'vexpress': AndroidVexpressConfig,
    'vexpress-a9': AndroidVexpressConfig,
    }

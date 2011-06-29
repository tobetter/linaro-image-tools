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
from linaro_image_tools.media_create.boards import SnowballSdConfig
from linaro_image_tools.media_create.boards import SnowballEmmcConfig
from linaro_image_tools.media_create.boards import (
    align_up,
    align_partition,
    make_boot_script
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
        boot_env["bootcmd"] = cls._get_bootcmd(None)
        return boot_env

    @classmethod
    def populate_boot_script(cls, boot_partition, boot_disk, consoles):
        cmd_runner.run(['mkdir', '-p', boot_disk]).wait()
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
    def get_sfdisk_cmd(cls, should_align_boot_part=False, start_addr=0):
        if cls.fat_size == 32:
            partition_type = '0x0C'
        else:
            partition_type = '0x0E'

        BOOT_MIN_SIZE_S = align_up(128 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
        SYSTEM_MIN_SIZE_S = align_up(256 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
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
        # If start address isn't '0' an extra primary partition will be added.
        # Due to a maximum of 4 primary partitions cache data will be placed in
        # a extended partition
        if start_addr != 0:
            return '%s,%s,%s,*\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,%s,L\n%s,,,-' % (
            boot_start, boot_len, partition_type, system_start, _system_len,
            cache_start, cache_start, _cache_len, userdata_start,
            _userdata_len, sdcard_start)

        return '%s,%s,%s,*\n%s,%s,L\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,,,-' % (
            boot_start, boot_len, partition_type, system_start, _system_len,
            cache_start, _cache_len, userdata_start, userdata_start,
            _userdata_len, sdcard_start)

    @classmethod
    def populate_startup_partition(cls, media, boot_dir):
        pass


class AndroidOmapConfig(AndroidBoardConfig):
    pass


class AndroidBeagleConfig(AndroidOmapConfig, BeagleConfig):
    _extra_serial_opts = 'console=tty0 console=ttyO2,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttyO2'


class AndroidPandaConfig(AndroidOmapConfig, PandaConfig):
    _extra_serial_opts = 'console=tty0 console=ttyO2,115200n8'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=48M '
        'omapfb.vram=0:24M,1:24M mem=456M@0x80000000 mem=512M@0xA0000000')
    android_specific_args = 'init=/init androidboot.console=ttyO2'


class AndroidSnowballSdConfig(AndroidBoardConfig, SnowballSdConfig):
    extra_boot_args_options = (
        'earlyprintk rootdelay=1 fixrtc nocompcache '
        'mem=128M@0 mali.mali_mem=64M@128M mem=24M@192M hwmem=167M@216M '
        'mem_issw=1M@383M mem=640M@384M vmalloc=256M')
    _extra_serial_opts = 'console=tty0 console=ttyO2,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttyAMA2'


class AndroidSnowballEmmcConfig(AndroidBoardConfig, SnowballEmmcConfig):
    extra_boot_args_options = (
        'earlyprintk rootdelay=1 fixrtc nocompcache '
        'mem=128M@0 mali.mali_mem=64M@128M mem=24M@192M hwmem=167M@216M '
        'mem_issw=1M@383M mem=640M@384M vmalloc=256M')
    _extra_serial_opts = 'console=tty0 console=ttyAMA2,115200n8'
    android_specific_args = 'init=/init androidboot.console=ttyAMA2'

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):

        LOADER_MIN_SIZE_S = align_up(
            1 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE

        loader_start, loader_end, loader_len = align_partition(
            SnowballEmmcConfig.SNOWBALL_LOADER_START_S,
            LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        command = super(AndroidSnowballEmmcConfig, cls).get_sfdisk_cmd(
            should_align_boot_part=True, start_addr=loader_end)

        return '%s,%s,0xDA\n%s' % (
            loader_start, loader_len, command)

    @classmethod
    def populate_startup_partition(cls, media, boot_dir):
        config_files_path = os.path.join(boot_dir, 'boot')
        cls.populate_raw_partition(config_files_path, media)

android_board_configs = {
    'beagle': AndroidBeagleConfig,
    'panda': AndroidPandaConfig,
    'snowball_sd': AndroidSnowballSdConfig,
    'snowball_emmc': AndroidSnowballEmmcConfig,
    }

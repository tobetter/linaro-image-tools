# Copyright (C) 2010, 2011 Linaro
#
# Author: Guilherme Salgado <guilherme.salgado@linaro.org>
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

"""Configuration for boards supported by linaro-media-create.

To add support for a new board, you need to create a subclass of
BoardConfig, set appropriate values for its variables and add it to
board_configs at the bottom of this file.
"""

import atexit
import glob
import os
import re
import tempfile
import struct
from binascii import crc32

from linaro_image_tools import cmd_runner

from linaro_image_tools.media_create.partitions import SECTOR_SIZE

# Notes:
# * since we align partitions on 4 MiB by default, geometry is currently 128
#   heads and 32 sectors (2 MiB) as to have CHS-aligned partition start/end
#   offsets most of the time and hence avoid some warnings with disk
#   partitioning tools
# * apparently some OMAP3 ROMs don't tolerate vfat length of an odd number of
#   sectors (only sizes rounded to 1 KiB seem to boot)
# * we want partitions aligned on 4 MiB as to get the best performance and
#   limit wear-leveling
# * image_size is passed on the command-line and should preferably be a power
#   of 2; it should be used as a "don't go over this size" information for a
#   real device, and a "give me a file exactly this big" requirement for an
#   image file.  Having exactly a power of 2 helps with QEMU; there seem to be
#   some truncating issues otherwise. XXX to be researched

# align on 4 MiB
PART_ALIGN_S = 4 * 1024 * 1024 / SECTOR_SIZE

def align_up(value, align):
    """Round value to the next multiple of align."""
    return (value + align - 1) / align * align

# optional bootloader partition; at least 1 MiB; in theory, an i.MX5x
# bootloader partition could hold RedBoot, FIS table, RedBoot config, kernel,
# and initrd, but we typically use U-Boot which is about 167 KiB as of
# 2011/02/11 and currently doesn't even store its environment there, so this
# should be enough
LOADER_MIN_SIZE_S = align_up(1 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
# boot partition; at least 50 MiB; XXX this shouldn't be hardcoded
BOOT_MIN_SIZE_S = align_up(50 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
# root partition; at least 50 MiB; XXX this shouldn't be hardcoded
ROOT_MIN_SIZE_S = align_up(50 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE

# Samsung v310 implementation notes
# * BL1 (SPL) is expected at offset +1s and is 32s long
# * BL2 (u-boot) is loaded at a raw MMC offset of +65s by BL1 which currently
# doesn't support FAT
# * the u-boot environment is at +33s and is 32s long (16 KiB)
# * currently, some hardware issues on certain boards causes u-boot to not be
# able to use FAT to load uImage and uInitrd (or boot.scr); as a temporary
# workaround, these are loaded from +1089s and +9281s respectively
# * hence we hardcode all offsets, make sure that the files aren't larger than
# their reserved spot, and create a bootloader partition from the first
# sector after MBR up to end of initrd
SAMSUNG_V310_BL1_START = 1
SAMSUNG_V310_BL1_LEN = 32
SAMSUNG_V310_ENV_START = SAMSUNG_V310_BL1_START + SAMSUNG_V310_BL1_LEN
SAMSUNG_V310_ENV_LEN = 32
assert SAMSUNG_V310_ENV_START == 33, "BL1 expects u-boot environment at +33s"
assert SAMSUNG_V310_ENV_LEN * SECTOR_SIZE == 16 * 1024, (
    "BL1 expects u-boot environment to be 16 KiB")
SAMSUNG_V310_BL2_START = SAMSUNG_V310_ENV_START + SAMSUNG_V310_ENV_LEN
SAMSUNG_V310_BL2_LEN = 1024
assert SAMSUNG_V310_BL2_LEN * SECTOR_SIZE == 512 * 1024, (
    "BL1 expects BL2 (u-boot) to be 512 KiB")
SAMSUNG_V310_UIMAGE_START = SAMSUNG_V310_BL2_START + SAMSUNG_V310_BL2_LEN
SAMSUNG_V310_UIMAGE_LEN = 8192
assert SAMSUNG_V310_UIMAGE_START == 1089, (
    "BL2 (u-boot) expects uImage at +1089s")
assert SAMSUNG_V310_UIMAGE_LEN * SECTOR_SIZE == 4 * 1024 * 1024, (
    "BL2 (u-boot) expects uImage to be 4 MiB")
SAMSUNG_V310_UINITRD_START = (
    SAMSUNG_V310_UIMAGE_START + SAMSUNG_V310_UIMAGE_LEN)
SAMSUNG_V310_UINITRD_RESERVED_LEN = 204800
SAMSUNG_V310_UINITRD_COPY_LEN = 32768
assert SAMSUNG_V310_UINITRD_START == 9281, (
    "BL2 (u-boot) expects uInitrd at +9281s")
assert SAMSUNG_V310_UINITRD_RESERVED_LEN * SECTOR_SIZE == 100 * 1024 * 1024, (
    "BL2 (u-boot) expects uInitrd to be 100 MiB")
assert SAMSUNG_V310_UINITRD_COPY_LEN * SECTOR_SIZE == 16 * 1024 * 1024, (
    "Only copy 16MiB for a faster boot")

def align_partition(min_start, min_length, start_alignment, end_alignment):
    """Compute partition start and end offsets based on specified constraints.

    :param min_start: Minimal start offset of partition
    :param min_lengh: Minimal length of partition
    :param start_alignment: Alignment of this partition
    :param end_alignment: Alignment of the data following this partition
    :return: start offset, end offset (inclusive), length
    """
    start = align_up(min_start, start_alignment)
    # end offset is inclusive, so substact one
    end = align_up(start + min_length, end_alignment) - 1
    # and add one to length
    length = end - start + 1
    return start, end, length


class classproperty(object):
    """A descriptor that provides @property behavior on class methods."""
    def __init__(self, getter):
        self.getter = getter
    def __get__(self, instance, cls):
        return self.getter(cls)


class BoardConfig(object):
    """The configuration used when building an image for a board."""
    # These attributes may not need to be redefined on some subclasses.
    uboot_flavor = None
    # whether to copy u-boot to the boot partition
    uboot_in_boot_part = False
    mmc_option = '0:1'
    mmc_part_offset = 0
    fat_size = 32
    extra_serial_opts = ''
    live_serial_opts = ''
    extra_boot_args_options = None

    # These attributes must be defined on all subclasses.
    kernel_addr = None
    initrd_addr = None
    load_addr = None
    kernel_suffix = None
    boot_script = None
    serial_tty = None

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):
        """Return the sfdisk command to partition the media.

        :param should_align_boot_part: Whether to align the boot partition too.

        This default implementation returns a boot vfat partition of type FAT16
        or FAT32, followed by a root partition.
        """
        if cls.fat_size == 32:
            partition_type = '0x0C'
        else:
            partition_type = '0x0E'

        BOOT_MIN_SIZE_S = align_up(50 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
        ROOT_MIN_SIZE_S = align_up(50 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
            
        # align on sector 63 for compatibility with broken versions of x-loader
        # unless align_boot_part is set
        boot_align = 63
        if should_align_boot_part:
            boot_align = PART_ALIGN_S

        # can only start on sector 1 (sector 0 is MBR / partition table)
        boot_start, boot_end, boot_len = align_partition(
            1, BOOT_MIN_SIZE_S, boot_align, PART_ALIGN_S)
        # apparently OMAP3 ROMs require the vfat length to be an even number
        # of sectors (multiple of 1 KiB); decrease the length if it's odd,
        # there should still be enough room
        boot_len = boot_len - boot_len % 2
        boot_end = boot_start + boot_len - 1

        # we ignore _root_end / _root_len and return a sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,%s,*\n%s,,,-' % (
            boot_start, boot_len, partition_type, root_start)

    # TODO: Create separate config classes for android and move this method
    # into them, also renaming it to get_sfdisk_cmd() so that we don't need
    # the image_type check in partitions.py.
    @classmethod
    def get_android_sfdisk_cmd(cls, should_align_boot_part=False):
        if cls.fat_size == 32:
            partition_type = '0x0C'
        else:
            partition_type = '0x0E'

        BOOT_MIN_SIZE_S = align_up(128 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
        ROOT_MIN_SIZE_S = align_up(128 * 1024 * 1024, SECTOR_SIZE) / SECTOR_SIZE
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
            1, BOOT_MIN_SIZE_S, boot_align, PART_ALIGN_S)
        # apparently OMAP3 ROMs require the vfat length to be an even number
        # of sectors (multiple of 1 KiB); decrease the length if it's odd,
        # there should still be enough room
        boot_len = boot_len - boot_len % 2
        boot_end = boot_start + boot_len - 1

        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        system_start, _system_end, _system_len = align_partition(
            _root_end + 1, SYSTEM_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        cache_start, _cache_end, _cache_len = align_partition(
            _system_end + 1, CACHE_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        userdata_start, _userdata_end, _userdata_len = align_partition(
            _cache_end + 1, USERDATA_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        sdcard_start, _sdcard_end, _sdcard_len = align_partition(
            _userdata_end + 1, SDCARD_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
 
        return '%s,%s,%s,*\n%s,%s,L\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,%s,L\n%s,,,-' % (
            boot_start, boot_len, partition_type, root_start, _root_len, 
            system_start, _system_len, cache_start, cache_start, _cache_len,
            userdata_start, _userdata_len, sdcard_start)

    @classproperty
    def bootcmd(cls):
        """Get the bootcmd for this board.

        In general subclasses should not have to override this.
        """
        replacements = dict(
            mmc_option=cls.mmc_option, kernel_addr=cls.kernel_addr,
            initrd_addr=cls.initrd_addr)
        return (
            "fatload mmc %(mmc_option)s %(kernel_addr)s "
                "uImage; fatload mmc %(mmc_option)s %(initrd_addr)s uInitrd; "
                "bootm %(kernel_addr)s %(initrd_addr)s"
                % replacements)

    @classmethod
    def _get_bootargs(cls, is_live, is_lowmem, consoles, rootfs_uuid):
        """Get the bootargs for this board.

        In general subclasses should not have to override this.
        """
        boot_args_options = 'rootwait ro'
        if cls.extra_boot_args_options is not None:
            boot_args_options += ' %s' % cls.extra_boot_args_options
        serial_opts = cls.extra_serial_opts
        for console in consoles:
            serial_opts += ' console=%s' % console

        lowmem_opt = ''
        boot_snippet = 'root=UUID=%s' % rootfs_uuid
        if is_live:
            serial_opts += ' %s' % cls.live_serial_opts
            boot_snippet = 'boot=casper'
            if is_lowmem:
                lowmem_opt = 'only-ubiquity'

        replacements = dict(
            serial_opts=serial_opts,
            lowmem_opt=lowmem_opt, boot_snippet=boot_snippet,
            boot_args_options=boot_args_options)
        return (
            "%(serial_opts)s %(lowmem_opt)s "
                "%(boot_snippet)s %(boot_args_options)s"
             % replacements)

    @classmethod
    def _get_boot_env(cls, is_live, is_lowmem, consoles, rootfs_uuid):
        """Get the boot environment for this board.

        In general subclasses should not have to override this.
        """
        boot_env = {}
        boot_env["bootargs"] = cls._get_bootargs(
            is_live, is_lowmem, consoles, rootfs_uuid)
        boot_env["bootcmd"] = cls.bootcmd
        return boot_env

    @classmethod
    def make_boot_files(cls, uboot_parts_dir, is_live, is_lowmem, consoles,
                        chroot_dir, rootfs_uuid, boot_dir, boot_device_or_file):
        boot_env = cls._get_boot_env(is_live, is_lowmem, consoles, rootfs_uuid)
        cls._make_boot_files(
            uboot_parts_dir, boot_env, chroot_dir, boot_dir, 
            boot_device_or_file)

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file):
        """Make the necessary boot files for this board.

        This is usually board-specific so ought to be defined in every
        subclass.
        """
        raise NotImplementedError()

    @classmethod
    def populate_boot(cls, chroot_dir, rootfs_uuid, boot_partition, boot_disk,
                      boot_device_or_file, is_live, is_lowmem, consoles):
        parts_dir = 'boot'
        if is_live:
            parts_dir = 'casper'
        uboot_parts_dir = os.path.join(chroot_dir, parts_dir)

        cmd_runner.run(['mkdir', '-p', boot_disk]).wait()
        cmd_runner.run(['mount', boot_partition, boot_disk],
            as_root=True).wait()

        if cls.uboot_in_boot_part:
            assert cls.uboot_flavor is not None, (
                "uboot_in_boot_part is set but not uboot_flavor")
            uboot_bin = os.path.join(chroot_dir, 'usr', 'lib', 'u-boot',
                cls.uboot_flavor, 'u-boot.bin')
            cmd_runner.run(
                ['cp', '-v', uboot_bin, boot_disk], as_root=True).wait()

        cls.make_boot_files(
            uboot_parts_dir, is_live, is_lowmem, consoles, chroot_dir,
            rootfs_uuid, boot_disk, boot_device_or_file)

        cmd_runner.run(['sync']).wait()
        try:
            cmd_runner.run(['umount', boot_disk], as_root=True).wait()
        except cmd_runner.SubcommandNonZeroReturnValue:
            pass


class OmapConfig(BoardConfig):
    kernel_suffix = 'linaro-omap'
    uboot_in_boot_part = True

    # XXX: Here we define these things as dynamic properties because our
    # temporary hack to fix bug 697824 relies on changing the board's
    # serial_tty at run time.
    _extra_serial_opts = None
    _live_serial_opts = None
    _serial_tty = None

    @classproperty
    def serial_tty(cls):
        # This is just to make sure no callsites use .serial_tty before
        # calling set_appropriate_serial_tty(). If we had this in the first
        # place we'd have uncovered bug 710971 before releasing.
        raise AttributeError(
            "You must not use this attribute before calling "
            "set_appropriate_serial_tty")

    @classproperty
    def live_serial_opts(cls):
        return cls._live_serial_opts % cls.serial_tty

    @classproperty
    def extra_serial_opts(cls):
        return cls._extra_serial_opts % cls.serial_tty

    @classmethod
    def set_appropriate_serial_tty(cls, chroot_dir):
        """Set the appropriate serial_tty depending on the kernel used.

        If the kernel found in the chroot dir is << 2.6.36 we use tyyS2, else
        we use the default value (_serial_tty).
        """
        # XXX: This is also part of our temporary hack to fix bug 697824.
        cls.serial_tty = classproperty(lambda cls: cls._serial_tty)
        vmlinuz = _get_file_matching(
            os.path.join(chroot_dir, 'boot', 'vmlinuz*'))
        basename = os.path.basename(vmlinuz)
        minor_version = re.match('.*2\.6\.([0-9]{2}).*', basename).group(1)
        if int(minor_version) < 36:
            cls.serial_tty = classproperty(lambda cls: 'ttyS2')

    @classmethod
    def make_boot_files(cls, uboot_parts_dir, is_live, is_lowmem, consoles,
                        chroot_dir, rootfs_uuid, boot_dir, boot_device_or_file):
        # XXX: This is also part of our temporary hack to fix bug 697824; we
        # need to call set_appropriate_serial_tty() before doing anything that
        # may use cls.serial_tty.
        cls.set_appropriate_serial_tty(chroot_dir)
        super(OmapConfig, cls).make_boot_files(
            uboot_parts_dir, is_live, is_lowmem, consoles, chroot_dir,
            rootfs_uuid, boot_dir, boot_device_or_file)

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file):
        install_omap_boot_loader(chroot_dir, boot_dir)
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)
        make_boot_ini(boot_script_path, boot_dir)


class BeagleConfig(OmapConfig):
    uboot_flavor = 'omap3_beagle'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    _live_serial_opts = 'serialtty=%s'
    kernel_addr = '0x80000000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=12M '
        'omapfb.mode=dvi:1280x720MR-16@60')


class OveroConfig(OmapConfig):
    uboot_flavor = 'omap3_overo'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    kernel_addr = '0x80000000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk mpurate=500 vram=12M '
        'omapfb.mode=dvi:1024x768MR-16@60 omapdss.def_disp=dvi')


class PandaConfig(OmapConfig):
    uboot_flavor = 'omap4_panda'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    _live_serial_opts = 'serialtty=%s'
    kernel_addr = '0x80200000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=32M '
        'omapfb.vram=0:8M mem=463M ip=none')


class IgepConfig(BeagleConfig):
    uboot_in_boot_part = False
    uboot_flavor = None

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file):
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)
        make_boot_ini(boot_script_path, boot_dir)


class Ux500Config(BoardConfig):
    serial_tty = 'ttyAMA2'
    extra_serial_opts = 'console=tty0 console=%s,115200n8' % serial_tty
    live_serial_opts = 'serialtty=%s' % serial_tty
    kernel_addr = '0x00100000'
    initrd_addr = '0x08000000'
    load_addr = '0x00008000'
    kernel_suffix = 'u?500'
    boot_script = 'flash.scr'
    extra_boot_args_options = (
        'earlyprintk rootdelay=1 fixrtc nocompcache '
        'mem=96M@0 mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
        'hwmem=48M@302M mem=152M@360M')
    mmc_option = '1:1'

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file):
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)


class Mx5Config(BoardConfig):
    serial_tty = 'ttymxc0'
    extra_serial_opts = 'console=tty0 console=%s,115200n8' % serial_tty
    live_serial_opts = 'serialtty=%s' % serial_tty
    boot_script = 'boot.scr'
    mmc_part_offset = 1
    mmc_option = '0:2'

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=None):
        """Return the sfdisk command to partition the media.

        :param should_align_boot_part: Ignored.

        This i.MX5 implementation returns a non-FS data bootloader partition,
        followed by a FAT32 boot partition, followed by a root partition.
        """
        # boot ROM expects bootloader at 0x400 which is sector 2 with the usual
        # SECTOR_SIZE of 512; we could theoretically leave sector 1 unused, but
        # older bootloaders like RedBoot might store the environment from 0x0
        # onwards, so it's safer to just start at the first sector, sector 1
        # (sector 0 is MBR / partition table)
        loader_start, loader_end, loader_len = align_partition(
            1, LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        boot_start, boot_end, boot_len = align_partition(
            loader_end + 1, BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        # we ignore _root_end / _root_len and return a sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
            loader_start, loader_len, boot_start, boot_len, root_start)

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file):
        uboot_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', cls.uboot_flavor, 'u-boot.imx')
        install_mx5_boot_loader(uboot_file, boot_device_or_file)
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)


class Mx51Config(Mx5Config):
    kernel_addr = '0x90000000'
    initrd_addr = '0x92000000'
    load_addr = '0x90008000'
    kernel_suffix = 'linaro-mx51'


class Mx53Config(Mx5Config):
    kernel_addr = '0x70800000'
    initrd_addr = '0x71800000'
    load_addr = '0x70008000'
    kernel_suffix = 'linaro-lt-mx53'


class EfikamxConfig(Mx51Config):
    uboot_flavor = 'efikamx'


class EfikasbConfig(Mx51Config):
    uboot_flavor = 'efikasb'


class Mx51evkConfig(Mx51Config):
    uboot_flavor = 'mx51evk'


class Mx53LoCoConfig(Mx53Config):
    uboot_flavor = 'mx53loco'


class VexpressConfig(BoardConfig):
    uboot_flavor = 'ca9x4_ct_vxp'
    uboot_in_boot_part = True
    serial_tty = 'ttyAMA0'
    extra_serial_opts = 'console=tty0 console=%s,38400n8' % serial_tty
    live_serial_opts = 'serialtty=%s' % serial_tty
    kernel_addr = '0x60008000'
    initrd_addr = '0x81000000'
    load_addr = kernel_addr
    kernel_suffix = 'linaro-vexpress'
    boot_script = None
    # ARM Boot Monitor is used to load u-boot, uImage etc. into flash and
    # only allows for FAT16
    fat_size = 16

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file):
        make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        make_uInitrd(uboot_parts_dir, cls.kernel_suffix, boot_dir)

class SMDKV310Config(BoardConfig):
    serial_tty = 'ttySAC1'
    extra_serial_opts = 'console=%s,115200n8' % serial_tty
    kernel_addr = '0x40007000'
    initrd_addr = '0x41000000'
    load_addr = '0x40008000'
    kernel_suffix = 's5pv310'
    boot_script = 'boot.scr'
    mmc_part_offset = 1
    mmc_option = '0:2'

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):
        # bootloader partition needs to hold everything from BL1 to uInitrd
        # inclusive
        min_len = (
            SAMSUNG_V310_UINITRD_START + SAMSUNG_V310_UINITRD_RESERVED_LEN -
            SAMSUNG_V310_BL1_START)

        # bootloader partition
        loader_start, loader_end, loader_len = align_partition(
            1, min_len, 1, PART_ALIGN_S)

        # FAT boot partition
        boot_start, boot_end, boot_len = align_partition(
            loader_end + 1, BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        # root partition
        # we ignore _root_end / _root_len and return a sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
            loader_start, loader_len, boot_start, boot_len, root_start)

    @classmethod
    def _get_boot_env(cls, is_live, is_lowmem, consoles, rootfs_uuid):
        boot_env = super(SMDKV310Config, cls)._get_boot_env(
            is_live, is_lowmem, consoles, rootfs_uuid)

        boot_env["ethact"] = "smc911x-0"
        boot_env["ethaddr"] = "00:40:5c:26:0a:5b"
        # XXX fixme once FAT support is fixed in u-boot bug 727978
        boot_env["bootcmd"] = (
            "movi read kernel %(kernel_addr)s; "
            "movi read rootfs %(initrd_addr)s %(rootfs_size)s; "
            "bootm %(kernel_addr)s %(initrd_addr)s" % {
                'kernel_addr': cls.kernel_addr,
                'initrd_addr': cls.initrd_addr,
                'rootfs_size': hex(SAMSUNG_V310_UINITRD_COPY_LEN * SECTOR_SIZE)})

        return boot_env

    @classmethod
    def _make_boot_files(cls, uboot_parts_dir, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file):
        uboot_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', 'smdkv310', 'u-boot.v310')
        install_smdkv310_boot_loader(uboot_file, boot_device_or_file)

        env_size = SAMSUNG_V310_ENV_LEN * SECTOR_SIZE
        env_file = make_flashable_env(boot_env, env_size)
        install_smdkv310_boot_env(env_file, boot_device_or_file)

        uImage_file = make_uImage(
            cls.load_addr, uboot_parts_dir, cls.kernel_suffix, boot_dir)
        install_smdkv310_uImage(uImage_file, boot_device_or_file)

        uInitrd_file = make_uInitrd(
            uboot_parts_dir, cls.kernel_suffix, boot_dir)
        install_smdkv310_initrd(uInitrd_file, boot_device_or_file)

        # unused at the moment once FAT support enabled for the
        # Samsung u-boot this can be used bug 727978
        #boot_script_path = os.path.join(boot_dir, cls.boot_script)
        #make_boot_script(boot_env, boot_script_path)


board_configs = {
    'beagle': BeagleConfig,
    'igep': IgepConfig,
    'panda': PandaConfig,
    'vexpress': VexpressConfig,
    'ux500': Ux500Config,
    'efikamx': EfikamxConfig,
    'efikasb': EfikasbConfig,
    'mx51evk': Mx51evkConfig,
    'mx53loco' : Mx53LoCoConfig,
    'overo': OveroConfig,
    'smdkv310': SMDKV310Config,
    }

android_board_configs = {
    'beagle': BeagleConfig,
    'panda': PandaConfig,
    }


def _dd(input_file, output_file, block_size=SECTOR_SIZE, count=None, seek=None,
        skip=None):
    """Wrapper around the dd command"""
    cmd = [
        "dd", "if=%s" % input_file, "of=%s" % output_file,
        "bs=%s" % block_size, "conv=notrunc"]
    if count is not None:
        cmd.append("count=%s" % count)
    if seek is not None:
        cmd.append("seek=%s" % seek)
    if skip is not None:
        cmd.append("skip=%s" % skip)
    proc = cmd_runner.run(cmd, as_root=True)
    proc.wait()


def _run_mkimage(img_type, load_addr, entry_point, name, img_data, img,
                 stdout=None, as_root=True):
    cmd = ['mkimage',
           '-A', 'arm',
           '-O', 'linux',
           '-T', img_type,
           '-C', 'none',
           '-a', load_addr,
           '-e', load_addr,
           '-n', name,
           '-d', img_data,
           img]
    proc = cmd_runner.run(cmd, as_root=as_root, stdout=stdout)
    proc.wait()
    return proc.returncode


def _get_file_matching(regex):
    """Return a file whose path matches the given regex.

    If zero or more than one files match, raise a ValueError.
    """
    files = glob.glob(regex)
    if len(files) == 1:
        return files[0]
    elif len(files) == 0:
        raise ValueError(
            "No files found matching '%s'; can't continue" % regex)
    else:
        # TODO: Could ask the user to chosse which file to use instead of
        # raising an exception.
        raise ValueError("Too many files matching '%s' found." % regex)


def make_uImage(load_addr, uboot_parts_dir, suffix, boot_disk):
    img_data = _get_file_matching(
        '%s/vmlinuz-*-%s' % (uboot_parts_dir, suffix))
    img = '%s/uImage' % boot_disk
    _run_mkimage(
        'kernel', load_addr, load_addr, 'Linux', img_data, img)
    return img


def make_uInitrd(uboot_parts_dir, suffix, boot_disk):
    img_data = _get_file_matching(
        '%s/initrd.img-*-%s' % (uboot_parts_dir, suffix))
    img = '%s/uInitrd' % boot_disk
    _run_mkimage('ramdisk', '0', '0', 'initramfs', img_data, img)
    return img


def make_boot_script(boot_env, boot_script_path):
    boot_script_data = (
        "setenv bootcmd '%(bootcmd)s'\n"
        "setenv bootargs '%(bootargs)s'\n"
        "boot"
        % boot_env)

    # Need to save the boot script data into a file that will be passed to
    # mkimage.
    _, tmpfile = tempfile.mkstemp()
    atexit.register(os.unlink, tmpfile)
    plain_boot_script = os.path.join(
        os.path.dirname(boot_script_path), 'boot.txt')
    with open(tmpfile, 'w') as fd:
        fd.write(boot_script_data)
    cmd_runner.run(['cp', tmpfile, plain_boot_script], as_root=True).wait()
    return _run_mkimage(
        'script', '0', '0', 'boot script', plain_boot_script, boot_script_path)


def make_flashable_env(boot_env, env_size):
    env_strings = ["%s=%s" % (k, v) for k, v in boot_env.items()]
    env_strings.sort()
    env = struct.pack('B', 0).join(env_strings)

    # we still need to zero-terminate the last string, and 4 bytes for crc
    assert len(env) + 1 + 4 <= env_size, (
        "environment doesn't fit in %s bytes" % env_size)

    # pad the rest of the env for the CRC calc; the "s" format will write zero
    # bytes to pad the (empty) string to repeat count
    env += struct.pack('%ss' % (env_size - len(env) - 4), '')

    crc = crc32(env)
    env = struct.pack('<i', crc) + env

    _, tmpfile = tempfile.mkstemp()

    with open(tmpfile, 'w') as fd:
        fd.write(env)

    return tmpfile


def install_mx5_boot_loader(imx_file, boot_device_or_file):
    # bootloader partition starts at +1s but we write the file at +2s, so we
    # need to check that the bootloader partition minus 1s is at least as large
    # as the u-boot binary; note that the real bootloader partition might be
    # larger than LOADER_MIN_SIZE_S, but if u-boot is larger it's a sign we
    # need to bump LOADER_MIN_SIZE_S
    max_size = (LOADER_MIN_SIZE_S - 1) * SECTOR_SIZE
    assert os.path.getsize(imx_file) <= max_size, (
        "%s is larger than guaranteed bootloader partition size" % imx_file)
    _dd(imx_file, boot_device_or_file, seek=2)


def _get_mlo_file(chroot_dir):
    # XXX bug=702645: This is a temporary solution to make sure l-m-c works
    # with any version of x-loader-omap. The proper solution is to have
    # hwpacks specify the location of the MLO file or include just the MLO
    # file instead of an x-loader-omap package.
    # This pattern matches the path of MLO files installed by the latest
    # x-loader-omap package (e.g. /usr/lib/x-loader/<version>/MLO)
    files = glob.glob(
        os.path.join(chroot_dir, 'usr', 'lib', '*', '*', 'MLO'))
    if len(files) == 0:
        # This one matches the path of MLO files installed by older
        # x-loader-omap package (e.g. /usr/lib/x-loader-omap[34]/MLO)
        files = glob.glob(
            os.path.join(chroot_dir, 'usr', 'lib', '*', 'MLO'))
    if len(files) == 1:
        return files[0]
    elif len(files) > 1:
        raise AssertionError(
            "More than one MLO file found on %s" % chroot_dir)
    else:
        raise AssertionError("No MLO files found on %s" % chroot_dir)


def install_omap_boot_loader(chroot_dir, boot_disk):
    mlo_file = _get_mlo_file(chroot_dir)
    cmd_runner.run(["cp", "-v", mlo_file, boot_disk], as_root=True).wait()
    # XXX: Is this really needed?
    cmd_runner.run(["sync"]).wait()


def make_boot_ini(boot_script_path, boot_disk):
    proc = cmd_runner.run(
        ["cp", "-v", boot_script_path, "%s/boot.ini" % boot_disk],
        as_root=True)
    proc.wait()


def install_smdkv310_uImage(uImage_file, boot_device_or_file):
    # the layout keeps SAMSUNG_V310_UIMAGE_LEN sectors for uImage; make sure
    # uImage isn't actually larger or it would be truncated
    max_size = SAMSUNG_V310_UIMAGE_LEN * SECTOR_SIZE
    assert os.path.getsize(uImage_file) <= max_size, (
        "%s is larger than the allocated v310 uImage length" % uImage_file)
    _dd(uImage_file, boot_device_or_file, count=SAMSUNG_V310_UIMAGE_LEN,
        seek=SAMSUNG_V310_UIMAGE_START)


def install_smdkv310_initrd(initrd_file, boot_device_or_file):
    # the layout keeps SAMSUNG_V310_UINITRD_RESERVED_LEN sectors for uInitrd
    # but only SAMSUNG_V310_UINITRD_COPY_LEN sectors are loaded into memory;
    # make sure uInitrd isn't actually larger or it would be truncated in
    # memory
    max_size = SAMSUNG_V310_UINITRD_COPY_LEN * SECTOR_SIZE
    assert os.path.getsize(initrd_file) <= max_size, (
        "%s is larger than the v310 uInitrd length as used by u-boot"
            % initrd_file)
    _dd(initrd_file, boot_device_or_file,
        count=SAMSUNG_V310_UINITRD_COPY_LEN,
        seek=SAMSUNG_V310_UINITRD_START)


def install_smdkv310_boot_env(env_file, boot_device_or_file):
    # the environment file is exactly SAMSUNG_V310_ENV_LEN as created by
    # make_flashable_env(), so we don't need to check the size of env_file
    _dd(env_file, boot_device_or_file, count=SAMSUNG_V310_ENV_LEN,
        seek=SAMSUNG_V310_ENV_START)


def install_smdkv310_boot_loader(v310_file, boot_device_or_file):
    """Samsung specific terminology
    BL0 is the first stage bootloader,
    BL1 is the SPL (secondary program loader)
    v310_file is a binary with the same layout as BL1 + u-boot environment +
    BL2; write BL1 (SPL) piece first (SAMSUNG_V310_BL1_LEN sectors at +0s in
    the file and +SAMSUNG_V310_BL1_START on disk), then write BL2 (u-boot)
    piece (rest of the file starting at +(SAMSUNG_V310_BL1_LEN +
    SAMSUNG_V310_ENV_LEN)s in the file which is the same as
    +(SAMSUNG_V310_BL2_START - SAMSUNG_V310_BL1_START)s)
    """
    _dd(v310_file, boot_device_or_file, count=SAMSUNG_V310_BL1_LEN,
        seek=SAMSUNG_V310_BL1_START)
    # XXX need to check that the length of v310_file - 64s is smaller than
    # SAMSUNG_V310_BL2_LEN
    _dd(v310_file, boot_device_or_file, seek=SAMSUNG_V310_BL2_START,
        skip=(SAMSUNG_V310_BL2_START - SAMSUNG_V310_BL1_START))


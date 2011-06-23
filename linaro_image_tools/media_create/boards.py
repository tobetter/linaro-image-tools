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

KERNEL_GLOB = 'vmlinuz-*-%(kernel_flavor)s'
INITRD_GLOB = 'initrd.img-*-%(kernel_flavor)s'
DTB_GLOB = 'dt-*-%(kernel_flavor)s/%(dtb_name)s'

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

# Samsung v310 implementation notes and terminology
#
# * BL0, BL1 etc. are the various bootloaders in order of execution
# * BL0 is the first stage bootloader, located in ROM; it loads a 32s long BL1
#   from MMC offset +1s and runs it
# * BL1 is the secondary program loader (SPL), a small (< 14k) version of
#   U-Boot with a checksum; it inits DRAM and loads a 1024s long BL2 to DRAM
#   from MMC offset +65s
# * BL2 is U-Boot; it loads its 32s (16 KiB) long environment from MMC offset
#   +33s which tells it to load a boot.scr from the first FAT partition of the
#   MMC
#
# Layout:
# +0s: part table / MBR, 1s long
# +1s: BL1/SPL, 32s long
# +33s: U-Boot environment, 32s long
# +65s: U-Boot, 1024s long
# >= +1089s: FAT partition with boot script (boot.scr), kernel (uImage) and
#            initrd (uInitrd)
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
    supports_writing_to_mmc = True

    # These attributes must be defined on all subclasses.
    kernel_addr = None
    initrd_addr = None
    load_addr = None
    dtb_addr = None
    dtb_name = None
    kernel_flavors = None
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

    @classmethod
    def _get_bootcmd(cls, d_img_data):
        """Get the bootcmd for this board.

        In general subclasses should not have to override this.
        """
        replacements = dict(
            mmc_option=cls.mmc_option, kernel_addr=cls.kernel_addr,
            initrd_addr=cls.initrd_addr, dtb_addr=cls.dtb_addr)
        boot_script = (
            "fatload mmc %(mmc_option)s %(kernel_addr)s uImage; "
            "fatload mmc %(mmc_option)s %(initrd_addr)s uInitrd; "
            % replacements)
        if d_img_data is not None:
            assert cls.dtb_addr is not None, (
                "Need a dtb_addr when passing d_img_data")
            boot_script += (
                "fatload mmc %(mmc_option)s %(dtb_addr)s board.dtb; "
                "bootm %(kernel_addr)s %(initrd_addr)s %(dtb_addr)s"
                % replacements)
        else:
            boot_script += (
                "bootm %(kernel_addr)s %(initrd_addr)s" % replacements)
        return boot_script

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
    def _get_boot_env(cls, is_live, is_lowmem, consoles, rootfs_uuid,
                      d_img_data):
        """Get the boot environment for this board.

        In general subclasses should not have to override this.
        """
        boot_env = {}
        boot_env["bootargs"] = cls._get_bootargs(
            is_live, is_lowmem, consoles, rootfs_uuid)
        boot_env["bootcmd"] = cls._get_bootcmd(d_img_data)
        return boot_env

    @classmethod
    def make_boot_files(cls, uboot_parts_dir, is_live, is_lowmem, consoles,
                        chroot_dir, rootfs_uuid, boot_dir, boot_device_or_file):
        (k_img_data, i_img_data, d_img_data) = cls._get_kflavor_files(
                                                   uboot_parts_dir)
        boot_env = cls._get_boot_env(is_live, is_lowmem, consoles, rootfs_uuid,
                                     d_img_data)
        cls._make_boot_files(
            boot_env, chroot_dir, boot_dir,
            boot_device_or_file, k_img_data, i_img_data, d_img_data)

    @classmethod
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
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

    @classmethod
    def _get_kflavor_files(cls, path):
        """Search for kernel, initrd and optional dtb in path."""
        for flavor in cls.kernel_flavors:
            kregex = KERNEL_GLOB % {'kernel_flavor' : flavor}
            iregex = INITRD_GLOB % {'kernel_flavor' : flavor}
            dregex = DTB_GLOB % {'kernel_flavor' : flavor,
                                 'dtb_name' : cls.dtb_name}
            kernel = _get_file_matching(os.path.join(path, kregex))
            if kernel is not None:
                initrd = _get_file_matching(os.path.join(path, iregex))
                if initrd is not None:
                    dtb = None
                    if cls.dtb_name is not None:
                        dtb = _get_file_matching(os.path.join(path, dregex))
                    return (kernel, initrd, dtb)
                raise ValueError(
                    "Found kernel for flavor %s but no initrd matching %s" % (
                        flavor, iregex))
        raise ValueError(
            "No kernel found matching %s for flavors %s" % (
                KERNEL_GLOB, " ".join(cls.kernel_flavors)))


class OmapConfig(BoardConfig):
    kernel_flavors = ['linaro-omap4', 'linaro-omap', 'omap4']
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
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        install_omap_boot_loader(chroot_dir, boot_dir)
        make_uImage(cls.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        make_dtb(d_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)
        make_boot_ini(boot_script_path, boot_dir)


class BeagleConfig(OmapConfig):
    uboot_flavor = 'omap3_beagle'
    dtb_name = 'omap3-beagle.dtb'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    _live_serial_opts = 'serialtty=%s'
    kernel_addr = '0x80000000'
    dtb_addr = '0x815f0000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=12M '
        'omapfb.mode=dvi:1280x720MR-16@60 mpurate=${mpurate}')


class OveroConfig(OmapConfig):
    uboot_flavor = 'omap3_overo'
    dtb_name = 'omap3-overo.dtb'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    kernel_addr = '0x80000000'
    dtb_addr = '0x815f0000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk mpurate=${mpurate} vram=12M')


class PandaConfig(OmapConfig):
    uboot_flavor = 'omap4_panda'
    dtb_name = 'omap4-panda.dtb'
    _serial_tty = 'ttyO2'
    _extra_serial_opts = 'console=tty0 console=%s,115200n8'
    _live_serial_opts = 'serialtty=%s'
    kernel_addr = '0x80200000'
    dtb_addr = '0x815f0000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=48M '
        'omapfb.vram=0:24M mem=456M@0x80000000 mem=512M@0xA0000000')


class IgepConfig(BeagleConfig):
    uboot_in_boot_part = False
    uboot_flavor = None
    dtb_name = 'isee-igep-v2.dtb'

    @classmethod
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        make_uImage(cls.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        make_dtb(d_img_data, boot_dir)
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
    kernel_flavors = ['u8500', 'ux500']
    boot_script = 'flash.scr'
    extra_boot_args_options = (
        'earlyprintk rootdelay=1 fixrtc nocompcache '
        'mem=96M@0 mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
        'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
        'hwmem=48M@302M mem=152M@360M')
    mmc_option = '1:1'

    @classmethod
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        make_uImage(cls.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)


class SnowballSdConfig(Ux500Config):
    '''Use only with --mmc option. Creates the standard vfat and ext2
       partitions for kernel and rootfs on an SD card.
       Note that the Snowball board needs a loader partition on the
       internal eMMC flash to boot. That partition is created with
       the SnowballConfigImage configuration.'''

    @classmethod
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        make_uImage(cls.load_addr, k_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)


class SnowballEmmcConfig(SnowballSdConfig):
    '''Use only with --image option. Creates a raw image which contains an
       additional (raw) loader partition, containing some boot stages
       and u-boot.'''
    # Boot ROM looks for a boot table of contents (TOC) at 0x20000
    # Actually, it first looks at address 0, but that's where l-m-c
    # puts the MBR, so the boot loader skips that address. 
    supports_writing_to_mmc = False
    SNOWBALL_LOADER_START_S = (128 * 1024) / SECTOR_SIZE
    SNOWBALL_STARTUP_FILES_CONFIG = 'startfiles.cfg'
    TOC_SIZE = 512

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=None):
        """Return the sfdisk command to partition the media.

        :param should_align_boot_part: Ignored.

        The Snowball partitioning scheme depends on whether the target is
        a raw image or an SD card. Both targets have the normal
        FAT 32 boot partition and EXT? root partition.
        The raw image prepends these two partitions with a raw loader partition,
        containing HW-dependent boot stages up to and including u-boot.
        This is done since the boot rom always boots off the internal memory;
        there simply is no point to having a loader partition on SD card.
        """
        # boot ROM expects bootloader at 0x20000, which is sector 0x100 
        # with the usual SECTOR_SIZE of 0x200.
        # (sector 0 is MBR / partition table)
        loader_start, loader_end, loader_len = align_partition(
            SnowballEmmcConfig.SNOWBALL_LOADER_START_S, 
            LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        boot_start, boot_end, boot_len = align_partition(
            loader_end + 1, BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        # we ignore _root_end / _root_len and return an sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
        loader_start, loader_len, boot_start, boot_len, root_start)

    @classmethod
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        make_uImage(cls.load_addr, k_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)
        _, toc_filename = tempfile.mkstemp()
        atexit.register(os.unlink, toc_filename)
        config_files_path = os.path.join(chroot_dir, 'boot')
        new_files = cls.get_file_info(config_files_path)
        with open(toc_filename, 'wb') as toc:
            cls.create_toc(toc, new_files)
        cls.install_snowball_boot_loader(toc_filename, new_files,
                                     boot_device_or_file,
                                     cls.SNOWBALL_LOADER_START_S)

    @classmethod
    def install_snowball_boot_loader(cls, toc_file_name, files,
                                     boot_device_or_file, start_sector):
        ''' Copies TOC and boot files into the boot partition.
        A sector size of 1 is used for some files, as they do not
        necessarily start on an even address. '''
        assert os.path.getsize(toc_file_name) <= cls.TOC_SIZE
        _dd(toc_file_name, boot_device_or_file, seek=start_sector)

        for file in files:
            # XXX We need checks that these files do not overwrite each
            # other. This code assumes that offset and file sizes are ok.
            if (file['offset'] % SECTOR_SIZE) != 0:
                seek_bytes = start_sector * SECTOR_SIZE + file['offset']
                _dd(file['filename'], boot_device_or_file, block_size=1,
                    seek=seek_bytes)
            else:
                seek_sectors = start_sector + file['offset']/SECTOR_SIZE
                _dd(file['filename'], boot_device_or_file, seek=seek_sectors)

    @classmethod
    def create_toc(cls, f, files):
        ''' Writes a table of contents of the boot binaries.
        Boot rom searches this table to find the binaries.'''
        for file in files:
            # Format string means: < little endian,
            # I; unsigned int; offset,
            # I; unsigned int; size,
            # I; unsigned int; flags,
            # i; int; align,
            # i; int; load_address,
            # 12s; string of char; name
            # http://igloocommunity.org/support/index.php/ConfigPartitionOverview
            flags = 0
            load_adress = file['align']
            data = struct.pack('<IIIii12s', file['offset'], file['size'],
                               flags, file['align'], load_adress,
                               file['section_name'])
            f.write(data)

    @classmethod
    def get_file_info(cls, bin_dir):
        ''' Fills in the offsets of files that are located in
        non-absolute memory locations depending on their sizes.'
        Also fills in file sizes'''
        ofs = cls.TOC_SIZE
        files = []
        with open(os.path.join(bin_dir, cls.SNOWBALL_STARTUP_FILES_CONFIG),
                  'r') as info_file:
            for line in info_file:
                file_data = line.split()
                if file_data[0][0] == '#':
                    continue
                filename = os.path.join(bin_dir, file_data[1])
                address = long(file_data[3], 16)
                if address != 0:
                    ofs = address
                size = os.path.getsize(filename)
                files.append({'section_name': file_data[0],
                              'filename': filename,
                              'align': int(file_data[2]),
                              'offset': ofs,
                              'size': size,
                              'load_adress': file_data[4]})
                ofs += size
        return files


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
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        uboot_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', cls.uboot_flavor, 'u-boot.imx')
        install_mx5_boot_loader(uboot_file, boot_device_or_file)
        make_uImage(cls.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        make_dtb(d_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)


class Mx51Config(Mx5Config):
    kernel_addr = '0x90000000'
    dtb_addr = '0x91ff0000'
    initrd_addr = '0x92000000'
    load_addr = '0x90008000'
    kernel_flavors = ['linaro-mx51', 'linaro-lt-mx5']


class Mx53Config(Mx5Config):
    kernel_addr = '0x70000000'
    dtb_addr = '0x71ff0000'
    initrd_addr = '0x72000000'
    load_addr = '0x70008000'
    kernel_flavors = ['linaro-lt-mx53', 'linaro-lt-mx5']


class EfikamxConfig(Mx51Config):
    uboot_flavor = 'efikamx'
    dtb_name = 'genesi-efikamx.dtb'


class EfikasbConfig(Mx51Config):
    uboot_flavor = 'efikasb'
    dtb_name = 'genesi-efikasb.dtb'


class Mx51evkConfig(Mx51Config):
    uboot_flavor = 'mx51evk'
    dtb_name = 'mx51-babbage.dtb'


class Mx53LoCoConfig(Mx53Config):
    uboot_flavor = 'mx53loco'
    dtb_name = 'mx53-loco.dtb'


class VexpressConfig(BoardConfig):
    uboot_flavor = 'ca9x4_ct_vxp'
    uboot_in_boot_part = True
    serial_tty = 'ttyAMA0'
    extra_serial_opts = 'console=tty0 console=%s,38400n8' % serial_tty
    live_serial_opts = 'serialtty=%s' % serial_tty
    kernel_addr = '0x60008000'
    initrd_addr = '0x81000000'
    load_addr = kernel_addr
    kernel_flavors = ['linaro-vexpress']
    boot_script = None
    # ARM Boot Monitor is used to load u-boot, uImage etc. into flash and
    # only allows for FAT16
    fat_size = 16

    @classmethod
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        make_uImage(cls.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)

class SMDKV310Config(BoardConfig):
    uboot_flavor = 'smdkv310'
    serial_tty = 'ttySAC1'
    extra_serial_opts = 'console=%s,115200n8' % serial_tty
    kernel_addr = '0x40007000'
    initrd_addr = '0x42000000'
    load_addr = '0x40008000'
    kernel_flavors = ['s5pv310']
    boot_script = 'boot.scr'
    mmc_part_offset = 1
    mmc_option = '0:2'

    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):
        # bootloaders partition needs to hold BL1, U-Boot environment, and BL2
        loaders_min_len = (
            SAMSUNG_V310_BL2_START + SAMSUNG_V310_BL2_LEN -
            SAMSUNG_V310_BL1_START)

        # bootloaders partition
        loaders_start, loaders_end, loaders_len = align_partition(
            1, loaders_min_len, 1, PART_ALIGN_S)

        # FAT boot partition
        boot_start, boot_end, boot_len = align_partition(
            loaders_end + 1, BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        # root partition
        # we ignore _root_end / _root_len and return a sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
            loaders_start, loaders_len, boot_start, boot_len, root_start)

    @classmethod
    def _get_boot_env(cls, is_live, is_lowmem, consoles, rootfs_uuid,
                      d_img_data):
        boot_env = super(SMDKV310Config, cls)._get_boot_env(
            is_live, is_lowmem, consoles, rootfs_uuid, d_img_data)

        boot_env["ethact"] = "smc911x-0"
        boot_env["ethaddr"] = "00:40:5c:26:0a:5b"

        return boot_env

    @classmethod
    def _make_boot_files(cls, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        install_smdk_boot_loader(chroot_dir, boot_device_or_file, cls.uboot_flavor)
        env_size = SAMSUNG_V310_ENV_LEN * SECTOR_SIZE
        env_file = make_flashable_env(boot_env, env_size)
        _dd(env_file, boot_device_or_file, seek=SAMSUNG_V310_ENV_START)

        make_uImage(cls.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)

        # unused at the moment once FAT support enabled for the
        # Samsung u-boot this can be used bug 727978
        boot_script_path = os.path.join(boot_dir, cls.boot_script)
        make_boot_script(boot_env, boot_script_path)


board_configs = {
    'beagle': BeagleConfig,
    'igep': IgepConfig,
    'panda': PandaConfig,
    'vexpress': VexpressConfig,
    'ux500': Ux500Config,
    'snowball_sd': SnowballSdConfig,
    'snowball_emmc': SnowballEmmcConfig,
    'efikamx': EfikamxConfig,
    'efikasb': EfikasbConfig,
    'mx51evk': Mx51evkConfig,
    'mx53loco' : Mx53LoCoConfig,
    'overo': OveroConfig,
    'smdkv310': SMDKV310Config,
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
        return None
    else:
        # TODO: Could ask the user to chosse which file to use instead of
        # raising an exception.
        raise ValueError("Too many files matching '%s' found." % regex)


def make_uImage(load_addr, img_data, boot_disk):
    img = '%s/uImage' % boot_disk
    return _run_mkimage('kernel', load_addr, load_addr, 'Linux', img_data, img)


def make_uInitrd(img_data, boot_disk):
    img = '%s/uInitrd' % boot_disk
    return _run_mkimage('ramdisk', '0', '0', 'initramfs', img_data, img)


def make_dtb(img_data, boot_disk):
    img = None
    if img_data is not None:
        img = '%s/board.dtb' % boot_disk
        cmd_runner.run(['cp', img_data, img], as_root=True).wait()
    return img


def get_plain_boot_script_contents(boot_env):
    # We use double quotes to avoid u-boot argument limits
    # while retaining the ability to expand variables. See
    # https://bugs.launchpad.net/linaro-image-tools/+bug/788765
    # for more.
    return (
        'setenv bootcmd "%(bootcmd)s"\n'
        'setenv bootargs "%(bootargs)s"\n'
        "boot"
        % boot_env)


def make_boot_script(boot_env, boot_script_path):
    boot_script_data = get_plain_boot_script_contents(boot_env)
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


def _get_smdk_spl(chroot_dir, uboot_flavor):
    spl_dir = os.path.join(
        chroot_dir, 'usr', 'lib', 'u-boot', uboot_flavor)
    old_spl_path = os.path.join(spl_dir, 'v310_mmc_spl.bin')
    new_spl_path = os.path.join(spl_dir, 'u-boot-mmc-spl.bin')

    spl_file = old_spl_path
    # The new upstream u-boot filename has changed
    if not os.path.exists(spl_file):
        spl_file = new_spl_path

    if not os.path.exists(spl_file):
        # missing SPL loader
        raise AssertionError("Couldn't find the SPL file, tried %s and %s"
            % (old_spl_path, new_spl_path))
    return spl_file


def _get_smdk_uboot(chroot_dir, uboot_flavor):
    uboot_file = os.path.join(
        chroot_dir, 'usr', 'lib', 'u-boot', uboot_flavor, 'u-boot.bin')
    return uboot_file


def install_smdk_boot_loader(chroot_dir, boot_device_or_file, uboot_flavor):
    spl_file = _get_smdk_spl(chroot_dir, uboot_flavor)
    # XXX need to check that the length of spl_file is smaller than
    # SAMSUNG_V310_BL1_LEN
    _dd(spl_file, boot_device_or_file, seek=SAMSUNG_V310_BL1_START)

    uboot_file = _get_smdk_uboot(chroot_dir, uboot_flavor)
    # XXX need to check that the length of uboot_file is smaller than
    # SAMSUNG_V310_BL2_LEN
    _dd(uboot_file, boot_device_or_file, seek=SAMSUNG_V310_BL2_START)

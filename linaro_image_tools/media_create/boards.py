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

from binascii import crc32
from parted import Device
import atexit
import glob
import logging
import os
import re
import string
import struct
import tempfile

from linaro_image_tools import cmd_runner

from linaro_image_tools.hwpack.handler import HardwarepackHandler
from linaro_image_tools.media_create.partitions import (
    SECTOR_SIZE,
    partition_mounted,
    register_loopback,
)

from linaro_image_tools.hwpack.hwpack_fields import (
    BOOTFS,
    BOOTFS16,
    BOOT_MIN_SIZE_FIELD,
    BOOT_SCRIPT_FIELD,
    DTB_ADDR_FIELD,
    DTB_FILES_FIELD,
    DTB_FILE_FIELD,
    ENV_DD_FIELD,
    EXTRA_BOOT_OPTIONS_FIELD,
    EXTRA_SERIAL_OPTIONS_FIELD,
    INITRD_ADDR_FIELD,
    KERNEL_ADDR_FIELD,
    LOADER_MIN_SIZE_FIELD,
    LOADER_START_FIELD,
    LOAD_ADDR_FIELD,
    MMC_ID_FIELD,
    PARTITION_LAYOUT_FIELD,
    RESERVED_BOOTFS,
    ROOT_MIN_SIZE_FIELD,
    SAMSUNG_BL1_LEN_FIELD,
    SAMSUNG_BL1_START_FIELD,
    SAMSUNG_BL2_LEN_FIELD,
    SAMSUNG_BL2_START_FIELD,
    SAMSUNG_ENV_LEN_FIELD,
    SAMSUNG_ENV_START_FIELD,
    SERIAL_TTY_FIELD,
    SNOWBALL_STARTUP_FILES_CONFIG_FIELD,
    SPL_DD_FIELD,
    SPL_IN_BOOT_PART_FIELD,
    WIRED_INTERFACES_FIELD,
    WIRELESS_INTERFACES_FIELD,
)

logger = logging.getLogger(__name__)

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


def copy_drop(src, dest_dir):
    """Copy a file from src to destdir, dropping root ownership on the
    way.
    """
    cmd = ["cp", "-v", src, dest_dir]
    cmd_runner.run(cmd, as_root=True).wait()

    final = os.path.join(dest_dir, os.path.basename(src))
    cmd = ["chown", "%s:%s" % (os.getuid(), os.getgid()), final]
    cmd_runner.run(cmd, as_root=True).wait()
    os.chmod(final, 0644)


class BoardException(Exception):
    """Class for board related exceptions."""


class BoardConfig(object):
    """The configuration used when building an image for a board."""

    LOADER_MIN_SIZE_S = align_up(1 * 1024 ** 2, SECTOR_SIZE) / SECTOR_SIZE
    BOOT_MIN_SIZE_S = align_up(50 * 1024 ** 2, SECTOR_SIZE) / SECTOR_SIZE
    ROOT_MIN_SIZE_S = align_up(50 * 1024 ** 2, SECTOR_SIZE) / SECTOR_SIZE

    def __init__(self):
        super(BoardConfig, self).__init__()
        # XXX: when killing v1 hwpack, we might rename these two without the
        # leading underscore. It is done in this way since sublcasses use
        # placeholders in the string for dinamically change values. But this
        # is done only for hwpack v1.
        self._extra_serial_options = ''
        self._live_serial_options = ''
        self.board = None
        self.boot_script = None
        self.bootloader_dd = False
        self.bootloader_file_in_boot_part = False
        self.bootloader_flavor = None
        self.dtb_addr = None
        self.dtb_file = None
        self.dtb_files = None
        self.dtb_name = None
        self.env_dd = False
        self.extra_boot_args_options = None
        self.fat_size = 32
        self.fatload_command = 'fatload'
        self.load_interface = 'mmc'
        self.bootfs_type = 'vfat'
        self.fdt_high = '0xffffffff'
        self.hardwarepack_handler = None
        self.hwpack_format = None
        self.initrd_addr = None
        self.initrd_high = '0xffffffff'
        self.kernel_addr = None
        self.kernel_flavors = None
        self.load_addr = None
        self.loader_start_s = 1
        self.mmc_device_id = 0
        self.mmc_id = None
        self.mmc_option = '0:1'
        self.mmc_part_offset = 0
        self.partition_layout = None
        self.serial_tty = None
        self.spl_dd = False
        self.spl_in_boot_part = False
        self.supports_writing_to_mmc = True
        self.uimage_path = ''
        self.wired_interfaces = None
        self.wireless_interfaces = None
        # Samsung Boot-loader implementation notes and terminology
        #
        # BL0, BL1, BL2, BL3 are the boot loader stages in order of execution
        #
        # BL0 - embedded boot loader on the internal ROM
        # BL1 - chip-specific boot loader provided by Samsung
        # BL2 - tiny boot loader; SPL (Second Program Loader)
        # BL3 - customized boot loader; U-Boot
        #
        # In linaro-image-tools, variables have been named samsung_blN-1
        # e.g BL1 is samsung_bl0, BL2 is samsung_bl1, BL3 is samsung_bl2
        #
        # samsung_bl0_{start,len}: Offset and maximum size for BL1
        # samsung_bl1_{start,len}: Offset and maximum size for BL2
        # samsung_bl2_{start,len}: Offset and maximum size for BL3
        # samsung_env_{start,len}: Offset and maximum size for settings
        #
        self.samsung_bl1_start = 1
        self.samsung_bl1_len = 32
        self.samsung_bl2_start = 65
        self.samsung_bl2_len = 1024
        self.samsung_env_start = 33
        self.samsung_env_len = 32
        # XXX: attributes that are not listed in hwpackV3, should be removed?
        self.vmlinuz = None
        self.initrd = None

    # XXX: can be removed when killing v1 hwpack.
    def _get_live_serial_options(self):
        live_serial = self._live_serial_options
        if live_serial:
            if isinstance(live_serial, list):
                live_serial = ' '.join(live_serial)
            if self._check_placeholder_presence(live_serial, r'%s'):
                live_serial = live_serial % self.serial_tty
        return live_serial

    def _set_live_serial_options(self, value):
        self._live_serial_options = value

    live_serial_options = property(_get_live_serial_options,
                                   _set_live_serial_options)

    # XXX: can be removed when killing v1 hwpack.
    def _get_extra_serial_options(self):
        extra_serial = self._extra_serial_options
        if extra_serial:
            if isinstance(extra_serial, list):
                extra_serial = ' '.join(extra_serial)
            if self._check_placeholder_presence(extra_serial, r'%s'):
                extra_serial = extra_serial % self.serial_tty
        return extra_serial

    def _set_extra_serial_options(self, value):
        self._extra_serial_options = value

    extra_serial_options = property(_get_extra_serial_options,
                                    _set_extra_serial_options)

    def get_metadata_field(self, field_name):
        """ Return the metadata value for field_name if it can be found.
        """
        data, _ = self.hardwarepack_handler.get_field(field_name)
        return data

    def set_metadata(self, hwpacks, bootloader=None, board=None,
                     dtb_file=None):
        self.hardwarepack_handler = HardwarepackHandler(hwpacks, bootloader,
                                                        board)
        with self.hardwarepack_handler:
            self.hwpack_format = self.hardwarepack_handler.get_format()
            if (self.hwpack_format == self.hardwarepack_handler.FORMAT_1):
                self.bootloader_copy_files = None
                return

            if (self.hwpack_format != self.hardwarepack_handler.FORMAT_1):
                # Clear V1 defaults.
                # TODO When removing v1 support, remove also default values
                # in the constructor and avoid all this.
                self.kernel_addr = None
                self.initrd_addr = None
                self.load_addr = None
                self.serial_tty = None
                self.fat_size = None
                self.dtb_name = None
                self.dtb_addr = None
                self.extra_boot_args_options = None
                self.boot_script = None
                self.kernel_flavors = None
                self.mmc_option = None
                self.mmc_part_offset = None
                self.samsung_bl1_start = None
                self.samsung_bl1_len = None
                self.samsung_env_len = None
                self.samsung_bl2_len = None
                # self.samsung_bl2_start and self.samsung_env_start should
                # be initialized to default value for backward compatibility.

            self.board = board
            # Set new values from metadata.
            self.kernel_addr = self.get_metadata_field(KERNEL_ADDR_FIELD)
            self.initrd_addr = self.get_metadata_field(INITRD_ADDR_FIELD)
            self.load_addr = self.get_metadata_field(LOAD_ADDR_FIELD)
            self.dtb_addr = self.get_metadata_field(DTB_ADDR_FIELD)
            self.serial_tty = self.get_metadata_field(SERIAL_TTY_FIELD)
            wired_interfaces = self.get_metadata_field(WIRED_INTERFACES_FIELD)
            if wired_interfaces:
                self.wired_interfaces = wired_interfaces
            wireless_interfaces = self.get_metadata_field(
                WIRELESS_INTERFACES_FIELD)
            if wireless_interfaces:
                self.wireless_interfaces = wireless_interfaces
            self.dtb_file = self.get_metadata_field(DTB_FILE_FIELD)
            # XXX: need to deprecate dtb_file field and use only dtb_files
            # for multiple entries.
            if self.dtb_file:
                logger.warn("Deprecation warning: use the 'dtb_files' field "
                            "instead of 'dtb_file'.")
            self.dtb_files = self.get_metadata_field(DTB_FILES_FIELD)
            if dtb_file:
                dtb_dict = self._find_dtb_dict(dtb_file)
                if dtb_dict:
                    self.dtb_files = []
                    self.dtb_files.append(dtb_dict)

            self.extra_boot_args_options = self.get_metadata_field(
                EXTRA_BOOT_OPTIONS_FIELD)
            self.boot_script = self.get_metadata_field(BOOT_SCRIPT_FIELD)
            self.extra_serial_options = self.get_metadata_field(
                EXTRA_SERIAL_OPTIONS_FIELD)
            self.snowball_startup_files_config = self.get_metadata_field(
                SNOWBALL_STARTUP_FILES_CONFIG_FIELD)
            self.partition_layout = self.get_metadata_field(
                PARTITION_LAYOUT_FIELD)
            if self.partition_layout in [BOOTFS, RESERVED_BOOTFS, None]:
                self.fat_size = 32
            elif self.partition_layout == BOOTFS16:
                self.fat_size = 16
            else:
                raise AssertionError("Unknown partition layout '%s'." %
                                     self.partition_layout)

            self.mmc_option = self.get_metadata_field(MMC_ID_FIELD)
            if self.mmc_option:
                self.mmc_device_id = int(self.mmc_option.split(':')[0])
                self.mmc_part_offset = int(self.mmc_option.split(':')[1]) - 1

            # XXX: need to fix these values.
            boot_min_size = self.get_metadata_field(BOOT_MIN_SIZE_FIELD)
            if boot_min_size:
                self.BOOT_MIN_SIZE_S = align_up(int(boot_min_size) * 1024 ** 2,
                                                SECTOR_SIZE) / SECTOR_SIZE
            root_min_size = self.get_metadata_field(ROOT_MIN_SIZE_FIELD)
            if root_min_size:
                self.ROOT_MIN_SIZE_S = align_up(int(root_min_size) * 1024 ** 2,
                                                SECTOR_SIZE) / SECTOR_SIZE
            loader_min_size = self.get_metadata_field(LOADER_MIN_SIZE_FIELD)
            if loader_min_size:
                self.LOADER_MIN_SIZE_S = (
                    align_up(int(loader_min_size) * 1024 ** 2,
                             SECTOR_SIZE) / SECTOR_SIZE)

            spl_in_boot_part = self.get_metadata_field(SPL_IN_BOOT_PART_FIELD)
            if spl_in_boot_part is None:
                self.spl_in_boot_part = False
            elif string.lower(spl_in_boot_part) == 'yes':
                self.spl_in_boot_part = True
            elif string.lower(spl_in_boot_part) == 'no':
                self.spl_in_boot_part = False

            env_dd = self.get_metadata_field(ENV_DD_FIELD)
            if env_dd is None:
                self.env_dd = False
            elif string.lower(env_dd) == 'yes':
                self.env_dd = True
            elif string.lower(env_dd) == 'no':
                self.env_dd = False

            # XXX: in hwpack v3 this field is just called 'dd'.
            # Need to check its use.
            bootloader_dd = self.get_metadata_field('bootloader_dd')
            # Either bootloader_dd is not specified, or it contains the dd
            # offset.
            if bootloader_dd is None:
                self.bootloader_dd = False
            else:
                self.bootloader_dd = int(bootloader_dd)
            spl_dd = self.get_metadata_field(SPL_DD_FIELD)
            # Either spl_dd is not specified, or it contains the dd offset.
            if spl_dd is None:
                self.spl_dd = False
            else:
                self.spl_dd = int(spl_dd)

            loader_start = self.get_metadata_field(LOADER_START_FIELD)
            if loader_start:
                self.loader_start_s = int(loader_start)

            samsung_bl1_start = self.get_metadata_field(
                SAMSUNG_BL1_START_FIELD)
            if samsung_bl1_start:
                self.samsung_bl1_start = int(samsung_bl1_start)

            samsung_bl1_len = self.get_metadata_field(
                SAMSUNG_BL1_LEN_FIELD)
            if samsung_bl1_len:
                self.samsung_bl1_len = int(samsung_bl1_len)

            samsung_bl2_start = self.get_metadata_field(
                SAMSUNG_BL2_START_FIELD)
            if samsung_bl2_start:
                self.samsung_bl2_start = int(samsung_bl2_start)

            samsung_bl2_len = self.get_metadata_field(
                SAMSUNG_BL2_LEN_FIELD)
            if samsung_bl2_len:
                self.samsung_bl2_len = int(samsung_bl2_len)

            samsung_env_start = self.get_metadata_field(
                SAMSUNG_ENV_START_FIELD)
            if samsung_env_start is not None:
                self.samsung_env_start = int(samsung_env_start)

            samsung_env_len = self.get_metadata_field(
                SAMSUNG_ENV_LEN_FIELD)
            if samsung_env_len:
                self.samsung_env_len = int(samsung_env_len)

            self.bootloader_copy_files = self.hardwarepack_handler.get_field(
                "bootloader_copy_files")[0]

            # XXX: no reference in hwpackV3 format of these fields, double
            # check if they can be dropped when killing v1.
            self.bootloader = self.hardwarepack_handler.get_field(
                "bootloader")
            self.vmlinuz = self.get_metadata_field('vmlinuz')
            self.initrd = self.get_metadata_field('initrd')
            bootloader_file_in_boot_part = self.get_metadata_field(
                'bootloader_file_in_boot_part')
            if bootloader_file_in_boot_part is None:
                self.bootloader_file_in_boot_part = False
            elif string.lower(bootloader_file_in_boot_part) == 'yes':
                self.bootloader_file_in_boot_part = True
            elif string.lower(bootloader_file_in_boot_part) == 'no':
                self.bootloader_file_in_boot_part = False

    def get_file(self, file_alias, default=None):
        # XXX remove the 'default' parameter when V1 support is removed!
        file_in_hwpack = self.hardwarepack_handler.get_file(file_alias)
        if file_in_hwpack is not None:
            return file_in_hwpack
        else:
            return default

    def get_v1_sfdisk_cmd(self, should_align_boot_part=False):
        # XXX: This default implementation and all overrides are left for V1
        # compatibility only. They should be removed as part of the work to
        # kill off hwpacks V1.
        return self.get_normal_sfdisk_cmd(should_align_boot_part)

    def get_normal_params(self, should_align_boot_part=False):
        if self.bootfs_type == 'vfat':
            if self.fat_size == 32:
                partition_type = '0x0C'
            else:
                partition_type = '0x0E'
        else:
            partition_type = '0x83'

        # align on sector 63 for compatibility with broken versions of x-loader
        # unless align_boot_part is set
        # XXX OMAP specific, might break other boards?
        boot_align = 63
        if should_align_boot_part:
            boot_align = PART_ALIGN_S

        # can only start on sector 1 (sector 0 is MBR / partition table)
        boot_start, boot_end, boot_len = align_partition(
            1, self.BOOT_MIN_SIZE_S, boot_align, PART_ALIGN_S)
        # apparently OMAP3 ROMs require the vfat length to be an even number
        # of sectors (multiple of 1 KiB); decrease the length if it's odd,
        # there should still be enough room
        # XXX OMAP specific, might break other boards?
        boot_len = boot_len - boot_len % 2
        boot_end = boot_start + boot_len - 1

        # we ignore _root_end / _root_len and return a sfdisk command to
        # instruct the use of all remaining space; XXX we now have root size
        # config, so we can do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, self.ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return (boot_start, boot_len, partition_type, root_start)

    def get_reserved_params(self, should_align_boot_part=None):
        loader_start, loader_end, loader_len = align_partition(
            self.loader_start_s, self.LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        boot_start, boot_end, boot_len = align_partition(
            loader_end + 1, self.BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, self.ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return (loader_start, loader_len, boot_start, boot_len, root_start)

    def get_normal_sfdisk_cmd(self, should_align_boot_part=False):
        """Return the sfdisk command to partition the media.

        :param should_align_boot_part: Whether to align the boot partition too.

        This returns a boot partition of type FAT16 or FAT32 or Linux,
        followed by a root partition.
        """
        (boot_start, boot_len, partition_type,
            root_start) = self.get_normal_params(should_align_boot_part)

        return '%s,%s,%s,*\n%s,,,-' % (
            boot_start, boot_len, partition_type, root_start)

    def get_reserved_sfdisk_cmd(self, should_align_boot_part=None):
        """Return the sfdisk command to partition the media.

        :param should_align_boot_part: Ignored.

        This returns a loader partition, then a boot vfat partition of type
        FAT16 or FAT32, followed by a root partition.
        """
        (loader_start, loader_len, boot_start, boot_len,
            root_start) = self.get_reserved_params(should_align_boot_part)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
            loader_start, loader_len, boot_start, boot_len, root_start)

    def get_normal_sgdisk_cmd(self, should_align_boot_part=None):
        (boot_start, boot_len, partition_type,
            root_start) = self.get_normal_params(should_align_boot_part)
        # Ignoring partition type because we need 0xEF for GPT
        return '-n 1:%s:%s -t 1:EF00 ' \
               '-n 2:%s:- -t 2:8300' % (boot_start, boot_len, root_start)

    def get_reserved_sgdisk_cmd(self, should_align_boot_part=None):
        """Return the sgdisk command to partition the media.

        :param should_align_boot_part: Ignored.
        """
        (loader_start, loader_len, boot_start, boot_len,
            root_start) = self.get_reserved_params(should_align_boot_part)
        return '-n 1:%s:%s -t 1:DA00 ' \
               '-n 2:%s:%s -t 2:0C00 ' \
               '-n 3:%s:- -t 3:8300' % (
                   loader_start, loader_len, boot_start, boot_len, root_start)

    def get_sfdisk_cmd(self, should_align_boot_part=False):
        if (self.partition_layout in ['bootfs_rootfs', 'bootfs16_rootfs'] or
                self.board == 'snowball_sd'):
            return self.get_normal_sfdisk_cmd(should_align_boot_part)
        elif self.partition_layout in ['reserved_bootfs_rootfs']:
            return self.get_reserved_sfdisk_cmd(should_align_boot_part)
        else:
            assert (self.hwpack_format == HardwarepackHandler.FORMAT_1), (
                "Hwpack format is not 1.0 but "
                "partition_layout is unspecified.")
            return self.get_v1_sfdisk_cmd(should_align_boot_part)

    def get_sgdisk_cmd(self, should_align_boot_part=False):
        if (self.partition_layout in ['bootfs_rootfs', 'bootfs16_rootfs'] or
                self.board == 'snowball_sd'):
            return self.get_normal_sgdisk_cmd(should_align_boot_part)
        elif self.partition_layout in ['reserved_bootfs_rootfs']:
            return self.get_reserved_sgdisk_cmd(should_align_boot_part)
        else:
            assert (self.hwpack_format == HardwarepackHandler.FORMAT_1), (
                "Hwpack format is not 1.0 but "
                "partition_layout is unspecified.")
            return self.get_normal_sgdisk_cmd(should_align_boot_part)

    def _get_bootcmd(self, i_img_data, d_img_data):
        """Get the bootcmd for this board.

        In general subclasses should not have to override this.
        """
        replacements = dict(
            fatload_command=self.fatload_command, uimage_path=self.uimage_path,
            mmc_option=self.mmc_option, kernel_addr=self.kernel_addr,
            initrd_addr=self.initrd_addr, dtb_addr=self.dtb_addr,
            load_interface=self.load_interface)

        boot_script = (
            ("%(fatload_command)s %(load_interface)s %(mmc_option)s "
             "%(kernel_addr)s %(uimage_path)suImage; ")) % replacements
        boot_script_bootm = (("bootm %(kernel_addr)s")) % replacements
        if i_img_data is not None and d_img_data is not None:
            boot_script += (
                ("%(fatload_command)s %(load_interface)s %(mmc_option)s "
                 "%(initrd_addr)s %(uimage_path)suInitrd; "
                 "%(fatload_command)s %(load_interface)s %(mmc_option)s "
                 "%(dtb_addr)s board.dtb; ")) % replacements
            boot_script_bootm += (
                (" %(initrd_addr)s %(dtb_addr)s")) % replacements
        elif i_img_data is None and d_img_data is not None:
            boot_script += (
                ("%(fatload_command)s %(load_interface)s %(mmc_option)s "
                 "%(dtb_addr)s board.dtb; ")) % replacements
            boot_script_bootm += ((" - %(dtb_addr)s")) % replacements
        elif i_img_data is not None and d_img_data is None:
            boot_script += (
                ("%(fatload_command)s %(load_interface)s %(mmc_option)s "
                 "%(initrd_addr)s %(uimage_path)suInitrd; ")) % replacements
            boot_script_bootm += ((" %(initrd_addr)s")) % replacements

        boot_script += boot_script_bootm
        return boot_script

    def add_boot_args(self, extra_args):
        if extra_args is not None:
            if self.extra_boot_args_options is None:
                self.extra_boot_args_options = extra_args
            else:
                self.extra_boot_args_options += ' %s' % extra_args

    def add_boot_args_from_file(self, path):
        if path is not None:
            with open(path, 'r') as boot_args_file:
                self.add_boot_args(boot_args_file.read().strip())

    def _get_bootargs(self, is_live, is_lowmem, consoles, rootfs_id):
        """Get the bootargs for this board.

        In general subclasses should not have to override this.
        """
        boot_args_options = 'rootwait ro'
        serial_options = ''
        if self.extra_boot_args_options:
            boot_args_options += ' %s' % self.extra_boot_args_options.strip()
        if self.extra_serial_options:
            serial_options = self.extra_serial_options.strip()
        for console in consoles:
            serial_options += ' console=%s' % console.strip()

        lowmem_opt = ''
        boot_snippet = 'root=%s' % rootfs_id.strip()
        if is_live:
            serial_options += ' %s' % self.live_serial_options
            boot_snippet = 'boot=casper'
            if is_lowmem:
                lowmem_opt = 'only-ubiquity'

        replacements = dict(serial_options=serial_options.strip(),
                            lowmem_opt=lowmem_opt,
                            boot_snippet=boot_snippet,
                            boot_args_options=boot_args_options)
        boot_args = ("%(serial_options)s %(lowmem_opt)s %(boot_snippet)s"
                     " %(boot_args_options)s" % replacements).strip()
        return boot_args

    def _get_boot_env(self, is_live, is_lowmem, consoles, rootfs_id,
                      i_img_data, d_img_data):
        """Get the boot environment for this board.

        In general subclasses should not have to override this.
        """
        boot_env = {}
        boot_env["bootargs"] = self._get_bootargs(
            is_live, is_lowmem, consoles, rootfs_id)
        boot_env["bootcmd"] = self._get_bootcmd(i_img_data, d_img_data)
        boot_env["initrd_high"] = self.initrd_high
        boot_env["fdt_high"] = self.fdt_high
        return boot_env

    def make_boot_files(self, bootloader_parts_dir, is_live, is_lowmem,
                        consoles, chroot_dir, rootfs_id, boot_dir,
                        boot_device_or_file):
        if self.hwpack_format == HardwarepackHandler.FORMAT_1:
            parts_dir = bootloader_parts_dir
        else:
            parts_dir = chroot_dir
        (k_img_data, i_img_data, d_img_data) = self._get_kflavor_files(
            parts_dir)
        boot_env = self._get_boot_env(is_live, is_lowmem, consoles, rootfs_id,
                                      i_img_data, d_img_data)

        if self.hwpack_format == HardwarepackHandler.FORMAT_1:
            self._make_boot_files(
                boot_env, chroot_dir, boot_dir,
                boot_device_or_file, k_img_data, i_img_data, d_img_data)
        else:
            self._make_boot_files_v2(
                boot_env, chroot_dir, boot_dir,
                boot_device_or_file, k_img_data, i_img_data, d_img_data)

    def _copy_dtb_files(self, dtb_files, dest_dir, search_dir):
        """Copy the files defined in dtb_files into the boot directory.

        :param dtb_files: The list of dtb files
        :param dest_dir: The directory where to copy each dtb file.
        :param search_dir: The directory where to search for the real file.
        """
        logger.info("Copying dtb files")
        for dtb_file in dtb_files:
            if dtb_file:
                if isinstance(dtb_file, dict):
                    for key, value in dtb_file.iteritems():
                        # The name of the dtb file in the new position.
                        to_file = os.path.basename(key)
                        # The directory where to copy the dtb file.
                        to_dir = os.path.join(dest_dir, os.path.dirname(key))
                        from_file = value

                        # User specified only the directory, without renaming
                        # the file.
                        if not to_file:
                            to_file = os.path.basename(from_file)

                        if not os.path.exists(to_dir):
                            cmd_runner.run(["mkdir", "-p", to_dir],
                                           as_root=True).wait()
                        dtb = _get_file_matching(os.path.join(search_dir,
                                                              from_file))
                        if not dtb:
                            logger.warn('Could not find a valid dtb file, '
                                        'skipping it.')
                            continue
                        else:
                            dest = os.path.join(to_dir, to_file)
                            logger.debug('Copying %s into %s' % (dtb, dest))
                            cmd_runner.run(['cp', dtb, dest],
                                           as_root=True).wait()
                else:
                    # Hopefully we should never get here.
                    # This should only happen if the hwpack config YAML file is
                    # wrong.
                    logger.warn('WARNING: Wrong syntax in metadata file. '
                                'Check the hwpack configuration file used to '
                                'generate the hwpack archive.')

    def _dd_file(self, from_file, to_file, seek, max_size=None):
        assert from_file is not None, "No source file name given."
        if max_size is not None:
            assert os.path.getsize(from_file) <= max_size, (
                "'%s' is larger than %s" % (from_file, max_size))
        logger.info("Writing '%s' to '%s' at %s." % (from_file, to_file, seek))
        _dd(from_file, to_file, seek=seek)

    def install_samsung_boot_loader(self, samsung_spl_file, bootloader_file,
                                    boot_device_or_file):
                self._dd_file(samsung_spl_file, boot_device_or_file,
                              self.samsung_bl1_start,
                              self.samsung_bl1_len * SECTOR_SIZE)
                self._dd_file(bootloader_file, boot_device_or_file,
                              self.samsung_bl2_start,
                              self.samsung_bl2_len * SECTOR_SIZE)

    def _make_boot_files_v2(self, boot_env, chroot_dir, boot_dir,
                            boot_device_or_file, k_img_data, i_img_data,
                            d_img_data):
        with self.hardwarepack_handler:
            spl_file = self.get_file('spl_file')
            if self.spl_in_boot_part:
                assert spl_file is not None, (
                    "SPL binary could not be found")
                logger.info(
                    "Copying spl '%s' to boot partition." % spl_file)
                cmd_runner.run(["cp", "-v", spl_file, boot_dir],
                               as_root=True).wait()

            if self.spl_dd:
                self._dd_file(spl_file, boot_device_or_file, self.spl_dd)

            bootloader_file = self.get_file('bootloader_file')
            if self.bootloader_dd:
                self._dd_file(bootloader_file, boot_device_or_file,
                              self.bootloader_dd)

        make_uImage(self.load_addr, k_img_data, boot_dir)

        if i_img_data is not None:
            make_uInitrd(i_img_data, boot_dir)

        if d_img_data is not None:
            make_dtb(d_img_data, boot_dir)

        if self.boot_script is not None:
            boot_script_path = os.path.join(boot_dir, self.boot_script)
            make_boot_script(boot_env, boot_script_path)

            # Only used for Omap, will this be bad for the other boards?
            make_boot_ini(boot_script_path, boot_dir)

        if (self.snowball_startup_files_config is not None and
                self.board != 'snowball_sd'):
            self.populate_raw_partition(boot_device_or_file, chroot_dir)

        if self.env_dd:
            # Do we need to zero out the env before flashing it?
            _dd("/dev/zero", boot_device_or_file,
                count=self.samsung_env_len,
                seek=self.samsung_env_start)
            env_size = self.samsung_env_len * SECTOR_SIZE
            env_file = make_flashable_env(boot_env, env_size)
            self._dd_file(env_file, boot_device_or_file,
                          self.samsung_env_start)

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        """Make the necessary boot files for this board.

        This is usually board-specific so ought to be defined in every
        subclass.
        """
        raise NotImplementedError()

    def populate_boot(self, chroot_dir, rootfs_id, boot_partition, boot_disk,
                      boot_device_or_file, is_live, is_lowmem, consoles):
        parts_dir = 'boot'
        if is_live:
            parts_dir = 'casper'
        bootloader_parts_dir = os.path.join(chroot_dir, parts_dir)
        cmd_runner.run(['mkdir', '-p', boot_disk]).wait()
        with partition_mounted(boot_partition, boot_disk):
            with self.hardwarepack_handler:
                if self.bootloader_file_in_boot_part:
                    # <legacy v1 support>
                    if self.bootloader_flavor is not None:
                        default = os.path.join(
                            chroot_dir, 'usr', 'lib', 'u-boot',
                            self.bootloader_flavor, 'u-boot.img')
                        if not os.path.exists(default):
                            default = os.path.join(
                                chroot_dir, 'usr', 'lib', 'u-boot',
                                self.bootloader_flavor, 'u-boot.bin')
                    else:
                        default = None
                    # </legacy v1 support>
                    bootloader_bin = self.get_file('bootloader_file',
                                                   default=default)
                    assert bootloader_bin is not None, (
                        "bootloader binary could not be found")

                    proc = cmd_runner.run(
                        ['cp', '-v', bootloader_bin, boot_disk], as_root=True)
                    proc.wait()

                # Handle copy_files field.
                self.copy_files(boot_disk)

            # Handle dtb_files field.
            if self.dtb_files:
                self._copy_dtb_files(self.dtb_files, boot_disk, chroot_dir)

            self.make_boot_files(
                bootloader_parts_dir, is_live, is_lowmem, consoles, chroot_dir,
                rootfs_id, boot_disk, boot_device_or_file)

    def copy_files(self, boot_disk):
        """Handle the copy_files metadata field."""

        # Extract anything specified by copy_files sections
        # self.bootloader_copy_files is always of the form:
        # {'source_package':
        #  [
        #   {'source_path': 'dest_path'}
        #  ]
        # }
        if self.bootloader_copy_files is None:
            return

        for source_package, file_list in \
                self.bootloader_copy_files.iteritems():
            for file_info in file_list:
                for source_path, dest_path in file_info.iteritems():
                    source = self.hardwarepack_handler.get_file_from_package(
                        source_path, source_package)
                    dest_path = dest_path.lstrip("/\\")
                    dirname = os.path.dirname(dest_path)
                    dirname = os.path.join(boot_disk, dirname)
                    if not os.path.exists(dirname):
                        cmd_runner.run(["mkdir", "-p", dirname],
                                       as_root=True).wait()
                    proc = cmd_runner.run(
                        ['cp', '-v', source,
                         os.path.join(boot_disk, dest_path)], as_root=True)
                    proc.wait()

    def _get_kflavor_files(self, path):
        """Search for kernel, initrd and optional dtb in path."""
        if self.kernel_flavors is None:
            # V2 metadata specifies each glob, not flavors.
            # XXX This duplication is temporary until V1 dies.
            return self._get_kflavor_files_v2(path)

        for flavor in self.kernel_flavors:
            kregex = KERNEL_GLOB % {'kernel_flavor': flavor}
            iregex = INITRD_GLOB % {'kernel_flavor': flavor}
            dregex = DTB_GLOB % {'kernel_flavor': flavor,
                                 'dtb_name': self.dtb_name}
            kernel = _get_file_matching(os.path.join(path, kregex))
            if kernel is not None:
                initrd = _get_file_matching(os.path.join(path, iregex))
                if initrd is not None:
                    dtb = None
                    if self.dtb_name is not None:
                        dtb = _get_file_matching(os.path.join(path, dregex))
                    return (kernel, initrd, dtb)
                raise ValueError(
                    "Found kernel for flavor %s but no initrd matching %s" % (
                        flavor, iregex))
        raise ValueError(
            "No kernel found matching %s for flavors %s" % (
                KERNEL_GLOB, " ".join(self.kernel_flavors)))

    def _get_kflavor_files_v2(self, path):
        kernel = initrd = dtb = None

        if self.vmlinuz:
            kernel = _get_file_matching(os.path.join(path, self.vmlinuz))
        if not self.vmlinuz or not kernel:
            raise ValueError("Unable to find a valid kernel image.")

        if self.initrd:
            initrd = _get_file_matching(os.path.join(path, self.initrd))
        if not self.initrd or not initrd:
            logger.warn("Could not find a valid initrd, skipping uInitrd.")

        if self.dtb_file:
            dtb = _get_file_matching(os.path.join(path, self.dtb_file))
        if not self.dtb_file or not dtb:
            logger.warn("Could not find a valid dtb file from dtb_file, "
                        "trying dtb_files...")

        if self.dtb_files:
            # Use first file from list as a default dtb file.
            dtb_file = self.dtb_files[0]
            if dtb_file:
                if isinstance(dtb_file, dict):
                    for key, value in dtb_file.iteritems():
                        # The name of the dtb file.
                        to_file = os.path.basename(key)
                        from_file = value

                        # User specified only the directory, without renaming
                        # the file.
                        if not to_file:
                            to_file = os.path.basename(from_file)
                        dtb = _get_file_matching(os.path.join(path, from_file))
        if not self.dtb_files or not dtb:
            logger.warn("Could not find a valid dtb file, skipping it.")

        logger.info("Will use kernel=%s, initrd=%s, dtb=%s." %
                    (kernel, initrd, dtb))
        return (kernel, initrd, dtb)

    def populate_raw_partition(self, media, boot_dir):
        # Override in subclass if needed
        pass

    def snowball_config(self, chroot_dir):
        # Override in subclasses where applicable
        raise NotImplementedError(
            "snowball_config() must only be called on BoardConfigs that "
            "use the Snowball startupfiles.")

    # XXX: can be removed when killing v1 hwpack and updating the attributes
    # that use it.
    @staticmethod
    def _check_placeholder_presence(string, placeholder):
        """Checks if the passed string contains the particular placeholder."""
        # Very simple way of achieving that.
        presence = False
        if string and placeholder in string:
            presence = True
        return presence

    def _find_dtb_dict(self, dtb):
        """Returns dictionary entry from dt_files containing dtb file."""
        for dtb_file in self.dtb_files:
            if isinstance(dtb_file, dict):
                for key, value in dtb_file.iteritems():
                    # The name of the dtb file.
                    if dtb in key:
                        return dtb_file
        return None


class OmapConfig(BoardConfig):
    def __init__(self):
        super(OmapConfig, self).__init__()
        self.kernel_flavors = ['linaro-omap4', 'linaro-lt-omap',
                               'linaro-omap', 'omap4']
        self.bootloader_file_in_boot_part = True
        # XXX: Here we define these things as dynamic properties because our
        # temporary hack to fix bug 697824 relies on changing the board's
        # serial_tty at run time.
        self._serial_tty = None

    # XXX: when killing v1 hwpack this should be safely removed.
    def _get_serial_tty(self):
        return self._serial_tty

    def _set_serial_tty(self, value):
        self._serial_tty = value

    serial_tty = property(_get_serial_tty, _set_serial_tty)

    def set_appropriate_serial_tty(self, chroot_dir):
        """Set the appropriate serial_tty depending on the kernel used.

        If the kernel found in the chroot dir is << 2.6.36 we use tyyS2, else
        we use the default value (_serial_tty).
        """
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        # XXX: This is also part of our temporary hack to fix bug 697824.
        # cls.serial_tty = classproperty(lambda cls: cls._serial_tty)
        vmlinuz = _get_file_matching(
            os.path.join(chroot_dir, 'boot', 'vmlinuz*'))
        basename = os.path.basename(vmlinuz)
        match = re.match('.*2\.6\.([0-9]{2}).*', basename)
        # Assume if it doesn't match that it is 3.0 or later.
        if match is not None:
            minor_version = match.group(1)
            if int(minor_version) < 36:
                self.serial_tty = 'ttyS2'

    def make_boot_files(self, bootloader_parts_dir, is_live, is_lowmem,
                        consoles, chroot_dir, rootfs_id, boot_dir,
                        boot_device_or_file):
        # XXX: This is also part of our temporary hack to fix bug 697824; we
        # need to call set_appropriate_serial_tty() before doing anything that
        # may use self.serial_tty.
        if self.hwpack_format == HardwarepackHandler.FORMAT_1:
            self.set_appropriate_serial_tty(chroot_dir)
        super(OmapConfig, self).make_boot_files(
            bootloader_parts_dir, is_live, is_lowmem, consoles, chroot_dir,
            rootfs_id, boot_dir, boot_device_or_file)

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        install_omap_boot_loader(chroot_dir, boot_dir, self)
        make_uImage(self.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        make_dtb(d_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)
        make_boot_ini(boot_script_path, boot_dir)


class BeagleConfig(OmapConfig):
    def __init__(self):
        super(BeagleConfig, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'omap3_beagle'
        self.dtb_addr = '0x815f0000'
        self.dtb_name = 'omap3-beagle.dtb'
        self.extra_boot_args_options = (
            'earlyprintk fixrtc nocompcache vram=12M '
            'omapfb.mode=dvi:1280x720MR-16@60 mpurate=${mpurate}')
        self.initrd_addr = '0x81600000'
        self.kernel_addr = '0x80000000'
        self.load_addr = '0x80008000'
        self._serial_tty = 'ttyO2'
        self._extra_serial_options = 'console=tty0 console=%s,115200n8'
        self._live_serial_options = 'serialtty=%s'


class OveroConfig(OmapConfig):
    def __init__(self):
        super(OveroConfig, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'omap3_overo'
        self.dtb_addr = '0x815f0000'
        self.dtb_name = 'omap3-overo.dtb'
        self.extra_boot_args_options = (
            'earlyprintk mpurate=${mpurate} vram=12M '
            'omapdss.def_disp=${defaultdisplay} omapfb.mode=dvi:${dvimode}')
        self.initrd_addr = '0x81600000'
        self.kernel_addr = '0x80000000'
        self.load_addr = '0x80008000'
        self._extra_serial_options = 'console=tty0 console=%s,115200n8'
        self._serial_tty = 'ttyO2'


class PandaConfig(OmapConfig):
    def __init__(self):
        super(PandaConfig, self).__init__()
        self._serial_tty = 'ttyO2'
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'omap4_panda'
        self.dtb_addr = '0x815f0000'
        self.dtb_name = 'omap4-panda.dtb'
        self.extra_boot_args_options = (
            'earlyprintk fixrtc nocompcache vram=48M '
            'omapfb.vram=0:24M mem=456M@0x80000000 mem=512M@0xA0000000')
        self.initrd_addr = '0x81600000'
        self.kernel_addr = '0x80200000'
        self.load_addr = '0x80008000'
        self._extra_serial_options = 'console=tty0 console=%s,115200n8'
        self._live_serial_options = 'serialtty=%s'


class BeagleBoneConfig(OmapConfig):
    def __init__(self):
        super(BeagleBoneConfig, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'am335x_evm'
        self.kernel_flavors = ['am335x']
        self._serial_tty = 'ttyO0'
        self.dtb_addr = '0x815f0000'
        self.initrd_addr = '0x81600000'
        self.kernel_addr = '0x80200000'
        self.load_addr = '0x80008000'
        self.extra_boot_args_options = ('fixrtc')
        self._extra_serial_options = 'console=ttyO0,115200n8'


class IgepConfig(BeagleConfig):
    def __init__(self):
        super(IgepConfig, self).__init__()
        self.bootloader_file_in_boot_part = False
        self.bootloader_flavor = None
        self.dtb_name = 'isee-igep-v2.dtb'

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        make_uImage(self.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        make_dtb(d_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)
        make_boot_ini(boot_script_path, boot_dir)


class Ux500Config(BoardConfig):
    def __init__(self):
        super(Ux500Config, self).__init__()
        self.boot_script = 'flash.scr'
        self.extra_boot_args_options = (
            'earlyprintk rootdelay=1 fixrtc nocompcache '
            'mem=96M@0 mem_modem=32M@96M mem=44M@128M pmem=22M@172M '
            'mem=30M@194M mem_mali=32M@224M pmem_hwb=54M@256M '
            'hwmem=48M@302M mem=152M@360M')
        self.initrd_addr = '0x08000000'
        self.kernel_addr = '0x00100000'
        self.kernel_flavors = ['u8500', 'ux500']
        self.load_addr = '0x00008000'
        self.mmc_option = '1:1'
        self.serial_tty = 'ttyAMA2'
        self._extra_serial_options = 'console=tty0 console=%s,115200n8'
        self._live_serial_options = 'serialtty=%s'

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        make_uImage(self.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)


class SnowballSdConfig(Ux500Config):
    '''Use only with --mmc option. Creates the standard vfat and ext2
       partitions for kernel and rootfs on an SD card.
       Note that the Snowball board needs a loader partition on the
       internal eMMC flash to boot. That partition is created with
       the SnowballConfigImage configuration.'''
    def __init__(self):
        super(SnowballSdConfig, self).__init__()

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        make_uImage(self.load_addr, k_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)


class SnowballEmmcConfig(SnowballSdConfig):
    '''Use only with --image option. Creates a raw image which contains an
       additional (raw) loader partition, containing some boot stages
       and u-boot.'''
    SNOWBALL_LOADER_START_S = (128 * 1024) / SECTOR_SIZE
    TOC_SIZE = 512

    def __init__(self):
        super(SnowballEmmcConfig, self).__init__()
        # Boot ROM looks for a boot table of contents (TOC) at 0x20000
        # Actually, it first looks at address 0, but that's where l-m-c
        # puts the MBR, so the boot loader skips that address.
        self.supports_writing_to_mmc = False
        self.snowball_startup_files_config = 'startfiles.cfg'
        self.mmc_option = '0:2'

    def get_v1_sfdisk_cmd(self, should_align_boot_part=None):
        """Return the sfdisk command to partition the media.

        :param should_align_boot_part: Ignored.

        The Snowball partitioning scheme depends on whether the target is
        a raw image or an SD card. Both targets have the normal
        FAT 32 boot partition and EXT? root partition.
        The raw image prepends these two partitions with a raw loader
        partition, containing HW-dependent boot stages up to and including
        u-boot. This is done since the boot rom always boots off the internal
        memory; there simply is no point to having a loader partition
        on SD card.
        """
        # boot ROM expects bootloader at 0x20000, which is sector 0x100
        # with the usual SECTOR_SIZE of 0x200.
        # (sector 0 is MBR / partition table)
        loader_start, loader_end, loader_len = align_partition(
            self.SNOWBALL_LOADER_START_S,
            self.LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        boot_start, boot_end, boot_len = align_partition(
            loader_end + 1, self.BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        # we ignore _root_end / _root_len and return an sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, self.ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
            loader_start, loader_len, boot_start, boot_len, root_start)

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        make_uImage(self.load_addr, k_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)
        self.populate_raw_partition(boot_device_or_file, chroot_dir)

    def populate_raw_partition(self, boot_device_or_file, chroot_dir):
        # Populate created raw partition with TOC and startup files.
        _, toc_filename = tempfile.mkstemp()
        config_files_dir = self.snowball_config(chroot_dir)
        new_files = self.get_file_info(chroot_dir, config_files_dir)
        with open(toc_filename, 'wb') as toc:
            self.create_toc(toc, new_files)
        self.install_snowball_boot_loader(toc_filename, new_files,
                                          boot_device_or_file,
                                          self.SNOWBALL_LOADER_START_S,
                                          self.delete_startupfiles)
        self.delete_file(toc_filename)
        if self.delete_startupfiles:
            self.delete_file(os.path.join(config_files_dir,
                                          self.snowball_startup_files_config))

    def snowball_config(self, chroot_dir):
        # We will find the startupfiles in the target boot partition.
        return os.path.join(chroot_dir, 'boot')

    @property
    def delete_startupfiles(self):
        # The startupfiles will have been installed to the target boot
        # partition by the hwpack, and should be deleted so we don't leave
        # them on the target system.
        return True

    def install_snowball_boot_loader(self, toc_file_name, files,
                                     boot_device_or_file, start_sector,
                                     delete_startupfiles=False):
        ''' Copies TOC and boot files into the boot partition.
        A sector size of 1 is used for some files, as they do not
        necessarily start on an even address. '''
        assert os.path.getsize(toc_file_name) <= self.TOC_SIZE
        _dd(toc_file_name, boot_device_or_file, seek=start_sector)

        for file in files:
            # XXX We need checks that these files do not overwrite each
            # other. This code assumes that offset and file sizes are ok.
            filename = file['filename']
            if (file['offset'] % SECTOR_SIZE) != 0:
                seek_bytes = start_sector * SECTOR_SIZE + file['offset']
                _dd(filename, boot_device_or_file, block_size=1,
                    seek=seek_bytes)
            else:
                seek_sectors = start_sector + file['offset'] / SECTOR_SIZE
                _dd(filename, boot_device_or_file, seek=seek_sectors)
            if delete_startupfiles:
                self.delete_file(filename)

    def delete_file(self, file_path):
            cmd = ["rm", "%s" % file_path]
            proc = cmd_runner.run(cmd, as_root=True)
            proc.wait()

    def create_toc(self, f, files):
        ''' Writes a table of contents of the boot binaries.
        Boot rom searches this table to find the binaries.'''
        # Format string means: < little endian,
        # I; unsigned int; offset,
        # I; unsigned int; size,
        # I; unsigned int; flags,
        # i; int; align,
        # i; int; load_address,
        # 12s; string of char; name
        # http://igloocommunity.org/support/index.php/ConfigPartitionOverview
        toc_format = '<IIIii12s'
        for file in files:
            assert len(file['section_name']) < 12, (
                "Section name %s too large" % file['section_name'])
            flags = 0
            load_adress = file['align']
            data = struct.pack(toc_format, file['offset'], file['size'],
                               flags, file['align'], load_adress,
                               file['section_name'])
            f.write(data)

    def get_file_info(self, chroot_dir, config_files_dir):
        ''' Fills in the offsets of files that are located in
        non-absolute memory locations depending on their sizes.'
        Also fills in file sizes'''
        ofs = self.TOC_SIZE
        files = []
        with open(os.path.join(config_files_dir,
                               self.snowball_startup_files_config),
                  'r') as info_file:
            for line in info_file:
                file_data = line.split()
                if len(file_data) == 0:
                    # Line contains only whitespace
                    continue
                if file_data[0][0] == '#':
                    continue
                if file_data[1].startswith('/'):
                    filename = os.path.join(chroot_dir,
                                            file_data[1].lstrip('/'))
                else:
                    filename = os.path.join(config_files_dir, file_data[1])
                assert os.path.exists(filename), "File %s does not exist, " \
                    "please check the startfiles config file." % file_data[1]
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
    def __init__(self):
        super(Mx5Config, self).__init__()
        self.boot_script = 'boot.scr'
        self.mmc_option = '0:2'
        self.mmc_part_offset = 1
        self.serial_tty = 'ttymxc0'
        self._extra_serial_options = 'console=tty0 console=%s,115200n8'
        self._live_serial_options = 'serialtty=%s'

    def get_v1_sfdisk_cmd(self, should_align_boot_part=None):
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
            1, self.LOADER_MIN_SIZE_S, 1, PART_ALIGN_S)

        boot_start, boot_end, boot_len = align_partition(
            loader_end + 1, self.BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)
        # we ignore _root_end / _root_len and return a sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, self.ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
            loader_start, loader_len, boot_start, boot_len, root_start)

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        with self.hardwarepack_handler:
            bootloader_file = self.get_file(
                'bootloader_file',
                default=os.path.join(
                    chroot_dir, 'usr', 'lib', 'u-boot', self.bootloader_flavor,
                    'u-boot.imx'))
            install_mx5_boot_loader(bootloader_file, boot_device_or_file,
                                    self.LOADER_MIN_SIZE_S)
        make_uImage(self.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)
        make_dtb(d_img_data, boot_dir)
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)


class Mx51Config(Mx5Config):
    def __init__(self):
        super(Mx51Config, self).__init__()
        self.dtb_addr = '0x91ff0000'
        self.initrd_addr = '0x92000000'
        self.kernel_addr = '0x90000000'
        self.kernel_flavors = ['linaro-mx51', 'linaro-lt-mx5']
        self.load_addr = '0x90008000'


class Mx53Config(Mx5Config):
    def __init__(self):
        super(Mx53Config, self).__init__()
        # XXX: Is dtb_addr really needed?
        #self.dtb_addr = '0x71ff0000'
        self.initrd_addr = '0x72000000'
        self.kernel_addr = '0x70000000'
        self.kernel_flavors = ['linaro-lt-mx53', 'linaro-lt-mx5']
        self.load_addr = '0x70008000'


class EfikamxConfig(Mx51Config):
    def __init__(self):
        super(EfikamxConfig, self).__init__()
        self.bootloader_flavor = 'efikamx'
        self.dtb_name = 'genesi-efikamx.dtb'


class EfikasbConfig(Mx51Config):
    def __init__(self):
        super(EfikasbConfig, self).__init__()
        self.bootloader_flavor = 'efikasb'
        self.dtb_name = 'genesi-efikasb.dtb'


class Mx51evkConfig(Mx51Config):
    def __init__(self):
        super(Mx51evkConfig, self).__init__()
        self.bootloader_flavor = 'mx51evk'
        self.dtb_name = 'mx51-babbage.dtb'


class Mx53LoCoConfig(Mx53Config):
    def __init__(self):
        super(Mx53LoCoConfig, self).__init__()
        self.bootloader_flavor = 'mx53loco'
        self.dtb_name = 'mx53-loco.dtb'


class VexpressConfig(BoardConfig):
    def __init__(self):
        super(VexpressConfig, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_file_in_boot_part = True
        self.bootloader_flavor = 'ca9x4_ct_vxp'
        # ARM Boot Monitor is used to load u-boot, uImage etc. into flash and
        # only allows for FAT16
        self.fat_size = 16
        self.initrd_addr = '0x62000000'
        self.kernel_addr = '0x60000000'
        self.kernel_flavors = ['linaro-vexpress']
        self.load_addr = '0x60008000'
        self.serial_tty = 'ttyAMA0'
        self._extra_serial_options = 'console=tty0 console=%s,38400n8'
        self._live_serial_options = 'serialtty=%s'

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        make_uImage(self.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)


class VexpressA9Config(VexpressConfig):
    # For now, this is a duplicate of VexpressConfig.
    # In future, there will also be A5 and A15 variants.
    # For all of these, there should never be any V1 hardware packs.
    def __init__(self):
        super(VexpressA9Config, self).__init__()


class GenericConfig(BoardConfig):
    def __init__(self):
        super(GenericConfig, self).__init__()

    def _get_bootcmd(self, i_img_data, d_img_data):
        """Get the bootcmd.

        We override this as we don't do uboot.
        """
        return ""

    def _make_boot_files_v2(self, boot_env, chroot_dir, boot_dir,
                            boot_device_or_file, k_img_data, i_img_data,
                            d_img_data):
        # Rename the kernel image
        if k_img_data is not None:
            k_img = os.path.join(boot_dir,
                                 os.path.basename(k_img_data).split('-')[0])
            cmd_runner.run(["cp", "-v", k_img_data, k_img],
                           as_root=True).wait()
        if i_img_data is not None:
            cmd_runner.run(["cp", "-v", i_img_data, boot_dir],
                           as_root=True).wait()


class FastModelConfig(GenericConfig):
    def __init__(self):
        super(FastModelConfig, self).__init__()
        self.supports_writing_to_mmc = False

    def _make_boot_files_v2(self, boot_env, chroot_dir, boot_dir,
                            boot_device_or_file, k_img_data, i_img_data,
                            d_img_data):
        output_dir = os.path.dirname(boot_device_or_file)

        # There are 2 kinds of models now, VE and Foundation
        bw_ve = _get_file_matching("%s/boot/img.axf" % chroot_dir)
        bw_foundation = _get_file_matching("%s/boot/img-foundation.axf" %
                                           chroot_dir)

        files = [bw_ve, bw_foundation, k_img_data, i_img_data, d_img_data]
        files.extend(glob.glob("%s/fvp/*" % boot_dir))
        files.extend(glob.glob("%s/juno/*" % boot_dir))
        files.extend(glob.glob("%s/boot/initrd.img-*" % chroot_dir))
        for filename in files:
            if filename is not None:
                copy_drop(filename, output_dir)
                cmd_runner.run(["cp", "-v", filename, boot_dir],
                               as_root=True).wait()
        # Rename the kernel image
        if k_img_data is not None:
            k_img_basename = os.path.basename(k_img_data)
            k_img = k_img_basename.split('-')[0]
            cmd_runner.run(["mv", "-v",
                           os.path.join(output_dir, k_img_basename),
                           os.path.join(output_dir, k_img)],
                           as_root=True).wait()
            cmd_runner.run(["mv", "-v",
                           os.path.join(boot_dir, k_img_basename),
                           os.path.join(boot_dir, k_img)],
                           as_root=True).wait()


class SamsungConfig(BoardConfig):
    def __init__(self):
        super(SamsungConfig, self).__init__()
        self._extra_serial_options = None

    def get_v1_sfdisk_cmd(self, should_align_boot_part=False):
        # bootloaders partition needs to hold BL1, U-Boot environment, and BL2
        loaders_min_len = (self.samsung_bl1_start + self.samsung_bl1_len +
                           self.samsung_bl2_len + self.samsung_env_len)

        # bootloaders partition
        loaders_start, loaders_end, loaders_len = align_partition(
            1, loaders_min_len, 1, PART_ALIGN_S)

        # FAT boot partition
        boot_start, boot_end, boot_len = align_partition(
            loaders_end + 1, self.BOOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        # root partition
        # we ignore _root_end / _root_len and return a sfdisk command to
        # instruct the use of all remaining space; XXX if we had some root size
        # config, we could do something more sensible
        root_start, _root_end, _root_len = align_partition(
            boot_end + 1, self.ROOT_MIN_SIZE_S, PART_ALIGN_S, PART_ALIGN_S)

        return '%s,%s,0xDA\n%s,%s,0x0C,*\n%s,,,-' % (
            loaders_start, loaders_len, boot_start, boot_len, root_start)

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        self.install_samsung_boot_loader(
            self._get_samsung_spl(chroot_dir),
            self._get_samsung_bootloader(chroot_dir), boot_device_or_file)
        env_size = self.samsung_env_len * SECTOR_SIZE
        env_file = make_flashable_env(boot_env, env_size)
        _dd(env_file, boot_device_or_file, seek=self.samsung_env_start)

        make_uImage(self.load_addr, k_img_data, boot_dir)
        make_uInitrd(i_img_data, boot_dir)

        # unused at the moment once FAT support enabled for the
        # Samsung u-boot this can be used bug 727978
        boot_script_path = os.path.join(boot_dir, self.boot_script)
        make_boot_script(boot_env, boot_script_path)

    def _get_samsung_spl(self, chroot_dir):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        spl_dir = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', self.bootloader_flavor)
        old_spl_path = os.path.join(spl_dir, 'v310_mmc_spl.bin')
        new_spl_path = os.path.join(spl_dir, 'u-boot-mmc-spl.bin')
        spl_path_origen2 = os.path.join(spl_dir, 'origen-spl.bin')
        spl_path_origen4 = os.path.join(spl_dir, 'origen_quad-spl.bin')
        spl_path_arndale = os.path.join(spl_dir, 'smdk5250-spl.bin')

        spl_file = old_spl_path
        # The new upstream u-boot filename has changed
        if not os.path.exists(spl_file):
            spl_file = new_spl_path

        # upstream u-boot filename for Origen Dual (Exynos 4210)
        if not os.path.exists(spl_file):
            spl_file = spl_path_origen2

        # upstream u-boot filename for Origen Quad (Exynos 4412)
        if not os.path.exists(spl_file):
            spl_file = spl_path_origen4

        # upstream u-boot filename for Arndale (Exynos 5250)
        if not os.path.exists(spl_file):
            spl_file = spl_path_arndale

        if not os.path.exists(spl_file):
            # missing SPL loader
            raise AssertionError("Couldn't find the SPL file, tried %s and %s"
                                 % (old_spl_path, new_spl_path))
        return spl_file

    def _get_samsung_bootloader(self, chroot_dir):
        # XXX: delete this method when hwpacks V1 can die
        assert self.hwpack_format == HardwarepackHandler.FORMAT_1
        bootloader_file = os.path.join(
            chroot_dir, 'usr', 'lib', 'u-boot', self.bootloader_flavor,
            'u-boot.bin')
        return bootloader_file

    def populate_raw_partition(self, boot_device_or_file, chroot_dir):
        # Zero the env so that the boot_script will get loaded
        _dd("/dev/zero", boot_device_or_file, count=self.samsung_env_len,
            seek=self.samsung_env_start)
        # Populate created raw partition with BL1 and u-boot
        spl_file = os.path.join(chroot_dir, 'boot', 'u-boot-mmc-spl.bin')
        assert os.path.getsize(spl_file) <= \
            (self.samsung_bl1_len * SECTOR_SIZE), \
            ("%s is larger than Samsung BL1 size" % spl_file)
        _dd(spl_file, boot_device_or_file, seek=self.samsung_bl1_start)
        uboot_file = os.path.join(chroot_dir, 'boot', 'u-boot.bin')
        assert os.path.getsize(uboot_file) <= \
            (self.samsung_bl2_len * SECTOR_SIZE), \
            ("%s is larger than Samsung BL2 size" % uboot_file)
        _dd(uboot_file, boot_device_or_file, seek=self.samsung_bl2_start)


class SMDKV310Config(SamsungConfig):
    def __init__(self):
        super(SMDKV310Config, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'smdkv310'
        self.initrd_addr = '0x42000000'
        self.kernel_addr = '0x40007000'
        self.kernel_flavors = ['s5pv310']
        self.load_addr = '0x40008000'
        self.mmc_option = '0:2'
        self.mmc_part_offset = 1
        self.serial_tty = 'ttySAC1'
        self._extra_serial_options = 'console=%s,115200n8'

    def _get_boot_env(self, is_live, is_lowmem, consoles, rootfs_id,
                      i_img_data, d_img_data):
        boot_env = super(SamsungConfig, self)._get_boot_env(
            is_live, is_lowmem, consoles, rootfs_id, i_img_data, d_img_data)

        boot_env["ethact"] = "smc911x-0"
        boot_env["ethaddr"] = "00:40:5c:26:0a:5b"

        return boot_env


class OrigenConfig(SamsungConfig):
    def __init__(self):
        super(OrigenConfig, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'origen'
        self.initrd_addr = '0x42000000'
        self.kernel_addr = '0x40007000'
        self.kernel_flavors = ['origen']
        self.load_addr = '0x40008000'
        self.mmc_option = '0:2'
        self.mmc_part_offset = 1
        self.serial_tty = 'ttySAC2'
        self._extra_serial_options = 'console=%s,115200n8'


class OrigenQuadConfig(SamsungConfig):
    def __init__(self):
        super(OrigenQuadConfig, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'origen_quad'
        self.initrd_addr = '0x42000000'
        self.kernel_addr = '0x40007000'
        self.kernel_flavors = ['origen_quad']
        self.load_addr = '0x40008000'
        self.mmc_option = '0:2'
        self.mmc_part_offset = 1
        self.samsung_bl1_len = 48
        self.samsung_bl2_start = 49
        self.samsung_env_start = 1601
        self.serial_tty = 'ttySAC2'
        self._extra_serial_options = 'console=%s,115200n8'

    def populate_raw_partition(self, boot_device_or_file, chroot_dir):
        # Overridden method for Origen Quad board, since the bootloader
        # is now composed of 4 binaries.
        boot_bin_0 = {'name': 'origen_quad.bl1.bin', 'seek': 1}
        boot_bin_1 = {'name': 'origen_quad-spl.bin.signed', 'seek': 31}
        boot_bin_2 = {'name': 'u-boot.bin', 'seek': 63}
        boot_bin_3 = {'name': 'exynos4x12.tzsw.signed.img', 'seek': 761}
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


class ArndaleConfig(SamsungConfig):
    def __init__(self):
        super(ArndaleConfig, self).__init__()
        self.bl0_file = 'lib/firmware/arndale/arndale-bl1.bin'
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'arndale'
        self.kernel_flavors = ['arndale']
        self.mmc_option = '0:2'
        self.mmc_part_offset = 1
        self.samsung_bl0_start = 1
        self.samsung_bl0_len = 16

    def _get_boot_env(self, is_live, is_lowmem, consoles, rootfs_id,
                      i_img_data, d_img_data):
        boot_env = super(SamsungConfig, self)._get_boot_env(
            is_live, is_lowmem, consoles, rootfs_id, i_img_data, d_img_data)

        boot_env["ethact"] = "smc911x-0"
        boot_env["ethaddr"] = "00:40:5c:26:0a:5b"

        return boot_env

    def _make_boot_files_v2(self, boot_env, chroot_dir, boot_dir,
                            boot_device_or_file, k_img_data, i_img_data,
                            d_img_data):
        with self.hardwarepack_handler:
            bl0_file = self._get_samsung_bl0(chroot_dir)
            if self.samsung_bl0_start:
                self._dd_file(bl0_file, boot_device_or_file,
                              self.samsung_bl0_start)

            spl_file = self.get_file('spl_file')
            if self.spl_in_boot_part:
                assert spl_file is not None, (
                    "SPL binary could not be found")
                logger.info(
                    "Copying spl '%s' to boot partition." % spl_file)
                cmd_runner.run(["cp", "-v", spl_file, boot_dir],
                               as_root=True).wait()

            if self.spl_dd:
                self._dd_file(spl_file, boot_device_or_file, self.spl_dd)

            bootloader_file = self.get_file('bootloader_file')
            if self.bootloader_dd:
                self._dd_file(bootloader_file, boot_device_or_file,
                              self.bootloader_dd)

        make_uImage(self.load_addr, k_img_data, boot_dir)

        if i_img_data is not None:
            make_uInitrd(i_img_data, boot_dir)

        if d_img_data is not None:
            make_dtb(d_img_data, boot_dir)

        if self.boot_script is not None:
            boot_script_path = os.path.join(boot_dir, self.boot_script)
            make_boot_script(boot_env, boot_script_path)

            # Only used for Omap, will this be bad for the other boards?
            make_boot_ini(boot_script_path, boot_dir)

        if self.env_dd:
            # Do we need to zero out the env before flashing it?
            _dd("/dev/zero", boot_device_or_file,
                count=self.samsung_env_len,
                seek=self.samsung_env_start)
            env_size = self.samsung_env_len * SECTOR_SIZE
            env_file = make_flashable_env(boot_env, env_size)
            self._dd_file(env_file, boot_device_or_file,
                          self.samsung_env_start)

    def _get_samsung_bl0(self, chroot_dir):
        bl0_file = os.path.join(chroot_dir, self.bl0_file)
        return bl0_file


class ArndaleOctaConfig(ArndaleConfig):
    def __init__(self):
        super(ArndaleOctaConfig, self).__init__()
        self.bl0_file = 'lib/firmware/arndale-octa/arndale-octa.bl1.bin'
        self.tzsw_file = 'lib/firmware/arndale-octa/arndale-octa.tzsw.bin'
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'arndale_octa'
        self.kernel_flavors = ['arndale-octa']
        self.mmc_option = '0:2'
        self.mmc_part_offset = 1
        self.samsung_bl0_start = 1
        self.samsung_bl0_len = 16
        self.samsung_tzsw_start = 719
        self.samsung_tzsw_len = 256

    def _get_boot_env(self, is_live, is_lowmem, consoles, rootfs_id,
                      i_img_data, d_img_data):
        boot_env = super(SamsungConfig, self)._get_boot_env(
            is_live, is_lowmem, consoles, rootfs_id, i_img_data, d_img_data)

        boot_env["bootcmd"] = 'run addmac; %s' % \
                              self._get_bootcmd(i_img_data, d_img_data)
        boot_env["addmac"] = 'setenv bootargs "${bootargs} mac=${ethaddr}"'

        return boot_env

    def _make_boot_files_v2(self, boot_env, chroot_dir, boot_dir,
                            boot_device_or_file, k_img_data, i_img_data,
                            d_img_data):
        with self.hardwarepack_handler:
            bl0_file = self._get_samsung_bl0(chroot_dir)
            if self.samsung_bl0_start:
                self._dd_file(bl0_file, boot_device_or_file,
                              self.samsung_bl0_start)

            spl_file = self.get_file('spl_file')
            if self.spl_in_boot_part:
                assert spl_file is not None, (
                    "SPL binary could not be found")
                logger.info(
                    "Copying spl '%s' to boot partition." % spl_file)
                cmd_runner.run(["cp", "-v", spl_file, boot_dir],
                               as_root=True).wait()

            if self.spl_dd:
                self._dd_file(spl_file, boot_device_or_file, self.spl_dd)

            bootloader_file = self.get_file('bootloader_file')
            if self.bootloader_dd:
                self._dd_file(bootloader_file, boot_device_or_file,
                              self.bootloader_dd)

            tzsw_file = self._get_samsung_tzsw(chroot_dir)
            if self.samsung_tzsw_start:
                self._dd_file(tzsw_file, boot_device_or_file,
                              self.samsung_tzsw_start)

        make_uImage(self.load_addr, k_img_data, boot_dir)

        if i_img_data is not None:
            make_uInitrd(i_img_data, boot_dir)

        if d_img_data is not None:
            make_dtb(d_img_data, boot_dir)

        if self.boot_script is not None:
            boot_script_path = os.path.join(boot_dir, self.boot_script)
            make_boot_script(boot_env, boot_script_path)

            # Only used for Omap, will this be bad for the other boards?
            make_boot_ini(boot_script_path, boot_dir)

        if self.env_dd:
            # Do we need to zero out the env before flashing it?
            _dd("/dev/zero", boot_device_or_file,
                count=self.samsung_env_len,
                seek=self.samsung_env_start)
            env_size = self.samsung_env_len * SECTOR_SIZE
            env_file = make_flashable_env(boot_env, env_size)
            self._dd_file(env_file, boot_device_or_file,
                          self.samsung_env_start)

    def _get_samsung_tzsw(self, chroot_dir):
        tzsw_file = os.path.join(chroot_dir, self.tzsw_file)
        return tzsw_file


class HighBankConfig(BoardConfig):
    def __init__(self):
        super(HighBankConfig, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'highbank'
        self.kernel_flavors = ['highbank']
        self.serial_tty = 'ttyAMA0'
        self.fatload_command = 'ext2load'
        self.load_interface = 'scsi'
        self.bootfs_type = 'ext2'
        self.dtb_addr = '0x00001000'
        self.initrd_addr = '0x01000000'
        self.kernel_addr = '0x00800000'
        self.load_addr = '0x00000000'


class Aa9Config(BoardConfig):
    def __init__(self):
        super(Aa9Config, self).__init__()
        self.boot_script = 'boot.scr'
        self.bootloader_flavor = 'mb8ac0300eb'
        self.kernel_flavors = None
        self._serial_tty = 'ttyS0'
        self.dtb_addr = '0x41000000'
        self.initrd_addr = '0x41100000'
        self.kernel_addr = '0x40000000'
        self.load_addr = '0x40008000'
        self._extra_serial_options = 'console=ttyS0,115200n8'


class I386Config(BoardConfig):
    # define bootloader
    BOOTLOADER_CMD = 'grub-install'
    BOOTLOADER_CFG_FILE = 'grub/grub.cfg'
    BOOTLOADER_CFG = """
    set timeout=3
    set default='0'
    menuentry 'core' {
            linux /%s root=LABEL=rootfs ro %s
            initrd /%s
    }"""

    def __init__(self):
        super(I386Config, self).__init__()
        self.kernel_flavors = ['generic', 'pae']
        self.serial_tty = 'ttyS0'
        self._extra_serial_options = 'console=tty0 console=%s,115200n8'
        self._live_serial_options = 'serialtty=%s'

    def _make_boot_files(self, boot_env, chroot_dir, boot_dir,
                         boot_device_or_file, k_img_data, i_img_data,
                         d_img_data):
        # copy image and init into boot partition
        cmd_runner.run(['cp', k_img_data, boot_dir], as_root=True).wait()
        cmd_runner.run(['cp', i_img_data, boot_dir], as_root=True).wait()

        # create a loop device with the whole image
        device = Device(boot_device_or_file)
        img_size = device.getLength() * SECTOR_SIZE
        img_loop = register_loopback(boot_device_or_file, 0, img_size)

        # install bootloader
        cmd_runner.run([self.BOOTLOADER_CMD,
                        '--boot-directory=%s' % boot_dir,
                        '--modules', 'part_msdos', img_loop],
                       as_root=True).wait()

        # generate loader config file
        loader_config = self.BOOTLOADER_CFG % (os.path.basename(k_img_data),
                                               self.extra_serial_options,
                                               os.path.basename(i_img_data))

        _, tmpfile = tempfile.mkstemp()
        atexit.register(os.unlink, tmpfile)
        with open(tmpfile, 'w') as fd:
            fd.write(loader_config)

        cmd_runner.run(['cp', tmpfile,
                        os.path.join(
                            boot_dir,
                            self.BOOTLOADER_CFG_FILE)], as_root=True).wait()

    def _make_boot_files_v2(self, boot_env, chroot_dir, boot_dir,
                            boot_device_or_file, k_img_data, i_img_data,
                            d_img_data):
        # reuse hwpack v1 function
        self._make_boot_files(boot_env, chroot_dir, boot_dir,
                              boot_device_or_file, k_img_data, i_img_data,
                              d_img_data)


class BoardConfigException(Exception):
    """General board config exception."""


board_configs = {
    'aa9': Aa9Config,
    'arndale': ArndaleConfig,
    'arndale-octa': ArndaleOctaConfig,
    'beagle': BeagleConfig,
    'beaglebone': BeagleBoneConfig,
    'efikamx': EfikamxConfig,
    'efikasb': EfikasbConfig,
    'fastmodel': FastModelConfig,
    'generic': GenericConfig,
    'highbank': HighBankConfig,
    'i386': I386Config,
    'igep': IgepConfig,
    'juno': GenericConfig,
    'mx51evk': Mx51evkConfig,
    'mx53loco': Mx53LoCoConfig,
    'mx6qsabrelite': BoardConfig,
    'origen': OrigenConfig,
    'origen_quad': OrigenQuadConfig,
    'overo': OveroConfig,
    'panda': PandaConfig,
    'smdkv310': SMDKV310Config,
    'snowball_emmc': SnowballEmmcConfig,
    'snowball_sd': SnowballSdConfig,
    'ux500': Ux500Config,
    'vexpress': VexpressConfig,
    'vexpress-a9': VexpressA9Config,
}


def get_board_config(board):
    """Get the board configuration for the specified board.

    :param board: The name of the board to get the configuration of.
    :type board: str
    """
    clazz = board_configs.get(board, None)
    if clazz:
        return clazz()
    else:
        raise BoardConfigException("Board name '%s' has no configuration "
                                   "available." % board)


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
        # TODO: Could ask the user to choose which file to use instead of
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
        'setenv initrd_high "%(initrd_high)s"\n'
        'setenv fdt_high "%(fdt_high)s"\n'
        'setenv bootcmd "%(bootcmd)s"\n'
        'setenv bootargs "%(bootargs)s"\n'
        'boot'
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


def install_mx5_boot_loader(imx_file, boot_device_or_file, loader_min_size):
    # bootloader partition starts at +1s but we write the file at +2s, so we
    # need to check that the bootloader partition minus 1s is at least as large
    # as the u-boot binary; note that the real bootloader partition might be
    # larger than LOADER_MIN_SIZE_S, but if u-boot is larger it's a sign we
    # need to bump LOADER_MIN_SIZE_S
    max_size = (loader_min_size - 1) * SECTOR_SIZE
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


def install_omap_boot_loader(chroot_dir, boot_disk, cls):
    with cls.hardwarepack_handler:
        try:
            default = _get_mlo_file(chroot_dir)
        except AssertionError:
            default = None
        mlo_file = cls.get_file('spl_file', default=default)
        cmd_runner.run(["cp", "-v", mlo_file, boot_disk], as_root=True).wait()


def make_boot_ini(boot_script_path, boot_disk):
    proc = cmd_runner.run(
        ["cp", "-v", boot_script_path, "%s/boot.ini" % boot_disk],
        as_root=True)
    proc.wait()

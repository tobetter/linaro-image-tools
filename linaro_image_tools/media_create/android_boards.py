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
BoardConfig, set appropriate values for its variables and add it to
android_board_configs at the bottom of this file.
"""

from linaro_image_tools.media_create.partitions import SECTOR_SIZE
from linaro_image_tools.media_create.boards import BeagleConfig
from linaro_image_tools.media_create.boards import PandaConfig


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

class AndroidBoardConfig(object):
    @classmethod
    def get_sfdisk_cmd(cls, should_align_boot_part=False):
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
            1, BOOT_MIN_SIZE_S, boot_align, PART_ALIGN_S)
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
 
        return '%s,%s,%s,*\n%s,%s,L\n%s,%s,L\n%s,-,E\n%s,%s,L\n%s,,,-' % (
            boot_start, boot_len, partition_type, system_start, _system_len,
            cache_start, _cache_len, userdata_start, userdata_start,
            _userdata_len, sdcard_start)


class AndroidBeagleConfig(AndroidBoardConfig, BeagleConfig):
    pass

class AndroidPandaConfig(AndroidBoardConfig, PandaConfig):
    pass

android_board_configs = {
    'beagle': AndroidBeagleConfig,
    'panda': AndroidPandaConfig,
    }

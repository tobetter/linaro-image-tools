# Copyright (C) 2010, 2011, 2012 Linaro
#
# Author: Milo Casagrande <milo.casagrande@linaro.org>
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

# This file contains all the valid fields for an hwpack v3.
# Reference wiki page: https://wiki.linaro.org/HardwarePacksV3
#
# Try to keep it alphabetically sorted per section.
#
ARCHITECTURES_FIELD = 'architectures'
ARCHITECTURE_FIELD = 'architecture'
ASSUME_INSTALLED_FIELD = 'assume_installed'
BOARDS_FIELD = 'boards'
BOOTLOADERS_FIELD = 'bootloaders'
BOOT_MIN_SIZE_FIELD = 'boot_min_size'
BOOT_SCRIPT_FIELD = 'boot_script'
COPY_FILES_FIELD = 'copy_files'
DTB_ADDR_FIELD = 'dtb_addr'
DTB_FILE_FIELD = 'dtb_file'
DTB_FILES_FIELD = 'dtb_files'
EXTRA_SERIAL_OPTIONS_FIELD = 'extra_serial_options'
FORMAT_FIELD = 'format'
INCLUDE_DEBS_FIELD = 'include_debs'
INITRD_ADDR_FIELD = 'initrd_addr'
INITRD_FILE_FIELD = 'initrd_file'
KERNEL_ADDR_FIELD = 'kernel_addr'
KERNEL_FILE_FIELD = 'kernel_file'
LOAD_ADDR_FIELD = 'load_addr'
LOADER_MIN_SIZE_FIELD = 'loader_min_size'
LOADER_START_FIELD = 'loader_start'
MAINTAINER_FIELD = 'maintainer'
MMC_ID_FIELD = 'mmc_id'
NAME_FIELD = 'name'
ORIGIN_FIELD = 'origin'
PACKAGES_FIELD = 'packages'
PARTITION_LAYOUT_FIELD = 'partition_layout'
ROOT_MIN_SIZE_FIELD = 'root_min_size'
SERIAL_TTY_FIELD = 'serial_tty'
SOURCES_FIELD = 'sources'
SUPPORT_FIELD = 'support'
WIRED_INTERFACES_FIELD = 'wired_interfaces'
WIRELESS_INTERFACES_FIELD = 'wireless_interfaces'
VERSION_FIELD = 'version'

# Bootloaders specific fields
COPY_FILES_FIELD = 'copy_files'
DD_FIELD = 'dd'
ENV_DD_FIELD = 'env_dd'
EXTRA_BOOT_OPTIONS_FIELD = 'extra_boot_options'
FILE_FIELD = 'file'
IN_BOOT_PART_FIELD = 'in_boot_part'
PACKAGE_FIELD = 'package'
SPL_DD_FIELD = 'spl_dd'
SPL_FILE_FIELD = 'spl_file'
SPL_IN_BOOT_PART_FIELD = 'spl_in_boot_part'
SPL_PACKAGE_FIELD = 'spl_package'

# Samsung fields
SAMSUNG_BL1_LEN_FIELD = 'samsung_bl1_len'
SAMSUNG_BL1_START_FIELD = 'samsung_bl1_start'
SAMSUNG_BL2_LEN_FIELD = 'samsung_bl2_len'
SAMSUNG_BL2_START_FIELD = 'samsung_bl2_start'
SAMSUNG_ENV_LEN_FIELD = 'samsung_env_len'
SAMSUNG_ENV_START_FIELD = 'samsung_env_start'

# Snowball fields
SNOWBALL_STARTUP_FILES_CONFIG_FIELD = 'snowball_startup_files_config'

# Fields that might be necessary for the metadata file
METADATA_ARCH_FIELD = 'architecture'
METADATA_VERSION_FIELD = 'version'

# The allowed partition layouts.
BOOTFS16 = 'bootfs16_rootfs'
BOOTFS = 'bootfs_rootfs'
RESERVED_BOOTFS = 'reserved_bootfs_rootfs'

DEFINED_PARTITION_LAYOUTS = [
    BOOTFS16,
    BOOTFS,
    RESERVED_BOOTFS,
]

# Supported bootloaders
U_BOOT = 'u_boot'
UEFI = 'uefi'
DEFAULT_BOOTLOADER = U_BOOT

# Define where fields are valid, so we can test them.
# If a key has a value None, this indicates there is either a value or
#  list of values that can be associated with it.
# If a key contains a dictionary, this means that the key can
#  contain a dictionary.
# The string "root" indicates that the key can contain the root
#  structure. This is used for the boards section, where each
#  board can contain the full or partial layout, overwriting the global
#  settings.
hwpack_v3_layout = {
    FORMAT_FIELD: None,
    NAME_FIELD: None,
    ARCHITECTURES_FIELD: None,
    ORIGIN_FIELD: None,
    MAINTAINER_FIELD: None,
    SUPPORT_FIELD: None,
    ASSUME_INSTALLED_FIELD: None,
    INCLUDE_DEBS_FIELD: None,
    DTB_FILE_FIELD: None,
    DTB_FILES_FIELD: None,
    DTB_ADDR_FIELD: None,
    SERIAL_TTY_FIELD: None,
    EXTRA_SERIAL_OPTIONS_FIELD: None,
    MMC_ID_FIELD: None,
    PACKAGES_FIELD: None,
    PARTITION_LAYOUT_FIELD: None,
    KERNEL_FILE_FIELD: None,
    KERNEL_ADDR_FIELD: None,
    INITRD_FILE_FIELD: None,
    INITRD_ADDR_FIELD: None,
    LOAD_ADDR_FIELD: None,
    BOOT_SCRIPT_FIELD: None,
    LOADER_START_FIELD: None,
    WIRED_INTERFACES_FIELD: None,
    WIRELESS_INTERFACES_FIELD: None,
    BOOT_MIN_SIZE_FIELD: None,
    ROOT_MIN_SIZE_FIELD: None,
    LOADER_MIN_SIZE_FIELD: None,
    SAMSUNG_BL1_LEN_FIELD: None,
    SAMSUNG_BL1_START_FIELD: None,
    SAMSUNG_ENV_LEN_FIELD: None,
    SAMSUNG_ENV_START_FIELD: None,
    SAMSUNG_BL2_LEN_FIELD: None,
    SAMSUNG_BL2_START_FIELD: None,
    SNOWBALL_STARTUP_FILES_CONFIG_FIELD: None,
    SOURCES_FIELD: None,
    BOOTLOADERS_FIELD: {
        "*":
        {
            PACKAGE_FIELD: None,
            FILE_FIELD: None,
            IN_BOOT_PART_FIELD: None,
            COPY_FILES_FIELD: None,
            DD_FIELD: None,
            EXTRA_BOOT_OPTIONS_FIELD: None,
            SPL_PACKAGE_FIELD: None,
            SPL_FILE_FIELD: None,
            SPL_IN_BOOT_PART_FIELD: None,
            SPL_DD_FIELD: None,
            ENV_DD_FIELD: None,
        }
    },
    BOARDS_FIELD: "root",
}

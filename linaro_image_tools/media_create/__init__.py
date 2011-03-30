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

import argparse

from linaro_image_tools.media_create.boards import board_configs


KNOWN_BOARDS = board_configs.keys()


class Live256MegsAction(argparse.Action):
    """A custom argparse.Action for the --live-256m option.

    It is a store_true action for the given dest plus a store_true action for
    'is_live'.
    """

    def __init__(self, option_strings, dest, default=None, required=False,
                 help=None, metavar=None):
        super(Live256MegsAction, self).__init__(
            option_strings=option_strings, dest=dest, nargs=0,
            default=False, required=required, help=help)

    def __call__(self, parser, namespace, values, option_string=None):
        setattr(namespace, self.dest, True)
        setattr(namespace, 'is_live', True)


def get_args_parser():
    """Get the ArgumentParser for the arguments given on the command line."""
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--mmc', dest='device', help='The storage device to use.')
    group.add_argument(
        '--image_file', dest='device',
        help='File where we should write the QEMU image.')
    parser.add_argument(
        '--dev', required=True, dest='board', choices=KNOWN_BOARDS,
        help='Generate an SD card or image for the given board.')
    parser.add_argument(
        '--rootfs', default='ext3', choices=['ext2', 'ext3', 'ext4', 'btrfs'],
        help='Type of filesystem to use for the rootfs')
    parser.add_argument(
        '--rfs_label', default='rootfs',
        help='Label to use for the root filesystem.')
    parser.add_argument(
        '--boot_label', default='boot',
        help='Label to use for the boot filesystem.')
    parser.add_argument(
        '--swap_file', type=int,
        help='Create a swap file of the given size (in MBs).')
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--live', dest='is_live', action='store_true',
        help=('Create boot command for casper/live images; if this is not '
              'provided the UUID for the rootfs is used as the root= option'))
    group.add_argument(
        '--live-256m', dest='is_lowmem', action=Live256MegsAction,
        help=('Create boot command for casper/live images; adds '
              'only-ubiquity option to allow use of live installer on '
              'boards with 256M memory - like beagle.'))
    parser.add_argument(
        '--console', action='append', dest='consoles', default=[],
        help=('Add a console to kernel boot parameter; this parameter can be '
              'defined multiple times.'))
    parser.add_argument(
        '--hwpack', action='append', dest='hwpacks', required=True,
        help=('A hardware pack that should be installed in the rootfs; this '
              'parameter can be defined multiple times.'))
    parser.add_argument(
        '--hwpack-force-yes', action='store_true',
        help='Pass --force-yes to linaro-hwpack-install')
    parser.add_argument(
        '--image_size', default='2G',
        help=('The image size, specified in mega/giga bytes (e.g. 3000M or '
              '3G); use with --image_file only'))
    parser.add_argument(
        '--binary', default='binary-tar.tar.gz', required=True,
        help=('The tarball containing the rootfs used to create the bootable '
              'system.'))
    parser.add_argument(
        '--no-rootfs', dest='should_format_rootfs', action='store_false',
        help='Do not deploy the root filesystem.')
    parser.add_argument(
        '--no-bootfs', dest='should_format_bootfs', action='store_false',
        help='Do not deploy the boot filesystem.')
    parser.add_argument(
        '--no-part', dest='should_create_partitions', action='store_false',
        help='Reuse existing partitions on the given media.')
    parser.add_argument(
        '--align-boot-part', dest='should_align_boot_part',
        action='store_true',
        help='Align boot partition too (might break older x-loaders).')
    return parser

def get_android_args_parser():
    """Get the ArgumentParser for the arguments given on the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '--mmc', required=True, dest='device', help='The storage device to use.')
    parser.add_argument(
        '--dev', required=True, dest='board', choices=KNOWN_BOARDS,
        help='Generate an SD card or image for the given board.')
    parser.add_argument(
        '--rootfs', default='ext4', choices=['ext3', 'ext4'],
        help='Type of filesystem to use for the rootfs')
    parser.add_argument(
        '--rfs_label', default='rootfs',
        help='Label to use for the root filesystem.')
    parser.add_argument(
        '--boot_label', default='boot',
        help='Label to use for the boot filesystem.')

    parser.add_argument(
        '--system', default='system.tar.bz2', required=True,
        help=('The tarball containing the Android system paritition'))
    parser.add_argument(
        '--userdata', default='userdata.tar.bz2', required=True,
        help=('The tarball containing the Android data paritition'))
    parser.add_argument(
        '--root', default='root.tar.bz2', required=True,
        help=('The tarball containing the Android root partition'))

    parser.add_argument(
        '--no-rootfs', dest='should_format_rootfs', action='store_false',
        help='Do not deploy the root filesystem.')
    parser.add_argument(
        '--no-bootfs', dest='should_format_bootfs', action='store_false',
        help='Do not deploy the boot filesystem.')
    parser.add_argument(
        '--no-part', dest='should_create_partitions', action='store_false',
        help='Reuse existing partitions on the given media.')
    parser.add_argument(
        '--align-boot-part', dest='should_align_boot_part',
        action='store_true',
        help='Align boot partition too (might break older x-loaders).')
    return parser

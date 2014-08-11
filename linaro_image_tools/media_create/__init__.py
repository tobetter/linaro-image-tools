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
import subprocess
import os

from linaro_image_tools import cmd_runner
from linaro_image_tools.media_create.boards import board_configs
from linaro_image_tools.media_create.android_boards import (
    android_board_configs)
from linaro_image_tools.__version__ import __version__
from linaro_image_tools.hwpack.hwpack_fields import (
    DEFAULT_BOOTLOADER
)


KNOWN_BOARDS = sorted(board_configs.keys())
ANDROID_KNOWN_BOARDS = sorted(android_board_configs.keys())


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


def get_version():
    qemu_path = '/usr/bin/qemu-arm-static'
    p = cmd_runner.run(["head", "-n", "1"],
                       stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    if os.path.exists(qemu_path):
        try:
            # qemu-arm-static has no --version option so it fails,
            # but still prints its version plus usage
            cmd_runner.run(["/usr/bin/qemu-arm-static", "--version"],
                           stdout=p.stdin).communicate()
            p.communicate()
        except:
            qemu_version = p.stdout.read()
    else:
        qemu_version = "Cannot find %s." % qemu_path
    return "%s\n: %s" % (__version__, qemu_version)


def add_common_options(parser):
    parser.add_argument(
        '--extra-boot-args', dest='extra_boot_args', required=False,
        help='Extra boot args.')
    parser.add_argument(
        '--extra-boot-args-file', dest='extra_boot_args_file',
        required=False, help=('File containing extra boot arguments.'))
    parser.add_argument("--debug", action="store_true")


def get_args_parser():
    """Get the ArgumentParser for the arguments given on the command line."""
    parser = argparse.ArgumentParser(version='%(prog)s ' + get_version())
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        '--mmc', dest='device', default="sd.img",
        help='The storage device to use.')
    group.add_argument(
        '--image-file', '--image_file', dest='device', default="sd.img",
        help='File where we should write an image file (defaults to sd.img '
             'if neither --image-file or --mmc are specified.)')
    parser.add_argument(
        '--output-directory', dest='directory',
        help='Directory where image and accessories should be written to.')
    parser.add_argument(
        '--read-hwpack', dest='readhwpack', action='store_true',
        help=('Read the hardware pack and print information about the '
              'supported boards and bootloaders.'))
    parser.add_argument(
        '--dev', dest='dev', choices=KNOWN_BOARDS,
        help='Generate an SD card or image for the given board.')
    parser.add_argument(
        '--part-table', default='mbr', choices=['mbr', 'gpt'],
        help='Type of partition table to use for the MMC image')
    parser.add_argument(
        '--rootfs', default='ext4', choices=['ext2', 'ext3', 'ext4', 'btrfs'],
        help='Type of filesystem to use for the rootfs')
    parser.add_argument(
        '--rfs-label', '--rfs_label', default='rootfs',
        help='Label to use for the root filesystem.')
    parser.add_argument(
        '--boot-label', '--boot_label', default='boot',
        help='Label to use for the boot filesystem.')
    parser.add_argument(
        '--swap-file', '--swap_file', type=int,
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
        '--hwpack-sig', action='append', dest='hwpacksigs', required=False,
        default=[],
        help=('Signature file for verifying a hwpack; this '
              'parameter can be defined multiple times.'))
    parser.add_argument(
        '--hwpack-force-yes', action='store_true',
        help='Pass --force-yes to linaro-hwpack-install')
    parser.add_argument(
        '--image-size', '--image_size', default='3G',
        help=('The image size, specified in mega/giga bytes (e.g. 3000M or '
              '3G); use with --image_file only'))
    parser.add_argument(
        '--binary', default='binary-tar.tar.gz', required=False,
        help=('The tarball containing the rootfs used to create the bootable '
              'system.'))
    parser.add_argument(
        '--binary-sig', dest='binarysig', required=False,
        help=('Signature file used for verifying the binary tarball.'))
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
    parser.add_argument(
        '--nocheck-mmc', dest='nocheck_mmc',
        action='store_true',
        help=('Assume yes to the question "Are you 100%% sure, '
              'on selecting [mmc]"'))
    parser.add_argument(
        '--bootloader',
        help="Select a bootloader from a hardware pack that contains more "
             "than one. If not specified, it will default to '%s'." %
             DEFAULT_BOOTLOADER)
    parser.add_argument(
        '--dtb-file',
        help="Select a DTB file from a hardware pack that contains more "
             "than one. If not specified, it will default to the first "
             "entry in 'dtb_files' list.")

    add_common_options(parser)
    return parser


def get_android_args_parser():
    """Get the ArgumentParser for the arguments given on the command line."""
    parser = argparse.ArgumentParser(version='%(prog)s ' + get_version())
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--mmc', dest='device', help='The storage device to use.')
    group.add_argument(
        '--image-file', '--image_file', dest='device',
        help='File where we should write the image file.')
    parser.add_argument(
        '--hwpack', required=False,
        help=('An Android hardware pack file with the board configuration.'))
    parser.add_argument(
        '--image-size', '--image_size', default='2G',
        help=('The image size, specified in mega/giga bytes (e.g. 3000M or '
              '3G); use with --image_file only'))
    parser.add_argument(
        '--dev', required=True, dest='dev', choices=ANDROID_KNOWN_BOARDS,
        help='Generate an SD card or image for the given board.')
    parser.add_argument(
        '--boot-label', '--boot_label', default='boot',
        help='Label to use for the boot filesystem.')
    parser.add_argument(
        '--console', action='append', dest='consoles', default=[],
        help=('Add a console to kernel boot parameter; this parameter can be '
              'defined multiple times.'))

    #group for system partition content specification
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--system', dest="system",
        help=('The tarball containing the Android system paritition.'
              'Like system.tar.bz2'))
    group.add_argument(
        '--systemimage', dest="systemimage",
        help=('The ext4 filesystem data file containing the Android '
              'system paritition. Like system.img'))

    #group for userdata partition content specification
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--userdata', dest="userdata",
        help=('The tarball containing the Android data paritition.'
              'Like userdata.tar.bz2'))
    group.add_argument(
        '--userdataimage', dest="userdataimage",
        help=('The ext4 filesystem data containing the Android '
              'data paritition. Like userdata.img'))

    parser.add_argument(
        '--boot', default='boot.tar.bz2', required=True,
        help=('The tarball containing the Android root partition'))
    parser.add_argument(
        '--no-part', dest='should_create_partitions', action='store_false',
        help='Reuse existing partitions on the given media.')
    parser.add_argument(
        '--align-boot-part', dest='should_align_boot_part',
        action='store_true',
        help='Align boot partition too (might break older x-loaders).')
    add_common_options(parser)
    return parser

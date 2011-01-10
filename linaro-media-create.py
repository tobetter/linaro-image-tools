#!/usr/bin/env python

import atexit
import os
import sys
import tempfile

from media_create import cmd_runner
from media_create.check_device import (
    confirm_device_selection_and_ensure_it_is_ready)
from media_create.ensure_command import ensure_command
from media_create.hwpack import install_hwpacks
from media_create.partitions import (
    Media,
    setup_partitions,
    )
from media_create.populate_boot import populate_boot
from media_create.remove_binary_dir import remove_dir
from media_create.rootfs import populate_rootfs
from media_create.unpack_binary_tarball import unpack_binary_tarball
from media_create import (
    get_args_parser,
    get_board_config,
    ROOTFS_UUID,
    )


TMP_DIR = tempfile.mkdtemp()
ROOTFS_DIR = os.path.join(TMP_DIR, 'binary')
BOOT_DISK = os.path.join(TMP_DIR, 'boot-disc')
ROOT_DISK = os.path.join(TMP_DIR, 'root-disc')


# TODO: Play tricks with PYTHONPATH to make it possible to run this off of a
# dev tree.

# Registered as the first atexit handler as we want this to be the last
# handler to execute.
@atexit.register
def cleanup():
    # Just in case anything is left behind.
    # umount boot/root filesystems, swallowing errors.
    try:
        cmd_runner.run(['umount', BOOT_DISK], as_root=True).wait()
        cmd_runner.run(['umount', ROOT_DISK], as_root=True).wait()
        # Remove TMP_DIR as root because some files written there are
        # owned by root.
        cmd_runner.run(['rm', '-rf', TMP_DIR], as_root=True).wait()
    except cmd_runner.SubcommandNonZeroReturnValue:
        pass


def ensure_required_commands(args):
    required_commands = [
        ('sfdisk', 'util-linux'),
        ('fdisk', 'util-linux'),
        ('mkimage', 'uboot-mkimage'),
        ('uuidgen', 'uuid-runtime'),
        ('parted', 'parted'),
        ]
    if args.rootfs in ['ext2', 'ext3', 'ext4']:
        required_commands.append(('mkfs.%s' % args.rootfs, 'e2fsprogs'))
    else:
        required_commands.append(('mkfs.btrfs', 'btrfs-tools'))
    for command, package in required_commands:
        ensure_command(command, package)


if __name__ == '__main__':
    parser = get_args_parser()
    args = parser.parse_args()
    board_config = get_board_config(args)

    if not confirm_device_selection_and_ensure_it_is_ready(args.device):
        sys.exit(1)

    media = Media(args.device)
    if (not media.is_block_device
        and (not args.should_format_rootfs or not args.should_format_bootfs)):
        print ("Do not use --no-boot or --no-part in conjunction with "
               "--image_file.")
        sys.exit(1)

    # TODO: Combine these two into a single function.
    remove_dir(ROOTFS_DIR)
    unpack_binary_tarball(args.binary, TMP_DIR)

    hwpacks = args.hwpacks
    if hwpacks is None:
        print ("Warning: no hwpack specified; the result is unlikely to be "
               "functional")
        sys.exit(1)
    else:
        install_hwpacks(ROOTFS_DIR, args.hwpack_force_yes, hwpacks)

    boot_partition, root_partition = setup_partitions(
        args.board, media, board_config['fat_size'], args.image_size,
        args.boot_label, args.rfs_label, args.rootfs, ROOTFS_UUID,
        args.should_create_partitions,
        args.should_format_bootfs, args.should_format_rootfs)

    if args.should_format_bootfs:
        populate_boot(
            args.board, board_config, ROOTFS_DIR, boot_partition, BOOT_DISK,
            args.device, TMP_DIR, args.is_live)

    if args.should_format_rootfs:
        create_swap = False
        if args.swap_file is not None:
            create_swap = True
        populate_rootfs(ROOTFS_DIR, ROOT_DISK, root_partition, args.rootfs,
            ROOTFS_UUID, create_swap, str(args.swap_file),
            board_config['mmc_part_offset'])

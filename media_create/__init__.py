import argparse
import uuid

ROOTFS_UUID = str(uuid.uuid4())
KNOWN_BOARDS = ['beagle', 'igep', 'mx51evk', 'panda', 'ux500', 'vexpress']


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
    # TODO: Must group these two as a mutually exclusive group and create a
    # custom Action that stores both is_live and is_lowmem in the case of
    # --live-256m
    parser.add_argument(
        '--live', dest='is_live', action='store_true',
        help=('Create boot command for casper/live images; if this is not '
              'provided a UUID for the rootfs is generated and used as the '
              'root= option'))
    parser.add_argument(
        '--live-256m', dest='is_live', action='store_true',
        help=('Create boot command for casper/live images; adds '
              'only-ubiquity option to allow use of live installer on '
              'boards with 256M memory - like beagle.'))
    parser.add_argument(
        '--console', action='append', dest='consoles',
        help=('Add a console to kernel boot parameter; this parameter can be '
              'defined multiple times.'))
    parser.add_argument(
        '--hwpack', action='append', dest='hwpacks',
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
        '--binary', default='binary-tar.tar.gz',
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
    return parser


def get_board_config(args):
    """Return a dict containing the configs to create an image for a board.

    :param args: An argparse.ArgumentParser object containing the arguments
        passed to linaro-media-create.
    """
    mmc_part_offset = 0
    mmc_option = '0:1'
    boot_args_options = 'rootwait ro'
    uboot_flavor = None
    fat_size = 32
    board = args.board
    assert board in KNOWN_BOARDS
    is_live = args.is_live
    serial_opts = ''
    if args.consoles is not None:
        for console in args.consoles:
            serial_opts += ' console=%s' % console

        # XXX: I think this is not needed as we have board-specific
        # serial options for when is_live is true.
        if args.is_live:
            serial_opts += ' serialtty=ttyS2'

    if board in ('beagle', 'igep'):
        if board == 'beagle':
            uboot_flavor = 'omap3_beagle'
        serial_opts += ' console=tty0 console=ttyS2,115200n8'
        live_serial_opts = 'serialtty=ttyS2'
        kernel_addr = '0x80000000'
        initrd_addr = '0x81600000'
        load_addr = '0x80008000'
        sub_arch = 'linaro-omap'
        boot_script = 'boot.scr'
        boot_args_options += (
            ' earlyprintk fixrtc nocompcache vram=12M omapfb.debug=y'
            ' omapfb.mode=dvi:1280x720MR-16@60')

    elif board == 'panda':
        uboot_flavor = 'omap4_panda'
        serial_opts += ' console = tty0 console = ttyO2,115200n8'
        live_serial_opts = 'serialtty = ttyO2'
        kernel_addr = '0x80200000'
        initrd_addr = '0x81600000'
        load_addr = '0x80008000'
        sub_arch = 'omap4'
        boot_script = 'boot.scr'
        boot_args_options += (
            ' earlyprintk fixrtc nocompcache vram = 32M omapfb.debug = y'
            ' omapfb.vram = 0:8M mem = 463M ip = none')

    elif board == 'ux500':
        serial_opts += ' console = tty0 console = ttyAMA2,115200n8'
        live_serial_opts = 'serialtty = ttyAMA2'
        kernel_addr = '0x00100000'
        initrd_addr = '0x08000000'
        load_addr = '0x00008000'
        sub_arch = 'ux500'
        boot_script = 'flash.scr'
        boot_args_options += (
            ' earlyprintk rootdelay = 1 fixrtc nocompcache'
            ' mem = 96M@0 mem_modem = 32M@96M mem = 44M@128M pmem = 22M@172M'
            ' mem = 30M@194M mem_mali = 32M@224M pmem_hwb = 54M@256M'
            ' hwmem = 48M@302M mem = 152M@360M')
        mmc_option = '1:1'

    elif board == 'mx51evk':
        serial_opts += ' console = tty0 console = ttymxc0,115200n8'
        live_serial_opts = 'serialtty = ttymxc0'
        kernel_addr = '0x90000000'
        initrd_addr = '0x90800000'
        load_addr = '0x90008000'
        sub_arch = 'linaro-mx51'
        boot_script = 'boot.scr'
        mmc_part_offset = 1
        mmc_option = '0:2'

    elif board == 'vexpress':
        uboot_flavor = 'ca9x4_ct_vxp'
        serial_opts += ' console = tty0 console = ttyAMA0,38400n8'
        live_serial_opts = 'serialtty = ttyAMA0'
        kernel_addr = '0x60008000'
        initrd_addr = '0x81000000'
        load_addr = kernel_addr
        sub_arch = 'linaro-vexpress'
        # ARM Boot Monitor is used to load u-boot, uImage etc. into flash and
        # only allows for FAT16
        fat_size = 16

    else:
        raise ValueError("Unkown board: %s" % board)

    lowmem_opt = ''
    boot_snippet = 'root=UUID=%s' % ROOTFS_UUID
    if args.is_live:
        serial_opts += ' %s' % live_serial_opts
        boot_snippet = 'boot=casper'
        if args.is_lowmem:
            lowmem_opt = 'only-ubiquity'

    boot_cmd = (
        "setenv bootcmd 'fatload mmc %(mmc_option)s %(kernel_addr)s "
            "uImage; fatload mmc %(mmc_option)s %(initrd_addr)s uInitrd; "
            "bootm %(kernel_addr)s %(initrd_addr)s'\n"
        "setenv bootargs '%(serial_opts)s %(lowmem_opt)s "
            "%(boot_snippet)s %(boot_args_options)s'\n"
        "boot" % vars())

    # Instead of constructing a dict here, we could create a separate class
    # for the config of every board, with the varying bits stored as class
    # variables. At this point I don't see much advantage in doing that,
    # though.
    return dict(
        kernel_addr=kernel_addr, initrd_addr=initrd_addr, load_addr=load_addr,
        sub_arch=sub_arch, boot_script=boot_script, fat_size=fat_size,
        boot_args_options=boot_args_options, serial_opts=serial_opts,
        uboot_flavor=uboot_flavor, mmc_part_offset=mmc_part_offset,
        mmc_option=mmc_option, boot_cmd=boot_cmd)

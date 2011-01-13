"""Configuration for boards supported by linaro-media-create.

To add support for a new board, you just need to create a subclass of
BoardConfig and set appropriate values for its variables.
"""

import uuid

ROOTFS_UUID = str(uuid.uuid4())


class BoardConfig(object):
    """The configuration used when building an image for a board."""
    uboot_flavor = None
    mmc_option = '0:1'
    mmc_part_offset = 0
    extra_serial_opts = None
    live_serial_opts = None
    kernel_addr = None
    initrd_addr = None
    load_addr = None
    sub_arch = None
    boot_script = None
    extra_boot_args_options = None
    fat_size = 32

    @classmethod
    def get_boot_cmd(cls, is_live, is_lowmem, consoles):
        """Get the boot command for this board."""
        boot_args_options = 'rootwait ro'
        if cls.extra_boot_args_options:
            boot_args_options += " %s" % cls.extra_boot_args_options
        serial_opts = ''
        if consoles is not None:
            for console in consoles:
                serial_opts += ' console=%s' % console

            # XXX: I think this is not needed as we have board-specific
            # serial options for when is_live is true.
            if is_live:
                serial_opts += ' serialtty=ttyS2'

        serial_opts += ' %s' % cls.extra_serial_opts

        lowmem_opt = ''
        boot_snippet = 'root=UUID=%s' % ROOTFS_UUID
        if is_live:
            serial_opts += ' %s' % cls.live_serial_opts
            boot_snippet = 'boot=casper'
            if is_lowmem:
                lowmem_opt = 'only-ubiquity'

        replacements = dict(
            mmc_option=cls.mmc_option, kernel_addr=cls.kernel_addr,
            initrd_addr=cls.initrd_addr, serial_opts=serial_opts,
            lowmem_opt=lowmem_opt, boot_snippet=boot_snippet,
            boot_args_options=boot_args_options)
        return (
            "setenv bootcmd 'fatload mmc %(mmc_option)s %(kernel_addr)s "
                "uImage; fatload mmc %(mmc_option)s %(initrd_addr)s uInitrd; "
                "bootm %(kernel_addr)s %(initrd_addr)s'\n"
            "setenv bootargs '%(serial_opts)s %(lowmem_opt)s "
                "%(boot_snippet)s %(boot_args_options)s'\n"
            "boot" % replacements)


class BeagleConfig(BoardConfig):
    uboot_flavor = 'omap3_beagle'
    extra_serial_opts = 'console=tty0 console=ttyS2,115200n8'
    live_serial_opts = 'serialtty=ttyS2'
    kernel_addr = '0x80000000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    sub_arch = 'linaro-omap'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram=12M omapfb.debug=y '
        'omapfb.mode=dvi:1280x720MR-16@60')


class PandaConfig(BoardConfig):
    uboot_flavor = 'omap4_panda'
    extra_serial_opts = 'console = tty0 console = ttyO2,115200n8'
    live_serial_opts = 'serialtty = ttyO2'
    kernel_addr = '0x80200000'
    initrd_addr = '0x81600000'
    load_addr = '0x80008000'
    sub_arch = 'omap4'
    boot_script = 'boot.scr'
    extra_boot_args_options = (
        'earlyprintk fixrtc nocompcache vram = 32M omapfb.debug = y '
        'omapfb.vram = 0:8M mem = 463M ip = none')


class IgepConfig(BeagleConfig):
    uboot_flavor = None


class Ux500Config(BoardConfig):
    extra_serial_opts = 'console = tty0 console = ttyAMA2,115200n8'
    live_serial_opts = 'serialtty = ttyAMA2'
    kernel_addr = '0x00100000'
    initrd_addr = '0x08000000'
    load_addr = '0x00008000'
    sub_arch = 'ux500'
    boot_script = 'flash.scr'
    extra_boot_args_options = (
        'earlyprintk rootdelay = 1 fixrtc nocompcache '
        'mem = 96M@0 mem_modem = 32M@96M mem = 44M@128M pmem = 22M@172M '
        'mem = 30M@194M mem_mali = 32M@224M pmem_hwb = 54M@256M '
        'hwmem = 48M@302M mem = 152M@360M')
    mmc_option = '1:1'


class Mx51evkConfig(BoardConfig):
    extra_serial_opts = 'console = tty0 console = ttymxc0,115200n8'
    live_serial_opts = 'serialtty = ttymxc0'
    kernel_addr = '0x90000000'
    initrd_addr = '0x90800000'
    load_addr = '0x90008000'
    sub_arch = 'linaro-mx51'
    boot_script = 'boot.scr'
    mmc_part_offset = 1
    mmc_option = '0:2'


class VexpressConfig(BoardConfig):
    uboot_flavor = 'ca9x4_ct_vxp'
    extra_serial_opts = 'console = tty0 console = ttyAMA0,38400n8'
    live_serial_opts = 'serialtty = ttyAMA0'
    kernel_addr = '0x60008000'
    initrd_addr = '0x81000000'
    load_addr = kernel_addr
    sub_arch = 'linaro-vexpress'
    boot_script = None
    # ARM Boot Monitor is used to load u-boot, uImage etc. into flash and
    # only allows for FAT16
    fat_size = 16


board_configs = {
    'beagle': BeagleConfig,
    'igep': IgepConfig,
    'panda': PandaConfig,
    'vexpress': VexpressConfig,
    'ux500': Ux500Config,
    'mx51evk': Mx51evkConfig,
    }

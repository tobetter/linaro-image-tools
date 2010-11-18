import sys


def create_boot_cmd(is_live, is_lowmem, mmc_option, root_uuid, kernel_addr,
                    initrd_addr, serial_opts, boot_args_options,
                    splash_opts=""):
    boot_snippet = 'root=UUID=%s' % root_uuid
    lowmem_opt = ''
    if is_live:
        boot_snippet = 'boot=casper'
        if is_lowmem:
            lowmem_opt = 'only-ubiquity'

    return ("setenv bootcmd 'fatload mmc %(mmc_option)s %(kernel_addr)s "
                "uImage; fatload mmc %(mmc_option)s %(initrd_addr)s uInitrd; "
                "bootm %(kernel_addr)s %(initrd_addr)s'\n"
            "setenv bootargs '%(serial_opts)s %(splash_opts)s %(lowmem_opt)s "
                "%(boot_snippet)s %(boot_args_options)s'\n"
            "boot" % vars())


if __name__ == '__main__':
    is_live = int(sys.argv[1])
    is_lowmem = int(sys.argv[2])
    # Use sys.stdout.write() to avoid the trailing newline added by print.
    sys.stdout.write(create_boot_cmd(is_live, is_lowmem, *sys.argv[3:]))

from media_create import cmd_runner


def unpack_binary_tarball(tarball, unpack_dir, as_root=True):
    proc = cmd_runner.run(
        ['tar', '--numeric-owner', '-C', unpack_dir, '-xf', tarball],
        as_root=as_root)
    proc.wait()
    return proc.returncode

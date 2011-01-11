import os.path

from media_create import cmd_runner


def remove_dir(directory, as_root=True):
    if os.path.exists(directory):
        proc = cmd_runner.run(['rm', '-rf', directory], as_root=as_root)
        proc.wait()
        return proc.returncode
    return 0

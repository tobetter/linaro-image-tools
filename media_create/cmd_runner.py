import subprocess


def run(command, shell=False, as_root=False):
    """Run the given command as a sub process.

    :param command: A list, tuple or string with the command to run.
    :param shell: Should the given command be run in a shell?
    :param as_root: Should the given command be run as root (with sudo)?
    """
    if isinstance(command, (list, tuple)):
        command = " ".join(command)
    assert isinstance(command, basestring), (
        "The command to run must be a list, tuple or string, found: %s"
        % type(command))
    # TODO: We might want to always use 'sudo -E' here to avoid problems like
    # https://launchpad.net/bugs/673570
    if as_root:
        command = "sudo %s" % command
    # XXX: Should we raise an error when the return code is not 0, so that it
    # behaves like the original shell script which was run with 'set -e'?
    return do_run(command, shell=shell)


def do_run(command, shell):
    proc = subprocess.Popen(command, shell=shell)
    proc.wait()
    return proc.returncode

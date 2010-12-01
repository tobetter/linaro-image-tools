import subprocess


def run(args, as_root=False):
    """Run the given command as a sub process.

    :param command: A list or tuple containing the command to run and the
                    arguments that should be passed to it.
    :param as_root: Should the given command be run as root (with sudo)?
    """
    assert isinstance(args, (list, tuple)), (
        "The command to run must be a list or tuple, found: %s" % type(args))
    # TODO: We might want to always use 'sudo -E' here to avoid problems like
    # https://launchpad.net/bugs/673570
    if as_root:
        args = args[:]
        args.insert(0, 'sudo')
    return_value = do_run(args)
    if return_value != 0:
        raise SubcommandNonZeroReturnValue(args, return_value)
    return return_value


def do_run(args):
    """A wrapper around subprocess.call() to make testing easier."""
    return subprocess.call(args)


class SubcommandNonZeroReturnValue(Exception):

    def __init__(self, command, return_value):
        self.command = command
        self.retval = return_value

    def __str__(self):
        return 'Sub process "%s" returned a non-zero value: %d' % (
            self.command, self.retval)

import subprocess


def run(args, as_root=False, stdin=None, stdout=None, stderr=None):
    """Run the given command as a sub process.

    Return a Popen instance.

    Callsites must wait() or communicate() with the returned Popen instance.

    :param command: A list or tuple containing the command to run and the
                    arguments that should be passed to it.
    :param as_root: Should the given command be run as root (with sudo)?
    :param stdin: Same as in subprocess.Popen().
    :param stdout: Same as in subprocess.Popen().
    :param stderr: Same as in subprocess.Popen().
    """
    assert isinstance(args, (list, tuple)), (
        "The command to run must be a list or tuple, found: %s" % type(args))
    # TODO: We might want to always use 'sudo -E' here to avoid problems like
    # https://launchpad.net/bugs/673570
    if as_root:
        args = args[:]
        args.insert(0, 'sudo')
    return Popen(args, stdin=stdin, stdout=stdout, stderr=stderr)


class Popen(subprocess.Popen):
    """A version of Popen which raises an error on non-zero returncode.

    Once the subprocess completes we check its returncode and raise
    SubcommandNonZeroReturnValue if it's non-zero.
    """

    def __init__(self, args, **kwargs):
        self._my_args = args
        super(Popen, self).__init__(args, **kwargs)

    def wait(self):
        returncode = super(Popen, self).wait()
        if returncode != 0:
            raise SubcommandNonZeroReturnValue(self._my_args, returncode)
        return returncode


class SubcommandNonZeroReturnValue(Exception):

    def __init__(self, command, return_value):
        self.command = command
        self.retval = return_value

    def __str__(self):
        return 'Sub process "%s" returned a non-zero value: %d' % (
            self.command, self.retval)

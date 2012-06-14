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

import os
import subprocess


DEFAULT_PATH = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
CHROOT_ARGS = ['chroot']
SUDO_ARGS = ['sudo', '-E']


def sanitize_path(env):
    """Makes sure PATH is set and has important directories"""
    dirs = env.get('PATH', DEFAULT_PATH).split(os.pathsep)
    for d in DEFAULT_PATH.split(os.pathsep):
        if d not in dirs:
            dirs.append(d)
    env['PATH'] = os.pathsep.join(dirs)


def run(args, as_root=False, chroot=None, stdin=None, stdout=None,
        stderr=None, cwd=None):
    """Run the given command as a sub process.

    Return a Popen instance.

    Callsites must wait() or communicate() with the returned Popen instance.

    :param command: A list or tuple containing the command to run and the
                    arguments that should be passed to it.
    :param as_root: Should the given command be run as root (with sudo)?
    :param chroot: A directory to chroot into (implies as_root).
    :param stdin: Same as in subprocess.Popen().
    :param stdout: Same as in subprocess.Popen().
    :param stderr: Same as in subprocess.Popen().
    """
    assert isinstance(args, (list, tuple)), (
        "The command to run must be a list or tuple, found: %s" % type(args))
    if isinstance(args, tuple):
        args = list(args)
    if chroot is not None:
        args = CHROOT_ARGS + [chroot] + args
        as_root = True
    if as_root and os.getuid() != 0:
        args = SUDO_ARGS + args
    return Popen(args, stdin=stdin, stdout=stdout, stderr=stderr, cwd=cwd)


class Popen(subprocess.Popen):
    """A version of Popen which raises an error on non-zero returncode.

    Once the subprocess completes we check its returncode and raise
    SubcommandNonZeroReturnValue if it's non-zero.
    """

    def __init__(self, args, env=None, **kwargs):
        self._my_args = args
        self.except_on_cmd_fail = True
        if env is None:
            env = os.environ.copy()
        env['LC_ALL'] = 'C'
        # ensure a proper PATH before calling Popen
        sanitize_path(os.environ)
        # and for subcommands
        sanitize_path(env)
        super(Popen, self).__init__(args, env=env, **kwargs)

    def communicate(self, input=None):
        self.except_on_cmd_fail = False
        stdout, stderr = super(Popen, self).communicate(input)
        self.except_on_cmd_fail = True

        if self.returncode != 0:
            raise SubcommandNonZeroReturnValue(self._my_args,
                                               self.returncode,
                                               stdout,
                                               stderr)
        return stdout, stderr

    def wait(self):
        returncode = super(Popen, self).wait()
        if returncode != 0 and self.except_on_cmd_fail:
            raise SubcommandNonZeroReturnValue(self._my_args, returncode)
        return returncode


class SubcommandNonZeroReturnValue(Exception):

    def __init__(self, command, return_value, stdout=None, stderr=None):
        self.command = command
        self.retval = return_value
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        message = 'Sub process "%s" returned a non-zero value: %d' % (
            self.command, self.retval)

        if self.stdout:
            message += '\nstdout was\n{0}'.format(self.stdout)
        if self.stderr:
            message += '\nstderr was\n{0}'.format(self.stderr)

        return message

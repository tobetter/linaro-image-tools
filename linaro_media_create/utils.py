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
import platform

try:
    from CommandNotFound import CommandNotFound
except ImportError:
    CommandNotFound = None

from linaro_media_create import cmd_runner


def install_package_providing(command):
    """Install a package which provides the given command.

    If we can't find any package which provides it, raise
    UnableToFindPackageProvidingCommand.
    """
    if CommandNotFound is None:
        raise UnableToFindPackageProvidingCommand(
            "Cannot lookup a package which provides %s" % command)

    packages = CommandNotFound().getPackages(command)
    if len(packages) == 0:
        raise UnableToFindPackageProvidingCommand(
            "Unable to find any package providing %s" % command)

    # TODO: Ask the user to pick a package when there's more than one that
    # provide the given command.
    package, _ = packages[0]
    print ("Installing required command %s from package %s"
           % (command, package))
    cmd_runner.run(['apt-get', 'install', package], as_root=True).wait()


def ensure_command(command):
    """Ensure the given command is available.

    If it's not, look up a package that provides it and install that.
    """
    try:
        cmd_runner.run(
            ['which', command], stdout=open('/dev/null', 'w')).wait()
    except cmd_runner.SubcommandNonZeroReturnValue:
        install_package_providing(command)

def find_command(name):
    """Finds a linaro-image-tools commands.

    Searches only the current directory when running from a checkout, and only
    search PATH when running from an installed version.
    """
    assert name != ""
    assert os.path.dirname(name) == ""

    if not os.environ.has_key("PATH"):
        os.environ["PATH"] = ":/bin:usr/bin"

    if os.path.isabs(__file__):
        dirs = os.environ["PATH"].split(os.pathsep)
    else:
        # search relative to current directory
        dirs = ('',)

    for dir in dirs:
        path = os.path.join(dir, name)
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path

    return None


def is_arm_host():
    return platform.machine().startswith('arm')


class UnableToFindPackageProvidingCommand(Exception):
    """We can't find a package which provides the given command."""

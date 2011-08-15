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
import subprocess
import re
import logging
import tempfile

try:
    from CommandNotFound import CommandNotFound
except ImportError:
    CommandNotFound = None

from linaro_image_tools import cmd_runner


def verify_file_integrity(sig_file_list):
    """Verify a list of signature files.

    The parameter is a list of filenames of gpg signature files which will be
    verified using gpg. For each of the files it is assumed that there is an
    sha1 hash file with the same file name minus the '.asc' extension.

    Each of the sha1 files will be checked using sha1sums. All files listed in
    the sha1 hash file must be found in the same directory as the hash file.
    """

    gpg_sig_ok = True
    gpg_out = ""

    verified_files = []
    for sig_file in sig_file_list:
        hash_file = sig_file[0:-len('.asc')]
        tmp = tempfile.NamedTemporaryFile()

        try:
             cmd_runner.run(['gpg', '--status-file={0}'.format(tmp.name),
                             '--verify', sig_file]).wait()
        except cmd_runner.SubcommandNonZeroReturnValue:
            gpg_sig_ok = False
            gpg_out = gpg_out + tmp.read()

        tmp.close()

        if os.path.dirname(hash_file) == '':
            sha_cwd = None
        else:
            sha_cwd = os.path.dirname(hash_file)

        try:
            sha1sums_out, _ = cmd_runner.Popen(
                                            ['sha1sum', '-c', hash_file],
                                            stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT,
                                            cwd=sha_cwd
                                            ).communicate()
        except cmd_runner.SubcommandNonZeroReturnValue as inst:
            sha1sums_out = inst.stdout

        for line in sha1sums_out.splitlines():
            sha1_check = re.search(r'^(.*):\s+OK', line)
            if sha1_check:
                verified_files.append(sha1_check.group(1))

    return verified_files, gpg_sig_ok, gpg_out

def check_file_integrity_and_log_errors(sig_file_list, binary, hwpacks):
    """
    Wrapper around verify_file_integrity that prints error messages to stderr
    if verify_file_integrity finds any problems.
    """
    verified_files, gpg_sig_pass, _ = verify_file_integrity(sig_file_list)

    # Check the outputs from verify_file_integrity
    # Abort if anything fails.
    if len(sig_file_list):
        if not gpg_sig_pass:
            logging.error("GPG signature verification failed.")
            return False, []
    
        if not os.path.basename(binary) in verified_files:
            logging.error("OS Binary verification failed")
            return False, []
        
        for hwpack in hwpacks:
            if not os.path.basename(hwpack) in verified_files:
                logging.error("Hwpack {0} verification failed".format(hwpack))
                return False, []
    
        for verified_file in verified_files:
            logging.info('Hash verification of file {0} OK.'.format(
                                                                verified_file))
    
    return True, verified_files

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
    cmd_runner.run(
        ['apt-get', '--yes', 'install', package], as_root=True).wait()


def has_command(command):
    """Check the given command is available."""
    try:
        cmd_runner.run(
            ['which', command], stdout=open('/dev/null', 'w')).wait()
        return True
    except cmd_runner.SubcommandNonZeroReturnValue:
        return False

def ensure_command(command):
    """Ensure the given command is available.

    If it's not, look up a package that provides it and install that.
    """
    if not has_command(command):
        install_package_providing(command)

def find_command(name, prefer_dir=None):
    """Finds a linaro-image-tools command.

    Prefers specified directory, otherwise searches only the current directory
    when running from a checkout, or only PATH when running from an installed
    version.
    """
    assert name != ""
    assert os.path.dirname(name) == ""

    cmd_runner.sanitize_path(os.environ)

    # default to searching in current directory when running from a bzr
    # checkout
    dirs = [os.getcwd(),]
    if os.path.isabs(__file__):
        dirs = os.environ["PATH"].split(os.pathsep)
        # empty dir in PATH means current directory
        dirs = map(lambda x: x == '' and '.' or x, dirs)

    if prefer_dir is not None:
        dirs.insert(0, prefer_dir)

    for dir in dirs:
        path = os.path.join(dir, name)
        if os.path.exists(path) and os.access(path, os.X_OK):
            return path

    return None


def is_arm_host():
    return platform.machine().startswith('arm')


def preferred_tools_dir():
    prefer_dir = None
    # running from bzr checkout?
    if not os.path.isabs(__file__):
        prefer_dir = os.getcwd()
    return prefer_dir


class UnableToFindPackageProvidingCommand(Exception):
    """We can't find a package which provides the given command."""

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
import tarfile
import sys

from linaro_image_tools import cmd_runner

DEFAULT_LOGGER_NAME = 'linaro_image_tools'

# The boot path in the boot tarball.
BOOT_DIR_IN_TARBALL = "boot"
# The name of the hwpack file found in the boot tarball.
HWPACK_NAME = "config"

# dconf keys to disable automount options.
AUTOMOUNT_DCONF_KEY = '/org/gnome/desktop/media-handling/automount'
AUTOMOUNT_OPEN_DCONF_KEYU = '/org/gnome/desktop/media-handling/automount-open'


# try_import was copied from python-testtools 0.9.12 and was originally
# licensed under a MIT-style license but relicensed under the GPL in Linaro
# Image Tools.
# Copyright (c) 2011 Jonathan M. Lange <jml@mumak.net>.
def try_import(name, alternative=None, error_callback=None):
    """Attempt to import ``name``.  If it fails, return ``alternative``.

    When supporting multiple versions of Python or optional dependencies, it
    is useful to be able to try to import a module.

    :param name: The name of the object to import, e.g. ``os.path`` or
        ``os.path.join``.
    :param alternative: The value to return if no module can be imported.
        Defaults to None.
    :param error_callback: If non-None, a callable that is passed the
        ImportError when the module cannot be loaded.
    """
    module_segments = name.split('.')
    last_error = None
    while module_segments:
        module_name = '.'.join(module_segments)
        try:
            module = __import__(module_name)
        except ImportError:
            last_error = sys.exc_info()[1]
            module_segments.pop()
            continue
        else:
            break
    else:
        if last_error is not None and error_callback is not None:
            error_callback(last_error)
        return alternative
    nonexistent = object()
    for segment in name.split('.')[1:]:
        module = getattr(module, segment, nonexistent)
        if module is nonexistent:
            if last_error is not None and error_callback is not None:
                error_callback(last_error)
            return alternative
    return module


CommandNotFound = try_import('CommandNotFound.CommandNotFound')


def path_in_tarfile_exists(path, tar_file):
    exists = True
    try:
        tarinfo = tarfile.open(tar_file, 'r:*')
        tarinfo.getmember(path)
        tarinfo.close()
    except KeyError:
        exists = False
    except (tarfile.ReadError, tarfile.CompressionError):
        exists = False
        # Fallback to tar command
        cmd = ['tar', '-tf', tar_file, '--wildcards', '*' + path]
        proc = cmd_runner.run(cmd,
                              stdout=open('/dev/null', 'w'),
                              stderr=open('/dev/null', 'w'))
        proc.wait()
        if proc.returncode == 0:
            exists = True
    finally:
        return exists


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
    logger = logging.getLogger(__name__)
    if len(sig_file_list):
        if not gpg_sig_pass:
            logger.error("GPG signature verification failed.")
            return False, []

        if not os.path.basename(binary) in verified_files:
            logger.error("OS Binary verification failed")
            return False, []

        for hwpack in hwpacks:
            if not os.path.basename(hwpack) in verified_files:
                logger.error("Hwpack {0} verification failed".format(hwpack))
                return False, []

        for verified_file in verified_files:
            logger.info('Hash verification of file {0} OK.'.format(
                verified_file))
    return True, verified_files


def install_package_providing(command):
    """Install a package which provides the given command.

    If we can't find any package which provides it, raise
    UnableToFindPackageProvidingCommand.

    If the user denies installing the package, the program exits.
    """

    if CommandNotFound is None:
        raise UnableToFindPackageProvidingCommand(
            "CommandNotFound python module does not exist.")

    packages = CommandNotFound().getPackages(command)
    if len(packages) == 0:
        raise UnableToFindPackageProvidingCommand(
            "Unable to find any package providing %s" % command)

    # TODO: Ask the user to pick a package when there's more than one that
    # provides the given command.
    package, _ = packages[0]
    output, _ = cmd_runner.run(['apt-get', '-s', 'install', package],
                               stdout=subprocess.PIPE).communicate()
    to_install = []
    for line in output.splitlines():
        if line.startswith("Inst"):
            to_install.append(line.split()[1])
    if not to_install:
        raise UnableToFindPackageProvidingCommand(
            "Unable to find any package to be installed.")

    try:
        print ("In order to use the '%s' command, the following package/s "
               "have to be installed: %s" % (command, " ".join(to_install)))
        resp = raw_input("Install? (Y/n) ")
        if resp.lower() != 'y':
            print "Package installation is necessary to continue. Exiting."
            sys.exit(1)
        print ("Installing required command '%s' from package '%s'..."
               % (command, package))
        cmd_runner.run(['apt-get', '--yes', 'install', package],
                       as_root=True).wait()
    except EOFError:
        raise PackageInstallationRefused(
            "Package installation interrupted: input error.")
    except KeyboardInterrupt:
        raise PackageInstallationRefused(
            "Package installation interrupted by the user.")


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
    dirs = [os.getcwd(), ]
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


def prep_media_path(args):
    if args.directory is not None:
        loc = os.path.abspath(args.directory)
        try:
            os.makedirs(loc)
        except OSError:
            # Directory exists.
            pass

        path = os.path.join(loc, args.device)
    else:
        path = args.device

    return path


class UnableToFindPackageProvidingCommand(Exception):
    """We can't find a package which provides the given command."""


class PackageInstallationRefused(Exception):
    """User has chosen not to install a package."""


class InvalidHwpackFile(Exception):
    """The hwpack parameter is not a regular file."""


class MissingRequiredOption(Exception):
    """A required option from the command line is missing."""
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class IncompatibleOptions(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


def additional_option_checks(args):
    if args.directory is not None:
    # If args.device is a path to a device (/dev/) then this is an error
        if "--mmc" in sys.argv:
            raise IncompatibleOptions("--directory option incompatible with "
                                      "option --mmc")

        # If directory is used as well as having a full path (rather than just
        # a file name or relative path) in args.device, this is an error.
        if re.search(r"^/", args.device):
            raise IncompatibleOptions("--directory option incompatible with "
                                      "a full path in --image-file")

    for hwpack in args.hwpacks:
        if not os.path.isfile(hwpack):
            raise InvalidHwpackFile(
                "--hwpack argument (%s) is not a regular file" % hwpack)


def additional_android_option_checks(args):
    """Checks that some of the args passed to l-a-m-c are valid."""
    if args.hwpack:
        if not os.path.isfile(args.hwpack):
            raise InvalidHwpackFile(
                "--hwpack argument (%s) is not a regular file" % args.hwpack)


def android_hwpack_in_boot_tarball(boot_dir):
    """Simple check for existence of a path.

    Needed to make cli command testable in some way.
    :param boot_dir: The path where the boot tarball has been extracted.
    :type str
    :return A tuple with a bool if the path exists, and the path to the config
            file.
    """
    conf_file = os.path.join(boot_dir, BOOT_DIR_IN_TARBALL, HWPACK_NAME)
    return os.path.exists(conf_file), conf_file


def check_required_args(args):
    """Check that the required args are passed."""
    if args.dev is None:
        raise MissingRequiredOption("--dev option is required")
    if args.binary is None:
        raise MissingRequiredOption("--binary option is required")


def get_logger(name=DEFAULT_LOGGER_NAME, debug=False):
    """
    Retrieves a named logger. Default name is set in the variable
    DEFAULT_LOG_NAME. Debug is set to False by default.

    :param name: The name of the logger.
    :param debug: If debug level should be turned on
    :return: A logger instance.
    """
    logger = logging.getLogger(name)
    ch = logging.StreamHandler()

    if debug:
        ch.setLevel(logging.DEBUG)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        ch.setFormatter(formatter)
        logger.setLevel(logging.DEBUG)
    else:
        ch.setLevel(logging.INFO)
        formatter = logging.Formatter("%(message)s")
        ch.setFormatter(formatter)
        logger.setLevel(logging.INFO)

    logger.addHandler(ch)
    return logger


def disable_automount():
    """Disables the desktop environment automount option.

    This will work only under GNOME with dconf installed.
    """
    logger = logging.getLogger(DEFAULT_LOGGER_NAME)

    if has_command('dconf'):
        logger.info("Disabling desktop environment automount option.")
        try:
            cmd_runner.run(
                ['dconf', 'write', AUTOMOUNT_DCONF_KEY, 'false'],
                stdout=open('/dev/null', 'w')).wait()
            cmd_runner.run(
                ['dconf', 'write', AUTOMOUNT_OPEN_DCONF_KEYU, 'false'],
                stdout=open('/dev/null', 'w')).wait()
        except cmd_runner.SubcommandNonZeroReturnValue:
            logger.error("Error disabling desktop environemnt automount.")


def enable_automount():
    """Re-enables back the desktop environment automount option.

    This will work only under GNOME with dconf installed. It should be run
    as an atexit function.
    """
    logger = logging.getLogger(DEFAULT_LOGGER_NAME)
    if has_command('dconf'):
        try:
            cmd_runner.run(
                ['dconf', 'write', AUTOMOUNT_DCONF_KEY, 'true'],
                stdout=open('/dev/null', 'w')).wait()
            cmd_runner.run(
                ['dconf', 'write', AUTOMOUNT_OPEN_DCONF_KEYU, 'true'],
                stdout=open('/dev/null', 'w')).wait()
        except cmd_runner.SubcommandNonZeroReturnValue:
            logger.error("Error enabling back desktop environemnt automount.")

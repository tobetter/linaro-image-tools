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
import re
import subprocess
from linaro_image_tools import cmd_runner


def unpack_android_binary_tarball(tarball, unpack_dir, as_root=True):
    if is_tar_support_selinux():
        tar_cmd = ['tar', '--selinux', '--numeric-owner', '-C', unpack_dir,
                   '-jxf', tarball]
    else:
        tar_cmd = ['tar', '--numeric-owner', '-C', unpack_dir,
                   '-jxf', tarball]
    proc = cmd_runner.run(tar_cmd, as_root=as_root,
                          stderr=subprocess.PIPE)
    stderr = proc.communicate()[1]
    selinux_warn_outputted = False
    selinux_warn1 = "tar: Ignoring unknown extended header keyword"
    selinux_warn2 = "tar: setfileconat: Cannot set SELinux context"
    for line in stderr.splitlines():
        # following 2 messages will not occur at the same time
        index = line.find(selinux_warn1)
        index2 = line.find(selinux_warn2)
        if index == -1 and index2 == -1:
            print line
            continue
        elif not selinux_warn_outputted:
            # either index != -1 or index2 != -1
            print line
            print ("WARNING: selinux will not work correctly since the\n"
                   "         --selinux option of tar command in this OS\n"
                   "         is not fully supported\n")
            selinux_warn_outputted = True
        else:
            # same line of selinux_warn1 or selinux_warn2
            continue

    return proc.returncode


def unpack_binary_tarball(tarball, unpack_dir, as_root=True):
    extract_opt = '-xf'
    if tarball.endswith('.xz'):
        extract_opt = '-Jxf'
    proc = cmd_runner.run(
        ['tar', '--numeric-owner', '-C', unpack_dir, extract_opt, tarball],
        as_root=as_root)
    proc.wait()
    return proc.returncode


def is_tar_support_selinux():
    try:
        tar_help, _ = cmd_runner.Popen(
            ['tar', '--help'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        ).communicate()
    except cmd_runner.SubcommandNonZeroReturnValue as inst:
        return False

    for line in tar_help.splitlines():
        selinux_support = re.search('--selinux', line)
        if selinux_support:
            return True
    return False

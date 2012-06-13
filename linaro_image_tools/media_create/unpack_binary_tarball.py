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

from linaro_image_tools import cmd_runner


def unpack_android_binary_tarball(tarball, unpack_dir, as_root=True):
    proc = cmd_runner.run(
        ['tar', '--numeric-owner', '-C', unpack_dir, '-jxf', tarball],
        as_root=as_root)
    proc.wait()
    return proc.returncode


def unpack_binary_tarball(tarball, unpack_dir, as_root=True):
    proc = cmd_runner.run(
        ['tar', '--numeric-owner', '-C', unpack_dir, '-xf', tarball],
        as_root=as_root)
    proc.wait()
    return proc.returncode

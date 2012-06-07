# Copyright (C) 2011 Linaro
#
# Author: Loic Minier <loic.minier@linaro.org>
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import subprocess
from testtools import TestCase


class TestPyflakes(TestCase):
    def test_pyflakes(self):
        # ignore return code
        proc = subprocess.Popen(['pyflakes', '.'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (stdout, stderr) = proc.communicate()
        self.assertEquals('', stdout)
        self.assertEquals('', stderr)

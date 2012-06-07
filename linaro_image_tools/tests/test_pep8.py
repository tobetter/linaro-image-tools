# Copyright (C) 2012 Linaro Ltd.
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


class TestPep8(TestCase):
    def test_pep8(self):
        ignore = [
            'E241', 'E251', 'E301', 'E302',
            'E303', 'E501', 'W291', 'W292', 'W293', 'W391']
        # ignore return code
        proc = subprocess.Popen(['pep8',
            '--repeat',
            '--ignore=%s' % ','.join(ignore),
            '.'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)
        (stdout, stderr) = proc.communicate()
        self.assertEquals('', stdout)
        self.assertEquals('', stderr)

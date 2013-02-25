# Copyright (C) 2010, 2011, 2012 Linaro
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

import os
import unittest

from linaro_image_tools.hwpack.tests import test_suite as hwpack_suite
from linaro_image_tools.media_create.tests import (
    test_suite as media_create_suite,
)
from linaro_image_tools.utils import has_command


def test_suite():
    module_names = [
        'linaro_image_tools.tests.test_cmd_runner',
        'linaro_image_tools.tests.test_utils',
    ]
    # if pyflakes is installed and we're running from a bzr checkout...
    if has_command('pyflakes') and not os.path.isabs(__file__):
        # ...also run the pyflakes test
        module_names.append('linaro_image_tools.tests.test_pyflakes')
    # if pep8 is installed and we're running from a bzr checkout...
    if has_command('pep8') and not os.path.isabs(__file__):
        # ...also run the pep8 test
        module_names.append('linaro_image_tools.tests.test_pep8')
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    suite.addTests(hwpack_suite())
    suite.addTests(media_create_suite())
    return suite

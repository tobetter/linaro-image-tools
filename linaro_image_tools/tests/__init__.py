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
        'linaro_image_tools.tests.test_fetch_image',
        ]
    # if pyflakes is installed and we're running from a bzr checkout...
    if has_command('pyflakes') and not os.path.isabs(__file__):
        # ...also run the pyflakes tests
        module_names.append('linaro_image_tools.tests.test_pyflakes')
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    suite.addTests(hwpack_suite())
    suite.addTests(media_create_suite())
    return suite


import unittest

def test_suite():
    module_names = ['hwpack.tests.test_config',
                    'hwpack.tests.test_better_tarfile',
                    'hwpack.tests.test_builder',
                    'hwpack.tests.test_hardwarepack',
                    'hwpack.tests.test_packages',
                    'hwpack.tests.test_tarfile_matchers',
                   ]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    return suite

import unittest

def test_suite():
    module_names = ['hwpack.tests.test_config',
                    'hwpack.tests.test_hwpack',
                   ]
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromNames(module_names)
    return suite

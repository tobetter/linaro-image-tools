#!/usr/bin/python

import os
import os.path
import shutil
import tempfile
import subprocess

class TempDirFixture(object):

    def __init__(self):
        self.tempdir = None

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)
            
    def get_temp_dir(self):
        return self.tempdir


class TarballFixture(object):

    def __init__(self, dir):
        self.dir = dir
        self.tarball = dir + '.tar.gz'
        
    def setUp(self):
        # Create gzipped tar archive.
        args = ['tar', '-czf', self.tarball, self.dir]
        proc = subprocess.Popen(args)
        proc.wait()
        
    def tearDown(self):
        if os.path.exists(self.tarball):
            os.remove(self.tarball)
            
    def get_tarball(self):
        return self.tarball

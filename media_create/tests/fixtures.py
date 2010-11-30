#!/usr/bin/python

import os
import shutil
import subprocess
import tempfile

class CreateTempDirFixture(object):

    def __init__(self):
        self.tempdir = None

    def setUp(self):
        self.tempdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)
            
    def get_temp_dir(self):
        return self.tempdir


class CreateTarballFixture(object):

    def __init__(self, dir):
        self.dir = dir
        self.tarball = os.path.join(self.dir + 'tarball.tar.gz')
        
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

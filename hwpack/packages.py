import os
import shutil
import tempfile

from apt.cache import Cache
from apt.package import FetchError
import apt_pkg


class DummyProgress(object):

    def start(self):
        pass

    def ims_hit(self, item):
        pass

    def fail(self, item):
        pass

    def fetch(self, item):
        pass

    def pulse(self, owner):
        return True

    def media_change(self):
        return False

    def stop(self):
        pass


def ensure_file_uri_starts_with_three_slashes(uri):
    """Ensure that file: URIs are in a format suitable for use with bzrlib.

    apt can handle file:/something URIs with no problem, but bzrlib
    rejects them. We therefore fix this up ourselves as we know how
    apt would handle them.

    :param uri: the uri to check.
    :type uri: str
    :return: the modified uri.
    :rtype: str
    """
    if uri.startswith("file:/") and uri[len("file:/")] != '/':
        uri = "file:///" + uri[len("file:/"):]
    return uri


class PackageFetcher(object):
    """A class to fetch packages from a defined list of sources."""

    def __init__(self, sources):
        """Create a PackageFetcher.

        Once created a PackageFetcher should have its `prepare` method
        called before use.

        :param sources: a list of sources such that they can be prefixed
            with "deb " and fed to apt.
        :type sources: an iterable of str
        """
        self.sources = sources
        self.tempdir = None

    def prepare(self):
        """Prepare a PackageFetcher for use.

        Should be called before use, and after any modification to the list
        of sources.
        """
        self.cleanup()
        self.tempdir = tempfile.mkdtemp(prefix="hwpack-apt-cache-")
        files = ["var/lib/dpkg/status",
                ]
        dirs = ["var/lib/dpkg",
                "etc/apt/",
                "var/cache/apt/archives/partial",
                "var/lib/apt/lists/partial",
               ]
        for d in dirs:
            os.makedirs(os.path.join(self.tempdir, d))
        for fn in files:
            with open(os.path.join(self.tempdir, fn), 'w'):
                pass
        sources_list = os.path.join(
            self.tempdir, "etc", "apt", "sources.list")
        with open(sources_list, 'w') as f:
            for source in self.sources:
                f.write("deb %s\n" % source)
        self.cache = Cache(rootdir=self.tempdir, memonly=True)
        self.cache.update()
        self.cache.open()

    def cleanup(self):
        """Cleanup any remaining artefacts.

        Should be called on all PackageFetchers when they are finished
        with.
        """
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)

    def fetch_packages(self, packages):
        """Fetch the files for the given list of package names.

        :param packages: a list of package names to install
        :type packages: an iterable of str
        :return: a dict containing the filenames of the .debs that were
            fetched as the keys, and file objects with the contents of
            those debs as the values.
        :rtype: a dict mapping str to file-like objects.
        :raises KeyError: if any of the package names in the list couldn't
            be found.
        """
        results = {}
        for package in packages:
            candidate = self.cache[package].candidate
            base = os.path.basename(candidate.filename)
            destfile = os.path.join(self.tempdir, base)
            acq = apt_pkg.Acquire(DummyProgress())
            acqfile = apt_pkg.AcquireFile(
                acq, candidate.uri, candidate.md5, candidate.size,
                base, destfile=destfile)
            acq.run()
            if acqfile.status != acqfile.STAT_DONE:
                raise FetchError(
                    "The item %r could not be fetched: %s" %
                    (acqfile.destfile, acqfile.error_text))
            results[base] = open(destfile)
        return results

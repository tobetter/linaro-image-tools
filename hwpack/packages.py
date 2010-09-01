import os
import shutil
import tempfile

from apt.cache import Cache

from bzrlib.transport import get_transport
from bzrlib import urlutils


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
        possible_transports = []
        for package in packages:
            apt_pkg = self.cache[package]
            candidate = apt_pkg.candidate
            base = os.path.basename(candidate.filename)
            dir_url = urlutils.dirname(candidate.uri)
            dir_url = ensure_file_uri_starts_with_three_slashes(dir_url)
            results[base] = get_transport(
                dir_url,
                possible_transports=possible_transports).get(base)
        return results

from contextlib import contextmanager
import hashlib
import os
import shutil
import tempfile
from StringIO import StringIO
import tarfile
import time

from testtools import TestCase
from testtools.matchers import Matcher, Mismatch

from hwpack.better_tarfile import writeable_tarfile
from hwpack.tarfile_matchers import TarfileHasFile
from hwpack.packages import get_packages_file, FetchedPackage


@contextmanager
def test_tarfile(contents=[], **kwargs):
    """Create a tarfile with the given contents, then re-open it for reading.

    This context manager creates a tarfile with the given contents, then
    reopens it for reading and yields it for use in a with block. When
    the block ends the tarfile will be closed.

    The contents can be specified as a list of tuples of (path, contents),
    where if the path ends with '/' it is considered to be a directory and
    the contents ignored.

    :param contents: the contents to put in the tarball, defaults to the
        empty list.
    :type contents: a list of tuples of (str, str)
    :param kwargs: keyword arguments for the better_tarfile.TarFile
        constructor.
    """
    backing_file = StringIO()
    with writeable_tarfile(backing_file, **kwargs) as tf:
        for path, content in contents:
            if path[-1] == "/":
                tf.create_dir(path)
            else:
                tf.create_file_from_string(path, content)
    if contents:
        backing_file.seek(0)
    tf = tarfile.TarFile.open(mode="r", fileobj=backing_file)
    try:
        yield tf
    finally:
        tf.close()


class DummyFetchedPackage(FetchedPackage):
    """A FetchedPackage with dummy information.

    See FetchedPackage for the instance variables.
    """

    def __init__(self, name, version, architecture="all", depends=None,
                 pre_depends=None, conflicts=None, recommends=None,
                 no_content=False):
        self.name = name
        self.version = version
        self.architecture = architecture
        self.depends = depends
        self.pre_depends = pre_depends
        self.conflicts = conflicts
        self.recommends = recommends
        self._no_content = no_content

    @property
    def filename(self):
        return "%s_%s_all.deb" % (self.name, self.version)

    def _content_str(self):
        return "Content of %s" % self.filename

    @property
    def content(self):
        if self._no_content:
            return None
        return StringIO(self._content_str())

    @property
    def size(self):
        return len(self._content_str())

    @property
    def md5(self):
        md5sum = hashlib.md5()
        md5sum.update(self._content_str())
        return md5sum.hexdigest()


class AptSourceFixture(object):
    """A fixture that provides an apt source, with packages and indices.

    An apt source provides a set of package files, and a Packages file
    that allows apt to determine the contents of the source.

    :ivar sources_entry: the URI and suite to give to apt to view the
        source (i.e. a sources.list line without the "deb" prefix
    :type sources_entry: str
    """

    def __init__(self, packages):
        """Create an AptSourceFixture.

        :param packages: a list of packages to add to the source
            and index.
        :type packages: an iterable of FetchedPackages
        """
        self.packages = packages

    def setUp(self):
        self.rootdir = tempfile.mkdtemp(prefix="hwpack-apt-source-")
        for package in self.packages:
            with open(
                os.path.join(self.rootdir, package.filename), 'wb') as f:
                f.write(package.content.read())
        with open(os.path.join(self.rootdir, "Packages"), 'wb') as f:
            f.write(get_packages_file(self.packages))

    def tearDown(self):
        if os.path.exists(self.rootdir):
            shutil.rmtree(self.rootdir)

    @property
    def sources_entry(self):
        return "file:" + os.path.abspath(self.rootdir) +" ./"


class TestCaseWithFixtures(TestCase):
    """A TestCase with the ability to easily add 'fixtures'.

    A fixture is an object which can be created and cleaned up, and
    this test case knows how to manage them to ensure that they will
    always be cleaned up at the end of the test.
    """

    def useFixture(self, fixture):
        """Make use of a fixture, ensuring that it will be cleaned up.

        Given a fixture, this method will run the `setUp` method of
        the fixture, and ensure that its `tearDown` method will be
        called at the end of the test, regardless of success or failure.

        :param fixture: the fixture to use.
        :type fixture: an object with setUp and tearDown methods.
        :return: the fixture that was passed in.
        """
        self.addCleanup(fixture.tearDown)
        fixture.setUp()
        return fixture


class ConfigFileFixture(object):

    def __init__(self, contents):
        self.contents = contents
        self.filename = None

    def setUp(self):
        fh, self.filename = tempfile.mkstemp(prefix="hwpack-test-config-")
        with os.fdopen(fh, 'w') as f:
            f.write(self.contents)

    def tearDown(self):
        if self.filename is not None and os.path.exists(self.filename):
            os.unlink(self.filename)


class ChdirToTempdirFixture(object):

    def __init__(self):
        self._orig_dir = None
        self.tempdir = None

    def setUp(self):
        self.tearDown()
        self._orig_dir = os.getcwd()
        self.tempdir = tempfile.mkdtemp(prefix="hwpack-tests-")
        os.chdir(self.tempdir)

    def tearDown(self):
        if self._orig_dir is not None:
            os.chdir(self._orig_dir)
            self._orig_dir = None
        if self.tempdir is not None and os.path.exists(self.tempdir):
            shutil.rmtree(self.tempdir)
            self.tempdir = None


class MismatchesAll(Mismatch):
    """A mismatch with many child mismatches."""

    def __init__(self, mismatches):
        self.mismatches = mismatches

    def describe(self):
        descriptions = ["Differences: ["]
        for mismatch in self.mismatches:
            descriptions.append(mismatch.describe())
        descriptions.append("]\n")
        return '\n'.join(descriptions)


class MatchesAll(object):

    def __init__(self, *matchers):
        self.matchers = matchers

    def __str__(self):
        return 'MatchesAll(%s)' % ', '.join(map(str, self.matchers))

    def match(self, matchee):
        results = []
        for matcher in self.matchers:
            mismatch = matcher.match(matchee)
            if mismatch is not None:
                results.append(mismatch)
        if results:
            return MismatchesAll(results)
        else:
            return None


class Not:
    """Inverts a matcher."""

    def __init__(self, matcher):
        self.matcher = matcher

    def __str__(self):
        return 'Not(%s)' % (self.matcher,)

    def match(self, other):
        mismatch = self.matcher.match(other)
        if mismatch is None:
            return MatchedUnexpectedly(self.matcher, other)
        else:
            return None


class MatchedUnexpectedly:
    """A thing matched when it wasn't supposed to."""

    def __init__(self, matcher, other):
        self.matcher = matcher
        self.other = other

    def describe(self):
        return "%r matches %s" % (self.other, self.matcher)


class HardwarePackHasFile(TarfileHasFile):
    """A subclass of TarfileHasFile specific to hardware packs.

    We default to a set of attributes expected for files in a hardware
    pack.
    """

    def __init__(self, path, **kwargs):
        """Create a HardwarePackHasFile matcher.

        The kwargs are the keyword arguments taken by TarfileHasFile.
        If they are not given then defaults will be checked:
            - The type should be a regular file
            - If the content is given then the size will be checked
                to ensure it indicates the length of the content
                correctly.
            - the mode is appropriate for the type. If the type is
                regular file this is 0644, otherwise if it is
                a directory then it is 0755.
            - the linkname should be the empty string.
            - the uid and gid should be 1000
            - the uname and gname should be "user" and "group"
                respectively.

        :param path: the path that should be present.
        :type path: str
        """
        kwargs.setdefault("type", tarfile.REGTYPE)
        if "content" in kwargs:
            kwargs.setdefault("size", len(kwargs["content"]))
        if kwargs["type"] == tarfile.DIRTYPE:
            kwargs.setdefault("mode", 0755)
        else:
            kwargs.setdefault("mode", 0644)
        kwargs.setdefault("linkname", "")
        kwargs.setdefault("uid", 1000)
        kwargs.setdefault("gid", 1000)
        kwargs.setdefault("uname", "user")
        kwargs.setdefault("gname", "group")
        kwargs.setdefault("mtime", time.time())
        # Enough that it won't fail if the test is slow to execute, but
        #  not enough that we can have a wildly wrong timestamp.
        kwargs.setdefault("mtime_skew", 100)
        super(HardwarePackHasFile, self).__init__(path, **kwargs)


class IsHardwarePack(Matcher):

    def __init__(self, metadata, packages, sources,
                 packages_without_content=None):
        self.metadata = metadata
        self.packages = packages
        self.sources = sources
        self.packages_without_content = packages_without_content or []

    def match(self, path):
        tf = tarfile.open(name=path, mode="r:gz")
        try:
            matchers = []
            matchers.append(HardwarePackHasFile("FORMAT", content="1.0\n"))
            matchers.append(HardwarePackHasFile(
                "metadata", content=str(self.metadata)))
            manifest = ""
            for package in self.packages:
                manifest += "%s=%s\n" % (package.name, package.version)
            matchers.append(HardwarePackHasFile("manifest", content=manifest))
            matchers.append(HardwarePackHasFile("pkgs", type=tarfile.DIRTYPE))
            packages_with_content = [p for p in self.packages
                if p not in self.packages_without_content]
            for package in packages_with_content:
                matchers.append(HardwarePackHasFile(
                    "pkgs/%s" % package.filename,
                    content=package.content.read()))
            matchers.append(HardwarePackHasFile(
                "pkgs/Packages",
                content=get_packages_file(packages_with_content)))
            matchers.append(HardwarePackHasFile(
                "sources.list.d", type=tarfile.DIRTYPE))
            for source_id, sources_entry in self.sources.items():
                matchers.append(HardwarePackHasFile(
                    "sources.list.d/%s.list" % source_id,
                    content="deb " + sources_entry + "\n"))
            matchers.append(HardwarePackHasFile(
                "sources.list.d.gpg", type=tarfile.DIRTYPE))
            return MatchesAll(*matchers).match(tf)
        finally:
            tf.close()

    def __str__(self):
        return "Is a valid hardware pack."

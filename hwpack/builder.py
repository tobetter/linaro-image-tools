import logging
import errno

from hwpack.config import Config
from hwpack.hardwarepack import HardwarePack, Metadata
from hwpack.packages import (
    FetchedPackage,
    LocalArchiveMaker,
    PackageFetcher,
    )


logger = logging.getLogger(__name__)


LOCAL_ARCHIVE_LABEL='hwpack-local'


class ConfigFileMissing(Exception):

    def __init__(self, filename):
        self.filename = filename
        super(ConfigFileMissing, self).__init__(
            "No such config file: '%s'" % self.filename)


class HardwarePackBuilder(object):

    def __init__(self, config_path, version, local_debs):
        try:
            with open(config_path) as fp:
                self.config = Config(fp)
        except IOError, e:
            if e.errno == errno.ENOENT:
                raise ConfigFileMissing(config_path)
            raise
        self.config.validate()
        self.version = version
        self.local_debs = local_debs

    def build(self):
        for architecture in self.config.architectures:
            logger.info("Building for %s" % architecture)
            metadata = Metadata.from_config(
                self.config, self.version, architecture)
            hwpack = HardwarePack(metadata)
            sources = self.config.sources
            with LocalArchiveMaker() as local_archive_maker:
                hwpack.add_apt_sources(sources)
                sources = sources.values()
                packages = self.config.packages[:]
                local_packages = [
                    FetchedPackage.from_deb(deb)
                    for deb in self.local_debs]
                sources.append(
                    local_archive_maker.sources_entry_for_debs(
                        local_packages, LOCAL_ARCHIVE_LABEL))
                packages.extend([lp.name for lp in local_packages])
                logger.info("Fetching packages")
                fetcher = PackageFetcher(
                    sources, architecture=architecture,
                    prefer_label=LOCAL_ARCHIVE_LABEL)
                with fetcher:
                    fetcher.ignore_packages(self.config.assume_installed)
                    packages = fetcher.fetch_packages(
                        packages, download_content=self.config.include_debs)
                    logger.debug("Adding packages to hwpack")
                    hwpack.add_packages(packages)
                    for local_package in local_packages:
                        if local_package not in packages:
                            logger.error(
                                "Local package '%s' not included",
                                local_package.name)
                    hwpack.add_dependency_package(self.config.packages)
                    with open(hwpack.filename(), 'w') as f:
                        hwpack.to_file(f)
                        logger.info("Wrote %s" % hwpack.filename())

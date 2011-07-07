#!/usr/bin/env python
# Copyright (C) 2010, 2011 Linaro
#
# Author: James Tunnicliffe <james.tunnicliffe@linaro.org>
#
# This file is part of Linaro Image Tools.
#
# Linaro Image Tools is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# Linaro Image Tools is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with Linaro Image Tools; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

import os
import re
import urlparse
import logging
import bz2
import linaro_image_tools.FetchImage

RELEASES_WWW_DOCUMENT_ROOT  = "/srv/releases.linaro.org/www/platform/"
RELEASE_URL                 = "http://releases.linaro.org/platform/"
SNAPSHOTS_WWW_DOCUMENT_ROOT = "/srv/snapshots.linaro.org/www/"
SNAPSHOTS_URL               = "http://snapshots.linaro.org/"

class ServerIndexer():
    """Create a database of files on the linaro image servers for use by image
       creation tools."""
    def reset(self):
        self.url_parse = {}

    def __init__(self):
        self.reset()
        self.db_file_name = "server_index"
        self.db = linaro_image_tools.FetchImage.DB(self.db_file_name)

    def crawl(self):
        self.db.set_url_parse_info(self.url_parse)
        logging.info(self.url_parse.items())
        
        for table, info in self.url_parse.items():
            logging.info(info["base_dir"], ":", info["base_url"], table,
                         info["url_validator"], info["url_chunks"])
            self.go(info["base_dir"], info["base_url"], table)
            logging.info("")

    def go(self, root_dir_, root_url_, table_):
        for root, subFolders, files in os.walk( root_dir_ ):
            for file in files:
                if(re.search('\.gz$', file)):
                    # Construct a URL to the file and save in the database
                    relative_location = re.sub(root_dir_, "", 
                                               os.path.join(root, file))
                    url = urlparse.urljoin(root_url_, relative_location)
                    url = urlparse.urljoin(url, file)
                   
                    if not re.search('/leb-panda/', url):
                        logging.info(url)
                        self.db.record_url(url, table_)
                    
        self.dump() 

    def dump(self):
        self.db.commit()
        
    def close_and_bzip2(self):
        # After finishing creating the database, create a compressed version
        # for more efficient downloads
        self.db.close()
        bz2_db_file = bz2.BZ2File(self.db_file_name + ".bz2", "w")
        db_file = open(self.db_file_name)
        bz2_db_file.write(db_file.read())
        bz2_db_file.close()

    def add_directory_parse_list(self,
                                 base_dir_,
                                 base_url_,
                                 url_validator_,
                                 id_,
                                 url_chunks_):
        
        if(not id_ in self.url_parse):
            self.url_parse[id_] = {"base_dir":      base_dir_,
                                   "base_url":      base_url_,
                                   "url_validator": url_validator_,
                                   "url_chunks":    url_chunks_}
            logging.info(self.url_parse[id_]["base_dir"])

            # Construct data needed to create the table
            items = []
            for item in url_chunks_:
                if(item != ""):
                    # If the entry is a tuple, it indicates it is of the
                    # form name, regexp
                    if(isinstance(item, tuple)):
                        items.append(item[0])
                    else:
                        items.append(item)

            self.db.create_table_with_url_text_items(id_, items)

    def clean_removed_urls_from_db(self):
        self.db.clean_removed_urls_from_db()

if __name__ == '__main__':
    crawler = ServerIndexer()

    # The use of a zero width assertion here to look for links that don't 
    # contain /hwpacks/ is a bit scary and could be replaced by a tuple of
    # (False, r"hwpacks"), where the first parameter could indicate that we
    # want the regexp to fail if we are to use the URL. May be a bit nicer.
    
    #http://releases.linaro.org/platform/linaro-m/plasma/final/
    crawler.add_directory_parse_list(RELEASES_WWW_DOCUMENT_ROOT,
                                     RELEASE_URL,
                                     r"^((?!hwpack).)*$",
                                     "release_binaries",
                                     ["platform", "image", "build"])

    #http://releases.linaro.org/platform/linaro-m/hwpacks/final/hwpack_linaro-bsp-omap4_20101109-1_armel_unsupported.tar.gz
    crawler.add_directory_parse_list(RELEASES_WWW_DOCUMENT_ROOT,
                                     RELEASE_URL,
                                     r"/hwpacks/",
                                     "release_hwpacks",
                                     ["platform", "", "build",
                                      ("hardware", r"hwpack_linaro-(.*?)_")])
    
    #http://snapshots.linaro.org/11.05-daily/linaro-alip/20110420/0/images/tar/
    crawler.add_directory_parse_list(SNAPSHOTS_WWW_DOCUMENT_ROOT,
                                     SNAPSHOTS_URL,
                                     r"^((?!hwpack).)*$",
                                     "snapshot_binaries",
                                     ["platform", "image", "date", "build"])

    #http://snapshots.linaro.org/11.05-daily/linaro-hwpacks/omap3/20110420/0/images/hwpack/
    crawler.add_directory_parse_list(SNAPSHOTS_WWW_DOCUMENT_ROOT,
                                     SNAPSHOTS_URL,
                                     r"/hwpack/",
                                     "snapshot_hwpacks",
                                     ["platform", "", "hardware", "date",
                                      "build"])

    crawler.crawl()
    crawler.clean_removed_urls_from_db()
    crawler.dump()
    crawler.close_and_bzip2()

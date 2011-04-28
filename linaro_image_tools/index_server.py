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

import os, sys, re
import urllib2, time
import getopt
from BeautifulSoup import BeautifulSoup, SoupStrainer
import FetchImage

sys.setrecursionlimit( 300 )

class server_indexer():

    def reset( self ):
        self.url_parse = {}

    def __init__( self ):
        self.reset()
        self.db = FetchImage.db( "server_index" )

    def download_file( self, url_ ):
        #print "download_file", url_
        #print ".",
        maxtries = 3
        for trycount in range( 0, maxtries ):
            try:
                response = urllib2.urlopen( url_ )
                break
            except: # urllib2.URLError, e:
                #return False
                if( trycount < maxtries - 1 ):
                    print "Error. Retrying"
                    time.sleep( 5 )
                    continue
                else:
                    return False

        return response.read()

    def crawl( self ):
        self.db.set_url_parse_info( self.url_parse )
        for table, ( base_url, url_validator, url_chunk_names ) in self.url_parse.items():
            print base_url, ":", table, url_validator, url_chunk_names
            self.go( base_url, table )
            print ""

    def go( self, url_, table_ ):
        #--- MASSIVE DEV HACK ---

        date_search = re.search( r"/(\d+)/", url_ )
        if( date_search and int( date_search.group( 1 ) ) < 20110427 and len( date_search.group( 1 ) ) == 8 ):
            # Found a chunk of date, which is too old for us to care about now
            return

        #--- END MASSIVE DEV HACK ---

        if( not re.search( r"/$", url_ ) ):
            url_ = url_ + "/"
        html = self.download_file( url_ )
        linksToCrawl = SoupStrainer( 'a', href = re.compile( '^[^\\?/]' ) )

        for tag in BeautifulSoup( html, parseOnlyThese = linksToCrawl ):
            for attr, value in tag.attrs: # Slightly paranoid way of doing things...
                if( attr == "href" and not re.match( '\.\.', value ) ):
                    # Minor optimisation - don't descend into any directories that will hit a negative match in a URL validator
                    # It would be easy to perform further optimisations if we had a fixed directory layout! I guess we could
                    # do something slightly messy and give the script a start hint. Of course, once we are able to directly
                    # interact with the server file system, our life gets very easy.
                    if( re.search( r"\(\?\!", self.url_parse[table_][1] ) # URL validator contains a negative match 
                        and not re.search( self.url_parse[table_][1], url_ ) ): # and we hit that match
                        return # If the URL doesn't pass the URL validator search, don't recurse

                    if( re.search( '/$', value ) ): # Is a directory, recurse
                        self.go( url_ + value, table_ )
                    elif( re.search( '\.gz$', value ) ): # Is a gzip, record
                        self.db.record_url( url_ + value, table_ )
                        print "Record:", url_

        self.dump()

    def dump( self ):
        self.db.commit()

    def add_url_parse_list( self, base_url_, url_validator, id_, url_chunks_ ):
        if( not id_ in self.url_parse ):
            self.url_parse[id_] = ( base_url_, url_validator, url_chunks_ )

            items = []
            for item in url_chunks_:
                if( item != "" ):
                    if( isinstance( item, tuple ) ): # If the entry is a tuple, it indicates it is of the form name, regexp
                        items.append( item[0] )
                    else:
                        items.append( item )

            self.db.create_table_with_url_text_items( id_, items )

    def clean_removed_urls_from_db( self ):
        self.db.clean_removed_urls_from_db()

if __name__ == '__main__':
    crawler = server_indexer()

    # The use of a zero width assertion here to look for links that don't contain /hwpacks/ is a bit scary and could
    # be replaced by a tuple of (False, r"hwpacks"), where the first parameter could indicate that we want the regexp
    # to fail if we are to use the URL. May be a bit nicer.
    #http://releases.linaro.org/platform/linaro-m/plasma/final/
    crawler.add_url_parse_list( "http://releases.linaro.org/platform",
                                r"^((?!/hwpacks/).)*$",
                                "release_binaries",
                                ["platform", "image", "build"] )

    #http://releases.linaro.org/platform/linaro-m/hwpacks/final/hwpack_linaro-bsp-omap4_20101109-1_armel_unsupported.tar.gz
    crawler.add_url_parse_list( "http://releases.linaro.org/platform",
                                r"/hwpacks/",
                                "release_hwpacks",
                                ["platform", "", "build", ( "hardware", r"hwpack_linaro-(.*?)_" )] )

    #http://snapshots.linaro.org/11.05-daily/linaro-alip/20110420/0/images/tar/
    crawler.add_url_parse_list( "http://snapshots.linaro.org/",
                                r"^((?!/linaro-hwpacks/).)*$",
                                "snapshot_binaries",
                                ["platform", "image", "date", "build"] )

    #http://snapshots.linaro.org/11.05-daily/linaro-hwpacks/omap3/20110420/0/images/hwpack/
    crawler.add_url_parse_list( "http://snapshots.linaro.org/",
                                r"/linaro-hwpacks/",
                                "snapshot_hwpacks",
                                ["platform", "", "hardware", "date", "build"] )

    crawler.crawl()
    crawler.clean_removed_urls_from_db()
    crawler.dump()

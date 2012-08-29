#!/bin/sh

basedir=$PWD

for dir in `find . -mindepth 1 -type d`; do
    echo "==$dir=="
    cd $dir
    ls -l
    equivs-build *.control
    mv *.deb ..
    cd $basedir
done

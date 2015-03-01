#!/bin/sh

# AwesomeTTS text-to-speech add-on for Anki
#
# Copyright (C) 2013-2014  Anki AwesomeTTS Development Team
# Copyright (C) 2013-2014  Dave Shifflett
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

if [ -z "$1" ]
then
    echo 'Please specify where you want to save the package.' 1>&2
    echo 1>&2
    echo "    Usage: $0 <target>" 1>&2
    echo "     e.g.: $0 ~/AwesomeTTS.zip" 1>&2
    exit 1
fi

target=$1

case $target in
    *.zip)
        ;;

    *)
        echo 'Expected target path to end in a ".zip" extension.' 1>&2
        exit 1
esac

case $target in
    /*)
        ;;

    *)
        target=$PWD/$target
esac

if [ -e "$target" ]
then
    echo 'Removing old package...'
    rm -fv "$target"
fi

oldPwd=$PWD
cd "$(dirname "$0")/.."

echo 'Packing zip file...'
zip -9R "$target" awesometts/LICENSE.txt awesometts/\*.mp3 \*.py \*.js

cd "$oldPwd"

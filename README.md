# About

gircheck is a utility for fixing up GIR files.

## Usage

```console
Fixup GIR files:

GIR files can be found at https://github.com/gtk-rs/gir-files

filelist.py can be found at https://github.com/renesugar/filelist

python3 -B ../filelist/filelist.py --path ../gtk/gir-files --extensions ".gir" > ./config/filelist.txt

python3 -B ./gircheck.py --output=./original-gir-files --passthrough --filelist=./config/filelist.txt

python3 -B ./gircheck.py --output=./gir-files --filelist=./config/filelist.txt --excluderegistered=./config/exclude-registered.txt


Fix GIR files (changes not handled by gircheck)

./fix.sh

Generate type information

python3 -B ./gircheck.py --output=./typeinfo --typeinfo --filelist=./config/filelist-macos.txt --excludegtypes=./config/exclude-gtypes.txt --excludeheaders=./config/exclude-headers.txt

Generate property information

python3 -B ./gircheck.py --output=./propinfo --propertyinfo --filelist=./config/filelist-macos.txt --excludegtypes=./config/exclude-gtypes.txt --excludeheaders=./config/exclude-headers.txt

Generate signal information

python3 -B ./gircheck.py --output=./signalinfo --signalinfo --filelist=./config/filelist-macos.txt --excludegtypes=./config/exclude-gtypes.txt --excludeheaders=./config/exclude-headers.txt

Merge type and property information

python3 -B ./gircheck.py --output=./info --excludegtypes=./config/exclude-gtypes.txt --mergeinfo=./info/typeinfo.txt,./info/propinfo.txt
```

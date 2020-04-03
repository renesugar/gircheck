#!/bin/bash
set -x -e

# incorrect GIR due to missing c:type (type declared later in GIR file)
xmlstarlet ed -P -L \
	-d '//_:record[@name="Value"]/_:field[@name="data"]/_:array/@c:type' \
  -u '//_:record[@name="Value"]/_:field[@name="data"]/_:array/_:type/@c:type' -v "union _Value__data__union" \
	-i '//_:record[@name="Value"]/_:field[@name="data"]/_:array/_:type[not(@c:type)]' -t attr -n "c:type" -v "union _Value__data__union" \
	original-gir-files/GObject-2.0.gir

# incorrect GIR due to typo in name attribute
xmlstarlet ed -P -L \
	-u '//_:enumeration[@name="nvokeError"]/@name' -v "InvokeError" \
  original-gir-files/GIRepository-2.0.gir
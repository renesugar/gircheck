# -*- Mode: Python -*-
# GObject-Introspection - a framework for introspecting GObject libraries
# Copyright (C) 2008-2010 Johan Dahlin
# Copyright (C) 2009 Red Hat, Inc.
# Copyright (C) 2019 Rene Sugar
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.
#

import errno
import optparse
import os
import shutil
import stat
import sys
import tempfile
import platform
import shlex

import gi
gi.require_version("Gtk", "3.0")
import gi.overrides
import gi.types

from gi.repository import Gtk
from gi.repository import Gio
from gi.repository import GObject
from gi.repository import GLib

import giscanner
from giscanner import ast
from giscanner.girparser import GIRParser
from giscanner.girwriter import GIRWriter as PassthroughWriter
from girwriter import GIRWriter
from codewriter import CodeWriter
from codewriter import COMMENT_HASH

ALL_EXTS = ['.gir']

class RegisteredType(ast.Type, ast.Registered):
    def __init__(self,
                 gtype_name=None,
                 get_type=None,
                 ctype=None,
                 fundamental_type=None):
        ast.Registered.__init__(self, gtype_name=gtype_name, get_type=get_type)
        self.ctype = ctype
        self.fundamental_type = fundamental_type

# Fundamental types, special types
TYPE_INVALID = RegisteredType(gtype_name='invalid', ctype='invalid', get_type='G_TYPE_INVALID')
TYPE_NONE = RegisteredType(gtype_name='none', ctype='void', get_type='G_TYPE_NONE')
# Fundamental types
TYPE_INTERFACE = RegisteredType(gtype_name='GTypeInterface', ctype='GTypeInterface', get_type='G_TYPE_INTERFACE')
TYPE_BOOLEAN = RegisteredType(gtype_name='gboolean', ctype='gboolean', get_type='G_TYPE_BOOLEAN')

# Basic types
# https://developer.gnome.org/glib/stable/glib-Basic-Types.html

# New types which are not part of standard C
TYPE_SIZE = RegisteredType(gtype_name='gsize', ctype='gsize', get_type='G_TYPE_ULONG')
TYPE_SSIZE = RegisteredType(gtype_name='gssize', ctype='gssize', get_type='G_TYPE_LONG')

# Integer types which are guaranteed to be the same size across all platforms
TYPE_INT8 = RegisteredType(gtype_name='gint8', ctype='gint8', get_type='G_TYPE_CHAR')
TYPE_UINT8 = RegisteredType(gtype_name='guint8', ctype='guint8', get_type='G_TYPE_UCHAR')
TYPE_INT16 = RegisteredType(gtype_name='gint16', ctype='gint16', get_type='G_TYPE_INT')
TYPE_UINT16 = RegisteredType(gtype_name='guint16', ctype='guint16', get_type='G_TYPE_UINT')
TYPE_INT32 = RegisteredType(gtype_name='gint32', ctype='gint32', get_type='G_TYPE_INT')
TYPE_UINT32 = RegisteredType(gtype_name='guint32', ctype='guint32', get_type='G_TYPE_UINT')
TYPE_INT64 = RegisteredType(gtype_name='gint64', ctype='gint64', get_type='G_TYPE_INT64')
TYPE_UINT64 = RegisteredType(gtype_name='guint64', ctype='guint64', get_type='G_TYPE_UINT64')

# Types which correspond to standard C types
TYPE_ANY = RegisteredType(gtype_name='gpointer', ctype='gpointer', get_type='G_TYPE_POINTER')
TYPE_CONSTPOINTER = RegisteredType(gtype_name='gconstpointer', ctype='gconstpointer', get_type='G_TYPE_POINTER')

# Fundamental types
TYPE_CHAR = RegisteredType(gtype_name='gchar', ctype='gchar', get_type='G_TYPE_CHAR')
TYPE_UCHAR = RegisteredType(gtype_name='guchar', ctype='guchar', get_type='G_TYPE_UCHAR')
TYPE_INT = RegisteredType(gtype_name='gint', ctype='gint', get_type='G_TYPE_INT')
TYPE_UINT = RegisteredType(gtype_name='guint', ctype='guint', get_type='G_TYPE_UINT')
TYPE_SHORT = RegisteredType(gtype_name='gshort', ctype='gshort', get_type='G_TYPE_INT')
TYPE_USHORT = RegisteredType(gtype_name='gushort', ctype='gushort', get_type='G_TYPE_UINT')
TYPE_LONG = RegisteredType(gtype_name='glong', ctype='glong', get_type='G_TYPE_LONG')
TYPE_ULONG = RegisteredType(gtype_name='gulong', ctype='gulong', get_type='G_TYPE_ULONG')
TYPE_FLOAT = RegisteredType(gtype_name='gfloat', ctype='gfloat', get_type='G_TYPE_FLOAT')
TYPE_DOUBLE = RegisteredType(gtype_name='gdouble', ctype='gdouble', get_type='G_TYPE_DOUBLE')

# Types which correspond exactly to standard C99 types, but are available to use even if your compiler does not support C99
TYPE_OFFSET = RegisteredType(gtype_name='goffset', ctype='goffset', get_type='G_TYPE_INT64')
TYPE_INTPTR = RegisteredType(gtype_name='gintptr', ctype='gintptr', get_type='G_TYPE_POINTER')
TYPE_UINTPTR = RegisteredType(gtype_name='guintptr', ctype='guintptr', get_type='G_TYPE_POINTER')

# Fundamental types
TYPE_OBJECT = RegisteredType(gtype_name='GObject', ctype='GObject', get_type='G_TYPE_OBJECT')
TYPE_VARIANT = RegisteredType(gtype_name='GVariant', ctype='GVariant', get_type='G_TYPE_VARIANT')

TYPE_CHECKSUM = RegisteredType(gtype_name='GChecksum', ctype='GChecksum', get_type='G_TYPE_CHECKSUM')

# Enumeration and flag types
# https://developer.gnome.org/gobject/stable/gobject-Enumeration-and-Flag-Types.html
TYPE_ENUM = RegisteredType(gtype_name='GEnum', ctype='gint', get_type='G_TYPE_ENUM')
TYPE_FLAGS = RegisteredType(gtype_name='GFlags', ctype='gint', get_type='G_TYPE_FLAGS')

# C99 types
TYPE_LONG_LONG = RegisteredType(gtype_name='long long', ctype='long long', get_type='G_TYPE_INT64')
TYPE_LONG_ULONG = RegisteredType(gtype_name='unsigned long long', ctype='unsigned long long', get_type='G_TYPE_UINT64')
# NOTE: Size of 'long double' is bigger than largest GType
# https://github.com/ocamllabs/ocaml-ctypes/blob/master/src/ctypes/ldouble_stubs.c
# https://developer.gnome.org/gobject/stable/gobject-Type-Information.html#g-type-register-fundamental
# https://arrow.apache.org/docs/c_glib/arrow-glib/basic-data-type-classes.html#GARROW-TYPE-DECIMAL128-DATA-TYPE:CAPS
# https://github.com/apache/arrow/blob/master/c_glib/arrow-glib/decimal128.cpp
# https://github.com/apache/arrow/blob/master/c_glib/arrow-glib/decimal128.h
TYPE_LONG_DOUBLE = RegisteredType(gtype_name='long double', ctype='long double', get_type='G_TYPE_DOUBLE')
TYPE_UNICHAR = RegisteredType(gtype_name='gunichar', ctype='gunichar', get_type='G_TYPE_INT')
TYPE_UNICHAR2 = RegisteredType(gtype_name='gunichar2', ctype='gunichar2', get_type='G_TYPE_INT')

# C types with semantics overlaid
TYPE_GTYPE = RegisteredType(gtype_name='GType', ctype='GType', get_type='G_TYPE_GTYPE')
TYPE_STRING = RegisteredType(gtype_name='utf8', ctype='gchar*', get_type='G_TYPE_STRING')
TYPE_FILENAME = RegisteredType(gtype_name='filename', ctype='gchar*', get_type='G_TYPE_STRING')

# Boxed types
# https://developer.gnome.org/gobject/stable/gobject-Boxed-Types.html
TYPE_BOXED = RegisteredType(gtype_name='GBoxed', ctype='GBoxed', get_type='G_TYPE_BOXED')
TYPE_HASH_TABLE = RegisteredType(gtype_name='GHashTable', ctype='GHashTable', get_type='G_TYPE_HASH_TABLE')
TYPE_DATE = RegisteredType(gtype_name='GDate', ctype='GDate', get_type='G_TYPE_DATE')
TYPE_GSTRING = RegisteredType(gtype_name='GString', ctype='GString', get_type='G_TYPE_GSTRING')
TYPE_STRV = RegisteredType(gtype_name='GStrv', ctype='gchar**', get_type='G_TYPE_STRV')
TYPE_REGEX = RegisteredType(gtype_name='GRegex', ctype='GRegex', get_type='G_TYPE_REGEX')
TYPE_MATCH_INFO = RegisteredType(gtype_name='GMatchInfo', ctype='GMatchInfo', get_type='G_TYPE_MATCH_INFO')
# https://developer.gnome.org/glib/stable/glib-Arrays.html
TYPE_ARRAY = RegisteredType(gtype_name='GArray', ctype='GArray', get_type='G_TYPE_ARRAY')
TYPE_BYTE_ARRAY = RegisteredType(gtype_name='GByteArray', ctype='GByteArray', get_type='G_TYPE_BYTE_ARRAY')
TYPE_PTR_ARRAY = RegisteredType(gtype_name='GPtrArray', ctype='GPtrArray', get_type='G_TYPE_PTR_ARRAY')
TYPE_BYTES = RegisteredType(gtype_name='GBytes', ctype='GBytes', get_type='G_TYPE_BYTES')
# https://developer.gnome.org/glib/stable/glib-GVariantType.html
TYPE_VARIANT_TYPE = RegisteredType(gtype_name='GVariantType', ctype='GVariantType', get_type='G_TYPE_VARIANT_TYPE')
TYPE_ERROR = RegisteredType(gtype_name='GError', ctype='GError', get_type='G_TYPE_ERROR')
TYPE_DATE_TIME = RegisteredType(gtype_name='GDateTime', ctype='GDateTime', get_type='G_TYPE_DATE_TIME')
TYPE_TIME_ZONE = RegisteredType(gtype_name='GTimeZone', ctype='GTimeZone', get_type='G_TYPE_TIME_ZONE')
TYPE_IO_CHANNEL = RegisteredType(gtype_name='GIOChannel', ctype='GIOChannel', get_type='G_TYPE_IO_CHANNEL')
TYPE_IO_CONDITION = RegisteredType(gtype_name='GIOCondition', ctype='GIOCondition', get_type='G_TYPE_IO_CONDITION')
TYPE_VARIANT_BUILDER = RegisteredType(gtype_name='GVariantBuilder', ctype='GVariantBuilder', get_type='G_TYPE_VARIANT_BUILDER')
TYPE_VARIANT_DICT = RegisteredType(gtype_name='GVariantDict', ctype='GVariantDict', get_type='G_TYPE_VARIANT_DICT')
TYPE_KEY_FILE = RegisteredType(gtype_name='GKeyFile', ctype='GKeyFile', get_type='G_TYPE_KEY_FILE')
TYPE_MAIN_CONTEXT = RegisteredType(gtype_name='GMainContext', ctype='GMainContext', get_type='G_TYPE_MAIN_CONTEXT')
TYPE_MAIN_LOOP = RegisteredType(gtype_name='GMainLoop', ctype='GMainLoop', get_type='G_TYPE_MAIN_LOOP')
TYPE_MAPPED_FILE = RegisteredType(gtype_name='GMappedFile', ctype='GMappedFile', get_type='G_TYPE_MAPPED_FILE')
TYPE_MARKUP_PARSE_CONTEXT = RegisteredType(gtype_name='GMarkupParseContext', ctype='GMarkupParseContext', get_type='G_TYPE_MARKUP_PARSE_CONTEXT')
TYPE_SOURCE = RegisteredType(gtype_name='GSource', ctype='GSource', get_type='G_TYPE_SOURCE')
TYPE_POLLFD = RegisteredType(gtype_name='GPollFD', ctype='GPollFD', get_type='G_TYPE_POLLFD')
TYPE_THREAD = RegisteredType(gtype_name='GThread', ctype='GThread', get_type='G_TYPE_THREAD')
TYPE_OPTION_GROUP = RegisteredType(gtype_name='GOptionGroup', ctype='GOptionGroup', get_type='G_TYPE_OPTION_GROUP')

# Parameters and values
# https://developer.gnome.org/gobject/stable/gobject-Standard-Parameter-and-Value-Types.html
TYPE_PARAM = RegisteredType(gtype_name='GParam', ctype='GParamSpec', get_type='G_TYPE_PARAM')
TYPE_PARAM_CHAR = RegisteredType(gtype_name='GParamChar', ctype='GParamChar', get_type='G_TYPE_PARAM_CHAR')
TYPE_PARAM_UCHAR = RegisteredType(gtype_name='GParamUChar', ctype='GParamUChar', get_type='G_TYPE_PARAM_UCHAR')
TYPE_PARAM_BOOLEAN = RegisteredType(gtype_name='GParamBoolean', ctype='GParamBoolean', get_type='G_TYPE_PARAM_BOOLEAN')
TYPE_PARAM_INT = RegisteredType(gtype_name='GParamInt', ctype='GParamInt', get_type='G_TYPE_PARAM_INT')
TYPE_PARAM_UINT = RegisteredType(gtype_name='GParamUInt', ctype='GParamUInt', get_type='G_TYPE_PARAM_UINT')
TYPE_PARAM_LONG = RegisteredType(gtype_name='GParamLong', ctype='GParamLong', get_type='G_TYPE_PARAM_LONG')
TYPE_PARAM_ULONG = RegisteredType(gtype_name='GParamULong', ctype='GParamULong', get_type='G_TYPE_PARAM_ULONG')
TYPE_PARAM_INT64 = RegisteredType(gtype_name='GParamInt64', ctype='GParamInt64', get_type='G_TYPE_PARAM_INT64')
TYPE_PARAM_UINT64 = RegisteredType(gtype_name='GParamUInt64', ctype='GParamUInt64', get_type='G_TYPE_PARAM_UINT64')
TYPE_PARAM_UNICHAR = RegisteredType(gtype_name='GParamUnichar', ctype='GParamUnichar', get_type='G_TYPE_PARAM_UNICHAR')
TYPE_PARAM_ENUM = RegisteredType(gtype_name='GParamEnum', ctype='GParamEnum', get_type='G_TYPE_PARAM_ENUM')
TYPE_PARAM_FLAGS = RegisteredType(gtype_name='GParamFlags', ctype='GParamFlags', get_type='G_TYPE_PARAM_FLAGS')
TYPE_PARAM_FLOAT = RegisteredType(gtype_name='GParamFloat', ctype='GParamFloat', get_type='G_TYPE_PARAM_FLOAT')
TYPE_PARAM_DOUBLE = RegisteredType(gtype_name='GParamDouble', ctype='GParamDouble', get_type='G_TYPE_PARAM_DOUBLE')
TYPE_PARAM_STRING = RegisteredType(gtype_name='GParamString', ctype='GParamString', get_type='G_TYPE_PARAM_STRING')
TYPE_PARAM_PARAM = RegisteredType(gtype_name='GParamParam', ctype='GParamParam', get_type='G_TYPE_PARAM_PARAM')
TYPE_PARAM_BOXED = RegisteredType(gtype_name='GParamBoxed', ctype='GParamBoxed', get_type='G_TYPE_PARAM_BOXED')
TYPE_PARAM_POINTER = RegisteredType(gtype_name='GParamPointer', ctype='GParamPointer', get_type='G_TYPE_PARAM_POINTER')
TYPE_PARAM_VALUE_ARRAY = RegisteredType(gtype_name='GParamValueArray', ctype='GParamValueArray', get_type='G_TYPE_PARAM_VALUE_ARRAY')
TYPE_PARAM_OBJECT = RegisteredType(gtype_name='GParamObject', ctype='GParamObject', get_type='G_TYPE_PARAM_OBJECT')
TYPE_PARAM_OVERRIDE = RegisteredType(gtype_name='GParamOverride', ctype='GParamOverride', get_type='G_TYPE_PARAM_OVERRIDE')
TYPE_PARAM_GTYPE = RegisteredType(gtype_name='GParamGType', ctype='GParamGType', get_type='G_TYPE_PARAM_GTYPE')
TYPE_PARAM_VARIANT = RegisteredType(gtype_name='GParamVariant', ctype='GParamVariant', get_type='G_TYPE_PARAM_VARIANT')

REGISTERED_TYPES = [TYPE_INVALID,
TYPE_NONE,
TYPE_INTERFACE,
TYPE_BOOLEAN,
TYPE_SIZE,
TYPE_SSIZE,
TYPE_INT8,
TYPE_UINT8,
TYPE_INT16,
TYPE_UINT16,
TYPE_INT32,
TYPE_UINT32,
TYPE_INT64,
TYPE_UINT64,
TYPE_ANY,
TYPE_CONSTPOINTER,
TYPE_CHAR,
TYPE_UCHAR,
TYPE_INT,
TYPE_UINT,
TYPE_SHORT,
TYPE_USHORT,
TYPE_LONG,
TYPE_ULONG,
TYPE_FLOAT,
TYPE_DOUBLE,
TYPE_OFFSET,
TYPE_INTPTR,
TYPE_UINTPTR,
TYPE_OBJECT,
TYPE_VARIANT,
TYPE_CHECKSUM,
TYPE_ENUM,
TYPE_FLAGS,
TYPE_LONG_LONG,
TYPE_LONG_ULONG,
TYPE_LONG_DOUBLE,
TYPE_UNICHAR,
TYPE_UNICHAR2,
TYPE_GTYPE,
TYPE_STRING,
TYPE_FILENAME,
TYPE_BOXED,
TYPE_HASH_TABLE,
TYPE_DATE,
TYPE_GSTRING,
TYPE_STRV,
TYPE_REGEX,
TYPE_MATCH_INFO,
TYPE_ARRAY,
TYPE_BYTE_ARRAY,
TYPE_PTR_ARRAY,
TYPE_BYTES,
TYPE_VARIANT_TYPE,
TYPE_ERROR,
TYPE_DATE_TIME,
TYPE_TIME_ZONE,
TYPE_IO_CHANNEL,
TYPE_IO_CONDITION,
TYPE_VARIANT_BUILDER,
TYPE_VARIANT_DICT,
TYPE_KEY_FILE,
TYPE_MAIN_CONTEXT,
TYPE_MAIN_LOOP,
TYPE_MAPPED_FILE,
TYPE_MARKUP_PARSE_CONTEXT,
TYPE_SOURCE,
TYPE_POLLFD,
TYPE_THREAD,
TYPE_OPTION_GROUP,
TYPE_PARAM,
TYPE_PARAM_CHAR,
TYPE_PARAM_UCHAR,
TYPE_PARAM_BOOLEAN,
TYPE_PARAM_INT,
TYPE_PARAM_UINT,
TYPE_PARAM_LONG,
TYPE_PARAM_ULONG,
TYPE_PARAM_INT64,
TYPE_PARAM_UINT64,
TYPE_PARAM_UNICHAR,
TYPE_PARAM_ENUM,
TYPE_PARAM_FLAGS,
TYPE_PARAM_FLOAT,
TYPE_PARAM_DOUBLE,
TYPE_PARAM_STRING,
TYPE_PARAM_PARAM,
TYPE_PARAM_BOXED,
TYPE_PARAM_POINTER,
TYPE_PARAM_VALUE_ARRAY,
TYPE_PARAM_OBJECT,
TYPE_PARAM_OVERRIDE,
TYPE_PARAM_GTYPE,
TYPE_PARAM_VARIANT,
]

registered_type_names = {}
registered_ctype_names = {}
for typeval in REGISTERED_TYPES:
    registered_type_names[typeval.gtype_name] = typeval
    registered_ctype_names[typeval.ctype] = typeval

class CmakeCodeContext(object):
    def __init__(self):
        self._pkg_index = 0

    def next_pkg_index(self):
        self._pkg_index += 1
        return self._pkg_index

def _get_option_parser():
    parser = optparse.OptionParser('%prog [options]',
                                   version='%prog ' + giscanner.__version__)
    parser.add_option('', "--output",
                      action="store", dest="output_path", default=None,
                      help="Path to output GIR directory")
    parser.add_option('', "--passthrough",
                    action="store_true", dest="passthrough", default=False,
                    help="If true, parse and rewrite GIR file without checking")
    parser.add_option('', "--typeinfo",
                    action="store_true", dest="typeinfo", default=False,
                    help="If true, parse and write GIR file type information program")
    parser.add_option('', "--propertyinfo",
                    action="store_true", dest="propertyinfo", default=False,
                    help="If true, parse and write GIR file property information program")
    parser.add_option('', "--signalinfo",
                    action="store_true", dest="signalinfo", default=False,
                    help="If true, parse and write GIR file signal information program")
    parser.add_option("", "--filelist",
                      action="store", dest="filelist", default=[],
                      help="file containing GIR files to be checked")
    parser.add_option("", "--mergeinfo",
                      action="store", dest="mergeinfo", default=[],
                      help="type information and property information files to be merged")
    parser.add_option("", "--excludegtypes",
                      action="store", dest="excludegtypes", default=[],
                      help="file containing gtypes to be excluded")
    parser.add_option("", "--excludeheaders",
                      action="store", dest="excludeheaders", default=[],
                      help="file containing headers to be excluded")
    parser.add_option("", "--excluderegistered",
                      action="store", dest="excluderegistered", default=[],
                      help="file containing types to be excluded from registered types")
    return parser


def _error(msg):
    raise SystemExit('ERROR: %s' % (msg, ))

def _write_type_names(writer, exclude_gtypes, namespace_name, type_names, infoformat="typeinfo", unregistered=False):
    fundamental_gtype = 'G_TYPE_INVALID'
    for key, node in type_names.items():
        node_type = "unknown"
        if isinstance(node, ast.Function):
            node_type = "function"
        elif isinstance(node, ast.FunctionMacro):
            node_type = "functionmacro"
        elif isinstance(node, ast.Enum):
            node_type = "enum"
            fundamental_gtype = 'G_TYPE_ENUM'
        elif isinstance(node, ast.Bitfield):
            node_type = "bitfield"
            fundamental_gtype = 'G_TYPE_FLAGS'
        elif isinstance(node, ast.Class):
            node_type = "class"
            fundamental_gtype = 'G_TYPE_OBJECT'
        elif isinstance(node, ast.Interface):
            node_type = "interface"
            fundamental_gtype = 'G_TYPE_INTERFACE'
        elif isinstance(node, ast.Callback):
            node_type = "callback"
            fundamental_gtype = 'G_TYPE_POINTER'
        elif isinstance(node, ast.Record):
            node_type = "record"
            fundamental_gtype = 'G_TYPE_BOXED'
        elif isinstance(node, ast.Union):
            node_type = "union"
            fundamental_gtype = 'G_TYPE_BOXED'
        elif isinstance(node, ast.Boxed):
            node_type = "boxed"
            fundamental_gtype = 'G_TYPE_BOXED'
        elif isinstance(node, ast.Member):
            node_type = "member" # enum or bitfield member
            fundamental_gtype = 'G_TYPE_INT'
        elif isinstance(node, ast.Alias):
            node_type = "alias"
        elif isinstance(node, ast.Constant):
            node_type = "constant"
            fundamental_gtype = 'G_TYPE_INVALID' # C define can be any number of types
        elif isinstance(node, ast.Type):
            node_type = "type"
        elif isinstance(node, ast.Registered):
            node_type = "registered"

        gtype_name = None
        get_type   = None

        if hasattr(node, 'gtype_name') and node.gtype_name is not None:
            gtype_name = node.gtype_name
        elif unregistered == False:
            gtype_name = node.target_fundamental
        else:
            gtype_name = ""

        if hasattr(node, 'get_type') and node.get_type is not None:
            # Handle when get_type is "intern"
            get_type = node.get_type
            if get_type == 'intern':
                type_node = registered_type_names.get(gtype_name)
                if type_node is not None:
                    get_type = type_node.get_type
                else:
                    get_type = node.gtype_name + "not found"
            else:
                if not get_type.startswith("G_TYPE_"):
                    get_type += '()'
        elif unregistered == False:
            get_type = 'g_type_from_name("%s")' % node.target_fundamental
        else:
            get_type = fundamental_gtype

        if hasattr(node, 'ctype') and node.ctype is not None:
            ctype = node.ctype
        elif hasattr(node, 'complete_ctype') and node.complete_ctype is not None:
            ctype = node.complete_ctype
        elif gtype_name is not None:
            # NOTE: ctype is missing from GIR file
            writer.write_line("""/* WARNING: ctype is missing for '%s' in GIR file */""" % (gtype_name,))
            ctype = gtype_name

        if gtype_name is not None:
            if gtype_name in exclude_gtypes:
                writer.write_source("""/*""")
        if "signalinfo" == infoformat:
            writer.write_line("""print_object_signals(stdout,%s,"%s","%s","%s");""" % (get_type.replace('"', '\\"'), namespace_name, node_type, gtype_name))
        elif "propertyinfo" == infoformat:
            writer.write_line("""print_object_properties(stdout,%s,"%s","%s","%s");""" % (get_type.replace('"', '\\"'), namespace_name, node_type, gtype_name))
        else:
            writer.write_source("""printf("%s,%s,%s,%s,%s,%s\\n",""")
            writer.write_line(""" "%s", "%s", "%s", "%s", "%s", g_type_fundamental_tostring((unsigned long)%s));""" % (namespace_name, node_type, gtype_name, ctype, get_type.replace('"', '\\"'), get_type,), False)
        if gtype_name is not None:
            if gtype_name in exclude_gtypes:
                writer.write_line("""*/""")

def typeinformation_gir(exclude_gtypes, exclude_headers, code_context, path, f, cmake_writer, header_writer, main_writer, infoformat):
    parser = GIRParser()
    parser.parse(path)

    namespace = parser.get_namespace()

    writer = CodeWriter()

    i = 0
    for pkg in sorted(set(namespace.exported_packages)):
        i = code_context.next_pkg_index()
        cmake_writer.write_line("""pkg_check_modules (PKG%s REQUIRED %s)""" % (str(i), pkg,))
        cmake_writer.write_line("""list(APPEND PROJECT_INCLUDE_DIRECTORIES ${PKG%s_INCLUDE_DIRS})""" % (str(i),))
        cmake_writer.write_line("""list(APPEND PROJECT_LINK_DIRECTORIES ${PKG%s_LIBRARY_DIRS})""" % (str(i),))
        cmake_writer.write_line("""set(CMAKE_C_FLAGS "${CMAKE_C_FLAGS} ${PKG%s_CFLAGS}")""" % (str(i),))
        cmake_writer.write_line("""list(APPEND PROJECT_LIBRARIES ${PKG%s_LIBRARIES})""" % (str(i),))
        cmake_writer.write_newline()
    
    writer.write_newline()
    writer.write_line('''#include "girtypes.h"
#include <glib-2.0/glib-object.h>''')
    for c_include in sorted(set(namespace.c_includes)):
        if c_include in exclude_headers:
            writer.write_comment('#include "%s"' % (c_include,))
        else:
            writer.write_line('#include "%s"' % (c_include,))
    writer.write_newline()

    namespace_name = namespace.name
    attrs = []

    writer.write_line("""void print_%s_types()""" % (namespace_name,))
    header_writer.write_line("""void print_%s_types();""" % (namespace_name,))
    main_writer.write_line("""    fprintf(stderr, "processing %s types....\\n");""" % (namespace_name,))
    main_writer.write_line("""    print_%s_types();""" % (namespace_name,))
    with writer.scopecontext('function', attrs):
        _write_type_names(writer, exclude_gtypes, namespace_name, namespace.type_names, infoformat)

    f.write(writer.get_encoded_source())

    return code_context

def typeinformation_ctypes(exclude_gtypes, exclude_headers, code_context, path, f, cmake_writer, header_writer, main_writer, infoformat):
    parser = GIRParser()
    parser.parse(path)

    namespace = parser.get_namespace()

    # C types that are not registered types

    unregistered_ctypes = {}
    for key, node in namespace.ctypes.items():
        
        if hasattr(node, 'gtype_name') and node.gtype_name is not None:
            continue

        if hasattr(node, 'ctype'):
            unregistered_ctypes[node.ctype] = node

    writer = CodeWriter()
    
    writer.write_newline()
    writer.write_line('''#include "girtypes.h"
#include <glib-2.0/glib-object.h>''')
    writer.write_newline()

    namespace_name = namespace.name
    attrs = []

    writer.write_line("""void print_%s_ctypes_types()""" % (namespace_name,))
    header_writer.write_line("""void print_%s_types();""" % (namespace_name,))
    main_writer.write_line("""    fprintf(stderr, "processing %s ctypes types....\\n");""" % (namespace_name,))
    main_writer.write_line("""    print_%s_ctypes_types();""" % (namespace_name,))
    with writer.scopecontext('function', attrs):
        if "typeinfo" == infoformat:
            _write_type_names(writer, exclude_gtypes, namespace_name, unregistered_ctypes, infoformat, True)

    f.write(writer.get_encoded_source())

    return code_context


def typeinformation_registered(exclude_gtypes, exclude_headers, code_context, path, f, cmake_writer, header_writer, main_writer, infoformat):
    writer = CodeWriter()
    
    writer.write_newline()
    writer.write_line('''#include "girtypes.h"
#include <glib-2.0/glib-object.h>''')
    writer.write_newline()

    namespace_name = "registered"
    attrs = []

    writer.write_line("""void print_%s_types()""" % (namespace_name,))
    header_writer.write_line("""void print_%s_types();""" % (namespace_name,))
    main_writer.write_line("""    fprintf(stderr, "processing %s types....\\n");""" % (namespace_name,))
    main_writer.write_line("""    print_%s_types();""" % (namespace_name,))
    with writer.scopecontext('function', attrs):
        if "typeinfo" == infoformat:
            _write_type_names(writer, exclude_gtypes, namespace_name, registered_type_names, infoformat)

    f.write(writer.get_encoded_source())

    return code_context

def passthrough_gir(path, f):
    parser = GIRParser()
    parser.parse(path)

    writer = PassthroughWriter(parser.get_namespace())
    f.write(writer.get_encoded_xml())

def process_gir(path, f, exclude_registered):
    parser = GIRParser()
    parser.parse(path)

    writer = GIRWriter(parser.get_namespace(), exclude_registered=exclude_registered)
    f.write(writer.get_encoded_xml())

def extract_filenames(args):
    filenames = []
    for arg in args:
        # We don't support real C++ parsing yet, but we should be able
        # to understand C API implemented in C++ files.
        if os.path.splitext(arg)[1] in ALL_EXTS:
            if not os.path.exists(arg):
                _error('%s: no such a file or directory' % (arg, ))
            # Make absolute, because we do comparisons inside scannerparser.c
            # against the absolute path that cpp will give us
            filenames.append(arg)
    return filenames


def extract_filelist(options):
    filenames = []
    if not os.path.exists(options.filelist):
        _error('%s: no such filelist file' % (options.filelist, ))
    with open(options.filelist, "r") as filelist_file:
        lines = filelist_file.readlines()
    for line in lines:
        # We don't support real C++ parsing yet, but we should be able
        # to understand C API implemented in C++ files.
        filename = line.strip()
        if filename.startswith("#"):
            # Skip files that do not build on platform
            # https://github.com/haskell-gi/haskell-gi/issues/218
            # https://gitlab.gnome.org/GNOME/glib/issues/1717
            continue
        if (filename.endswith('.gir')):
            filename = filename.replace("$CWD", os.getcwd())
            if not os.path.exists(filename):
                _error('%s: Invalid filelist entry-no such file or directory' % (line, ))
            # Make absolute, because we do comparisons inside scannerparser.c
            # against the absolute path that cpp will give us
            filenames.append(filename)
    return filenames

def extract_typeinfo(options):
    typeinfo = {}
    typeinfo_filename, propinfo_filename = options.mergeinfo.split(",")
    if not os.path.exists(typeinfo_filename):
        _error('%s: no such type information file' % (typeinfo_filename, ))
    with open(typeinfo_filename, "r") as typeinfo_file:
        lines = typeinfo_file.readlines()
    for line in lines:
        namespace_name, node_type, gtype_name, ctype, get_type, fundamental_type = line.strip().split(",")
        typeinfo[gtype_name] = RegisteredType(gtype_name=gtype_name, ctype=ctype, get_type=get_type, fundamental_type=fundamental_type)

    return typeinfo

def extract_propinfo(options, exclude_gtypes, typeinfo):
    propinfo = []
    typeinfo_filename, propinfo_filename = options.mergeinfo.split(",")
    if not os.path.exists(propinfo_filename):
        _error('%s: no such property information file' % (propinfo_filename, ))
    with open(propinfo_filename, "r") as propinfo_file:
        lines = propinfo_file.readlines()
    for line in lines:
        namespace_name, node_type, gtype_name, type_name, is_pointer, flags, property_name, fundamental_type = line.strip().split(",")
        type_node = typeinfo.get(type_name)
        if type_node is not None:
            get_type = type_node.get_type
        else:
            type_node = registered_ctype_names.get(type_name+is_pointer)
            if type_node is not None:
                get_type = type_node.get_type
            else:
                if type_name in exclude_gtypes:
                    get_type = "exclude"
                else:
                    get_type = "?"

        propinfo.append(line.strip() + "," + get_type + "\n")

    return propinfo

def extract_excluderegisteredset(options):
    exclude_set = set()
    if not os.path.exists(options.excluderegistered):
        _error('%s: no such excluderegistered file' % (options.excluderegistered, ))
    with open(options.excluderegistered, "r") as exclude_file:
        lines = exclude_file.readlines()
    for line in lines:
        elem = line.strip()
        if elem.startswith("#"):
            # Skip commented out elements
            continue

        exclude_set.add(elem)
    return exclude_set

def extract_excludegtypesset(options):
    exclude_set = set()
    if not os.path.exists(options.excludegtypes):
        _error('%s: no such excludegtypes file' % (options.excludegtypes, ))
    with open(options.excludegtypes, "r") as exclude_file:
        lines = exclude_file.readlines()
    for line in lines:
        elem = line.strip()
        if elem.startswith("#"):
            # Skip commented out gtypes
            continue

        exclude_set.add(elem)
    return exclude_set

def extract_excludeheadersset(options):
    exclude_set = set()
    if not os.path.exists(options.excludeheaders):
        _error('%s: no such excludeheaders file' % (options.excludeheaders, ))
    with open(options.excludeheaders, "r") as exclude_file:
        lines = exclude_file.readlines()
    for line in lines:
        elem = line.strip()
        if elem.startswith("#"):
            # Skip commented out elements
            continue

        exclude_set.add(elem)
    return exclude_set

def scanner_main(args):
    parser = _get_option_parser()
    (options, args) = parser.parse_args(args)

    if hasattr(options, 'filelist') and options.filelist:
        filenames = extract_filelist(options)
    else:
        filenames = extract_filenames(args)
    filenames = [os.path.realpath(f) for f in filenames]

    if hasattr(options, 'excluderegistered') and options.excluderegistered:
        exclude_registered = extract_excluderegisteredset(options)
    else:
        exclude_registered = set()

    if hasattr(options, 'excludegtypes') and options.excludegtypes:
        exclude_gtypes = extract_excludegtypesset(options)
    else:
        exclude_gtypes = set()

    if hasattr(options, 'excludeheaders') and options.excludeheaders:
        exclude_headers = extract_excludeheadersset(options)
    else:
        exclude_headers = set()

    outputPath = os.path.abspath(os.path.expanduser(options.output_path))

    if os.path.isdir(outputPath) == False:
        # Check if output directory exists
        print("Error: output path '" + outputPath + "' does not exist.")
        sys.exit(1)

    if hasattr(options, 'mergeinfo') and options.mergeinfo:
        typeinfo_filename, propertyinfo_filename = options.mergeinfo.split(",")
        typeinfo = extract_typeinfo(options)
        propinfo = extract_propinfo(options, exclude_gtypes, typeinfo)

        path, filename = os.path.split(propertyinfo_filename)
        filename, file_extension = os.path.splitext(filename)
        filename = filename + "-merged" + file_extension
        outputFilename = os.path.join(outputPath, filename)
        with open(outputFilename, 'w') as o:
            for line in propinfo:
                o.write(line)
            o.flush()
    elif options.typeinfo == True or options.propertyinfo == True or options.signalinfo == True:
        if options.propertyinfo == True:
            infoformat = "propertyinfo"
        elif options.signalinfo == True:
            infoformat = "signalinfo"
        elif options.typeinfo == True:
            infoformat = "typeinfo"
        else:
            infoformat = ""
        # https://cmake.org/cmake/help/latest/module/FindPkgConfig.html
        outputCmakeFilename = os.path.join(outputPath, 'CMakeLists.txt')
        cmake_writer = CodeWriter(COMMENT_HASH)
        cmake_code_context = CmakeCodeContext()
        cmake_writer.write_line("""cmake_minimum_required(VERSION 3.10)
project (girtypes)

find_package (PkgConfig REQUIRED)

set(PROJECT_SOURCES ${PROJECT_SOURCES} girtypes.c)

""")
        outputHeaderFilename = os.path.join(outputPath, 'girtypes.h')
        header_writer = CodeWriter()

        outputMainFilename = os.path.join(outputPath, 'girtypes.c')
        main_writer = CodeWriter()

        # https://github.com/GNOME/gtk-doc/blob/master/gtkdoc/scangobj.py
        main_writer.write_line('''#include "girtypes.h"

const char * g_type_fundamental_tostring(GType gtype) {
  GType _gtype = g_type_fundamental(gtype);

  if (_gtype == G_TYPE_INVALID) {
    return "G_TYPE_INVALID";
  }
  else if (_gtype == G_TYPE_NONE) {
    return "G_TYPE_NONE";
  }
  else if (_gtype == G_TYPE_INTERFACE) {
    return "G_TYPE_INTERFACE";
  }
  else if (_gtype == G_TYPE_CHAR) {
    return "G_TYPE_CHAR";
  }
  else if (_gtype == G_TYPE_UCHAR) {
    return "G_TYPE_UCHAR";
  }
  else if (_gtype == G_TYPE_BOOLEAN) {
    return "G_TYPE_BOOLEAN";
  }
  else if (_gtype == G_TYPE_INT) {
    return "G_TYPE_INT";
  }
  else if (_gtype == G_TYPE_UINT) {
    return "G_TYPE_UINT";
  }
  else if (_gtype == G_TYPE_LONG) {
    return "G_TYPE_LONG";
  }
  else if (_gtype == G_TYPE_ULONG) {
    return "G_TYPE_ULONG";
  }
  else if (_gtype == G_TYPE_INT64) {
    return "G_TYPE_INT64";
  }
  else if (_gtype == G_TYPE_UINT64) {
    return "G_TYPE_UINT64";
  }
  else if (_gtype == G_TYPE_ENUM) {
    return "G_TYPE_ENUM";
  }
  else if (_gtype == G_TYPE_FLAGS) {
    return "G_TYPE_FLAGS";
  }
  else if (_gtype == G_TYPE_FLOAT) {
    return "G_TYPE_FLOAT";
  }
  else if (_gtype == G_TYPE_DOUBLE) {
    return "G_TYPE_DOUBLE";
  }
  else if (_gtype == G_TYPE_STRING) {
    return "G_TYPE_STRING";
  }
  else if (_gtype == G_TYPE_POINTER) {
    return "G_TYPE_POINTER";
  }
  else if (_gtype == G_TYPE_BOXED) {
    return "G_TYPE_BOXED";
  }
  else if (_gtype == G_TYPE_PARAM) {
    return "G_TYPE_PARAM";
  }
  else if (_gtype == G_TYPE_OBJECT) {
    return "G_TYPE_OBJECT";
  }
  else if (_gtype == G_TYPE_GTYPE) {
    return "G_TYPE_GTYPE";
  }
  else if (_gtype == G_TYPE_VARIANT) {
    return "G_TYPE_VARIANT";
  }
  else if (_gtype == G_TYPE_CHECKSUM) {
    return "G_TYPE_CHECKSUM";
  }
  else if (_gtype == G_TYPE_PARAM_BOOLEAN) {
    return "G_TYPE_PARAM_BOOLEAN";
  }
  else if (_gtype == G_TYPE_PARAM_CHAR) {
    return "G_TYPE_PARAM_CHAR";
  }
  else if (_gtype == G_TYPE_PARAM_UCHAR) {
    return "G_TYPE_PARAM_UCHAR";
  }
  else if (_gtype == G_TYPE_PARAM_INT) {
    return "G_TYPE_PARAM_INT";
  }
  else if (_gtype == G_TYPE_PARAM_UINT) {
    return "G_TYPE_PARAM_UINT";
  }
  else if (_gtype == G_TYPE_PARAM_LONG) {
    return "G_TYPE_PARAM_LONG";
  }
  else if (_gtype == G_TYPE_PARAM_ULONG) {
    return "G_TYPE_PARAM_ULONG";
  }
  else if (_gtype == G_TYPE_PARAM_INT64) {
    return "G_TYPE_PARAM_INT64";
  }
  else if (_gtype == G_TYPE_PARAM_UINT64) {
    return "G_TYPE_PARAM_UINT64";
  }
  else if (_gtype == G_TYPE_PARAM_FLOAT) {
    return "G_TYPE_PARAM_FLOAT";
  }
  else if (_gtype == G_TYPE_PARAM_DOUBLE) {
    return "G_TYPE_PARAM_DOUBLE";
  }
  else if (_gtype == G_TYPE_PARAM_ENUM) {
    return "G_TYPE_PARAM_ENUM";
  }
  else if (_gtype == G_TYPE_PARAM_FLAGS) {
    return "G_TYPE_PARAM_FLAGS";
  }
  else if (_gtype == G_TYPE_PARAM_STRING) {
    return "G_TYPE_PARAM_STRING";
  }
  else if (_gtype == G_TYPE_PARAM_PARAM) {
    return "G_TYPE_PARAM_PARAM";
  }
  else if (_gtype == G_TYPE_PARAM_BOXED) {
    return "G_TYPE_PARAM_BOXED";
  }
  else if (_gtype == G_TYPE_PARAM_POINTER) {
    return "G_TYPE_PARAM_POINTER";
  }
  else if (_gtype == G_TYPE_PARAM_OBJECT) {
    return "G_TYPE_PARAM_OBJECT";
  }
  else if (_gtype == G_TYPE_PARAM_UNICHAR) {
    return "G_TYPE_PARAM_UNICHAR";
  }
  else if (_gtype == G_TYPE_PARAM_VALUE_ARRAY) {
    return "G_TYPE_PARAM_VALUE_ARRAY";
  }
  else if (_gtype == G_TYPE_PARAM_OVERRIDE) {
    return "G_TYPE_PARAM_OVERRIDE";
  }
  else if (_gtype == G_TYPE_PARAM_OVERRIDE) {
    return "G_TYPE_PARAM_OVERRIDE";
  }
  else if (_gtype == G_TYPE_PARAM_GTYPE) {
    return "G_TYPE_PARAM_GTYPE";
  }
  else if (_gtype == G_TYPE_PARAM_VARIANT) {
    return "G_TYPE_PARAM_VARIANT";
  }

  return "UNKNOWN";
}

const gchar * get_type_name (GType type, gboolean * is_pointer) {
    const gchar *type_name;
    *is_pointer = FALSE;
    type_name = g_type_name (type);
    switch (type) {
    case G_TYPE_NONE:
    case G_TYPE_CHAR:
    case G_TYPE_UCHAR:
    case G_TYPE_BOOLEAN:
    case G_TYPE_INT:
    case G_TYPE_UINT:
    case G_TYPE_LONG:
    case G_TYPE_ULONG:
    case G_TYPE_FLOAT:
    case G_TYPE_DOUBLE:
    case G_TYPE_POINTER:
        /* These all have normal C type names so they are OK. */
        return type_name;
    case G_TYPE_STRING:
        /* A GtkString is really a gchar*. */
        *is_pointer = TRUE;
        return "gchar";
    case G_TYPE_ENUM:
    case G_TYPE_FLAGS:
        /* We use a gint for both of these. Hopefully a subtype with a decent
        name will be registered and used instead, as GTK+ does itself. */
        return "gint";
    case G_TYPE_BOXED:
        /* The boxed type shouldn't be used itself, only subtypes. Though we
        return 'gpointer' just in case. */
        return "gpointer";
    case G_TYPE_PARAM:
        /* A GParam is really a GParamSpec*. */
        *is_pointer = TRUE;
        return "GParamSpec";
    #if GLIB_CHECK_VERSION (2, 25, 9)
    case G_TYPE_VARIANT:
        *is_pointer = TRUE;
        return "GVariant";
    #endif
    default:
        break;
    }
    /* For all GObject subclasses we can use the class name with a "*",
        e.g. 'GtkWidget *'. */
    if (g_type_is_a (type, G_TYPE_OBJECT))
        *is_pointer = TRUE;
    /* Also catch non GObject root types */
    if (G_TYPE_IS_CLASSED (type))
        *is_pointer = TRUE;
    /* All boxed subtypes will be pointers as well. */
    /* Exception: GStrv */
    if (g_type_is_a (type, G_TYPE_BOXED) &&
        !g_type_is_a (type, G_TYPE_STRV))
        *is_pointer = TRUE;
    /* All pointer subtypes will be pointers as well. */
    if (g_type_is_a (type, G_TYPE_POINTER))
        *is_pointer = TRUE;
    /* But enums are not */
    if (g_type_is_a (type, G_TYPE_ENUM) ||
        g_type_is_a (type, G_TYPE_FLAGS))
        *is_pointer = FALSE;
    return type_name;
}

gint compare_param_specs (const void *a, const void *b) {
  GParamSpec *spec_a = *(GParamSpec **)a;
  GParamSpec *spec_b = *(GParamSpec **)b;
  return strcmp (g_param_spec_get_name (spec_a), g_param_spec_get_name (spec_b));
}

void print_object_properties(FILE *fp, GType object_type, char* namespace_name, char* node_type, char* gtype_name)
{
  gpointer class;
  const gchar *object_class_name;
  guint arg;
  gchar flags[16], *pos;
  GParamSpec **properties;
  guint n_properties;
  gboolean child_prop;
  gboolean style_prop;
  gboolean is_pointer;
  const gchar *type_name;
  gchar *type_desc;
  gchar *default_value;
  if (G_TYPE_IS_OBJECT (object_type))
    {
      class = g_type_class_ref (object_type);
      if (!class) {
        fprintf(stderr, "WARNING: Unable to list properties for %s %s.%s\\n", node_type, namespace_name, gtype_name);
	    return;
      }
      properties = g_object_class_list_properties (class, &n_properties);
    }
#if GLIB_MAJOR_VERSION > 2 || (GLIB_MAJOR_VERSION == 2 && GLIB_MINOR_VERSION >= 3)
  else if (G_TYPE_IS_INTERFACE (object_type))
    {
      class = g_type_default_interface_ref (object_type);
      if (!class) {
        fprintf(stderr, "WARNING: Unable to list properties for %s %s.%s\\n", node_type, namespace_name, gtype_name);
	    return;
      }
      properties = g_object_interface_list_properties (class, &n_properties);
    }
#endif
  else
    return;
  object_class_name = g_type_name (object_type);
  child_prop = FALSE;
  style_prop = FALSE;
  while (TRUE) {
    qsort (properties, n_properties, sizeof (GParamSpec *), compare_param_specs);
    for (arg = 0; arg < n_properties; arg++) {
        GParamSpec *spec = properties[arg];
        const gchar *nick, *blurb, *dot;
        if (spec->owner_type != object_type)
          continue;
        pos = flags;
        /* We use one-character flags for simplicity. */
        if (child_prop && !style_prop)
   	        *pos++ = 'c';
        if (style_prop)
   	        *pos++ = 's';
        if (spec->flags & G_PARAM_READABLE)
 	        *pos++ = 'r';
        if (spec->flags & G_PARAM_WRITABLE)
	        *pos++ = 'w';
        if (spec->flags & G_PARAM_CONSTRUCT)
	        *pos++ = 'x';
        if (spec->flags & G_PARAM_CONSTRUCT_ONLY)
	        *pos++ = 'X';
        *pos = 0;
        nick = g_param_spec_get_nick (spec);
        blurb = g_param_spec_get_blurb (spec);
        dot = "";
        if (blurb) {
            int str_len = strlen (blurb);
            if (str_len > 0  && blurb[str_len - 1] != '.')
                dot = ".";
        }
	    type_name = get_type_name (spec->value_type, &is_pointer);
        fprintf(fp, "%s,%s,%s,%s,%s,%s,%s,%s\\n", namespace_name, node_type, gtype_name, type_name, is_pointer ? "*" : "", flags, g_param_spec_get_name(spec), g_type_fundamental_tostring(G_PARAM_SPEC_VALUE_TYPE(spec)));
      }
    g_free (properties);
#ifdef GTK_IS_CONTAINER_CLASS
    if (!child_prop && GTK_IS_CONTAINER_CLASS (class)) {
      properties = gtk_container_class_list_child_properties (class, &n_properties);
      child_prop = TRUE;
      continue;
    }
#endif
#ifdef GTK_IS_CELL_AREA_CLASS
    if (!child_prop && GTK_IS_CELL_AREA_CLASS (class)) {
      properties = gtk_cell_area_class_list_cell_properties (class, &n_properties);
      child_prop = TRUE;
      continue;
    }
#endif
#ifdef GTK_IS_WIDGET_CLASS
#if GTK_CHECK_VERSION(2,1,0)
    if (!style_prop && GTK_IS_WIDGET_CLASS (class)) {
      properties = gtk_widget_class_list_style_properties (GTK_WIDGET_CLASS (class), &n_properties);
      style_prop = TRUE;
      continue;
    }
#endif
#endif
    break;
  }
}

gint compare_signals (const void *a, const void *b) {
  const guint *signal_a = a;
  const guint *signal_b = b;

  return strcmp (g_signal_name (*signal_a), g_signal_name (*signal_b));
}

/* This prints all the signals of one object. */
void print_object_signals (FILE *fp, GType object_type, char* namespace_name, char* node_type, char* gtype_name) {
  const gchar *object_class_name;
  guint *signals, n_signals;
  guint sig;

  if (G_TYPE_IS_CLASSED (object_type))
    g_type_class_ref (object_type);
  if (G_TYPE_IS_INTERFACE (object_type))
    g_type_default_interface_ref (object_type);

  if (G_TYPE_IS_INSTANTIATABLE (object_type) ||
      G_TYPE_IS_INTERFACE (object_type)) {

    object_class_name = g_type_name (object_type);

    signals = g_signal_list_ids (object_type, &n_signals);
    qsort (signals, n_signals, sizeof (guint), compare_signals);

    for (sig = 0; sig < n_signals; sig++) {
       output_object_signal (fp, object_type, namespace_name, node_type, gtype_name, object_class_name, signals[sig]);
    }
    g_free (signals);
  } else {
    fprintf(stderr, "WARNING: Unable to list signals for %s %s.%s\\n", node_type, namespace_name, gtype_name);
  }
}

/* This outputs one signal. */
void output_object_signal (FILE *fp, GType object_type, char* namespace_name, char* node_type, char* gtype_name, const gchar *object_name, guint signal_id) {
  GSignalQuery query_info;
  const gchar *type_name, *ret_type, *object_arg, *arg_name;
  gchar *pos, *object_arg_lower;
  gboolean is_pointer;
  gchar buffer[1024];
  guint i, param;
  gint param_num, widget_num, event_num, callback_num;
  gint *arg_num;
  gchar signal_name[128];
  gchar flags[16];
  gchar *delim;

  /*  g_print ("Object: %s Signal: %u\\n", object_name, signal_id);*/

  param_num = 1;
  widget_num = event_num = callback_num = 0;

  g_signal_query (signal_id, &query_info);

  /* Output the signal object type and the argument name. We assume the
   * type is a pointer - I think that is OK. We remove "Gtk" or "Gnome" and
   * convert to lower case for the argument name. */
  pos = buffer;
  sprintf (pos, "%s ", object_name);
  pos += strlen (pos);

  /* Try to come up with a sensible variable name for the first arg
   * It chops off 2 know prefixes :/ and makes the name lowercase
   * It should replace lowercase -> uppercase with '_'
   * GFileMonitor -> file_monitor
   * GIOExtensionPoint -> extension_point
   * GtkTreeView -> tree_view
   * if 2nd char is upper case too
   *   search for first lower case and go back one char
   * else
   *   search for next upper case
   */
  if (!strncmp (object_name, "Gtk", 3))
    object_arg = object_name + 3;
  else if (!strncmp (object_name, "Gnome", 5))
    object_arg = object_name + 5;
  else
    object_arg = object_name;

  object_arg_lower = g_ascii_strdown (object_arg, -1);
  sprintf (pos, "*%s|", object_arg_lower);
  pos += strlen (pos);
  if (!strncmp (object_arg_lower, "widget", 6))
    widget_num = 2;
  g_free(object_arg_lower);

  /* Convert signal name to use underscores rather than dashes '-'. */
  strncpy (signal_name, query_info.signal_name, 127);
  signal_name[127] = '\\0';
  for (i = 0; signal_name[i]; i++) {
    if (signal_name[i] == '-')
      signal_name[i] = '_';
  }

  /* Output the signal parameters. */
  delim = "";
  for (param = 0; param < query_info.n_params; param++) {
    type_name = get_type_name (query_info.param_types[param] & ~G_SIGNAL_TYPE_STATIC_SCOPE, &is_pointer);

    /* Most arguments to the callback are called "arg1", "arg2", etc.
       GtkWidgets are called "widget", "widget2", ...
       GtkCallbacks are called "callback", "callback2", ... */
    if (!strcmp (type_name, "GtkWidget")) {
      arg_name = "widget";
      arg_num = &widget_num;
    }
    else if (!strcmp (type_name, "GtkCallback")
             || !strcmp (type_name, "GtkCCallback")) {
      arg_name = "callback";
      arg_num = &callback_num;
    }
    else {
      arg_name = "arg";
      arg_num = &param_num;
    }
    sprintf (pos, "%s%s ", delim, type_name);
    pos += strlen (pos);

    if (!arg_num || *arg_num == 0)
      sprintf (pos, "%s%s", is_pointer ? "*" : " ", arg_name);
    else
      sprintf (pos, "%s%s%i", is_pointer ? "*" : " ", arg_name,
               *arg_num);
    pos += strlen (pos);

    if (arg_num) {
      if (*arg_num == 0)
        *arg_num = 2;
      else
        *arg_num += 1;
    }
    delim = "|";
  }

  pos = flags;
  /* We use one-character flags for simplicity. */
  if (query_info.signal_flags & G_SIGNAL_RUN_FIRST)
    *pos++ = 'f';
  if (query_info.signal_flags & G_SIGNAL_RUN_LAST)
    *pos++ = 'l';
  if (query_info.signal_flags & G_SIGNAL_RUN_CLEANUP)
    *pos++ = 'c';
  if (query_info.signal_flags & G_SIGNAL_NO_RECURSE)
    *pos++ = 'r';
  if (query_info.signal_flags & G_SIGNAL_DETAILED)
    *pos++ = 'd';
  if (query_info.signal_flags & G_SIGNAL_ACTION)
    *pos++ = 'a';
  if (query_info.signal_flags & G_SIGNAL_NO_HOOKS)
    *pos++ = 'h';
  *pos = 0;

  /* Output the return type and function name. */
  ret_type = get_type_name (query_info.return_type & ~G_SIGNAL_TYPE_STATIC_SCOPE, &is_pointer);

  fprintf(fp, "%s,%s,%s,%s,%s,%s,%s,%s,%s\\n", namespace_name, node_type, gtype_name, object_name, query_info.signal_name, ret_type, is_pointer ? "*" : "", flags, buffer);
}

void print_all_types() {''')

        header_writer.write_line("#ifndef _girtypes_h")
        header_writer.write_line("#define _girtypes_h")
        header_writer.write_newline()
        header_writer.write_line("""#include <stdio.h>
#include <glib-2.0/glib-object.h>
#include <gtk/gtk.h>

const char * g_type_fundamental_tostring(GType gtype);
void print_object_properties(FILE *fp, GType object_type, char* namespace_name, char* node_type, char* gtype_name);
void print_object_signals(FILE *fp, GType object_type, char* namespace_name, char* node_type, char* gtype_name);
void output_object_signal(FILE *fp, GType object_type, char* namespace_name, char* node_type, char* gtype_name, const gchar *object_name, guint signal_id);""")

        with open(outputCmakeFilename, 'wb') as c:
            with open(outputMainFilename, 'wb') as m:
                with open(outputHeaderFilename, 'wb') as h:
                    for f in filenames:
                        path, filename = os.path.split(f)
                        if options.typeinfo == True or options.propertyinfo == True or options.signalinfo == True:
                            filename, file_extension = os.path.splitext(filename)
                            filename += '.c'
                        outputFilename = os.path.join(outputPath, filename)
                        cmake_writer.write_line("""set(PROJECT_SOURCES ${PROJECT_SOURCES} ${CMAKE_CURRENT_SOURCE_DIR}/%s)""" % (filename,))
                        with open(outputFilename, 'wb') as o:
                            cmake_code_context = typeinformation_gir(exclude_gtypes, exclude_headers, cmake_code_context, f, o, cmake_writer, header_writer, main_writer, infoformat)
                            o.flush()
                        if options.typeinfo == True:
                            # Write unregistered ctypes
                            filename, file_extension = os.path.splitext(filename)
                            filename += '_ctypes.c'
                            outputFilename = os.path.join(outputPath, filename)
                            cmake_writer.write_line("""set(PROJECT_SOURCES ${PROJECT_SOURCES} ${CMAKE_CURRENT_SOURCE_DIR}/%s)""" % (filename,))
                            with open(outputFilename, 'wb') as o:
                                cmake_code_context = typeinformation_ctypes(exclude_gtypes, exclude_headers, cmake_code_context, f, o, cmake_writer, header_writer, main_writer, infoformat)
                                o.flush()
                    # Write registered types
                    filename = 'registered.c'
                    outputFilename = os.path.join(outputPath, filename)
                    cmake_writer.write_line("""set(PROJECT_SOURCES ${PROJECT_SOURCES} ${CMAKE_CURRENT_SOURCE_DIR}/%s)""" % (filename,))
                    with open(outputFilename, 'wb') as o:
                        cmake_code_context = typeinformation_registered(exclude_gtypes, exclude_headers, cmake_code_context, f, o, cmake_writer, header_writer, main_writer, infoformat)
                        o.flush()
                    cmake_writer.write_line("""string(REPLACE ";" " " CMAKE_C_FLAGS "${CMAKE_C_FLAGS}")""")
                    cmake_writer.write_line("""add_executable (girtypes ${PROJECT_SOURCES})""")
                    cmake_writer.write_line("""target_include_directories (girtypes PUBLIC ${PROJECT_INCLUDE_DIRECTORIES})""")
                    cmake_writer.write_line("""target_link_directories (girtypes PUBLIC ${PROJECT_LINK_DIRECTORIES})""")
                    cmake_writer.write_line("""target_link_libraries (girtypes ${PROJECT_LIBRARIES})""")
                    header_writer.write_newline()
                    header_writer.write_line("""#endif /* _girtypes_h */""")
                    h.write(header_writer.get_encoded_source())
                    h.flush()
                main_writer.write_line("""}

int main(int argc, char *argv[]) {
    gtk_init(&argc, &argv);
    print_all_types();
    exit(0);
}""")
                m.write(main_writer.get_encoded_source())
                m.flush()
            c.write(cmake_writer.get_encoded_source())
            c.flush()
    else:
        for f in filenames:
            path, filename = os.path.split(f)
            outputFilename = os.path.join(outputPath, filename)

            with open(outputFilename, 'wb') as o:
                if options.passthrough == True:
                    passthrough_gir(f, o)
                else:
                    process_gir(f, o, exclude_registered)
                o.flush()
    return 0

if __name__ == "__main__":
    scanner_main(sys.argv)
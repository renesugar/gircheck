# -*- Mode: Python -*-
# GObject-Introspection - a framework for introspecting GObject libraries
# Copyright (C) 2008  Johan Dahlin
# Copyright (C) 2019  Rene Sugar
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2 of the License, or (at your option) any later version.
#
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place - Suite 330,
# Boston, MA 02111-1307, USA.
#

from io import StringIO
from contextlib import contextmanager
from xml.sax.saxutils import escape, quoteattr

COMMENT_C     = "/* "
COMMENT_OCAML = "(* "
COMMENT_CPP   = "// "
COMMENT_HASH  = "# "

class CodeWriter(object):

    def __init__(self, begin_comment="/* "):
        self._data = StringIO()
        self._begin_comment = begin_comment
        self._middle_comment = ""
        self._end_comment = ""
        if begin_comment == COMMENT_C:
            self._middle_comment = " * "
            self._end_comment = " */"
        elif begin_comment == COMMENT_OCAML:
            self._middle_comment = " * "
            self._end_comment = " *)"
        elif begin_comment == COMMENT_HASH:
            self._middle_comment = COMMENT_HASH
            self._end_comment = ""
        elif begin_comment == COMMENT_CPP:
            self._middle_comment = COMMENT_CPP
            self._end_comment = ""
        else:
            self._begin_comment = ""
            self._middle_comment = ""
            self._end_comment = ""
        
        self._scope_stack = []
        self._indent = 0
        self._indent_unit = 2
        self.enable_whitespace()

        self.write_comment("""

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public
License as published by the Free Software Foundation; either
version 2 of the License, or (at your option) any later version.

This library is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public
License along with this library; if not, write to the
Free Software Foundation, Inc., 59 Temple Place - Suite 330,
Boston, MA 02111-1307, USA.


""")

    # Private

    def _open_scope(self, scope_name, attributes=None):
        if attributes is None:
            attributes = []
        #attrs = collect_attributes(scope_name, attributes,
        #                           self._indent, self._indent_char, len(scope_name) + 2)
        self.write_line('{ %s%s%s' % (self._begin_comment, scope_name, self._end_comment ))

    def _close_scope(self, scope_name):
        self.write_line('} %s%s%s' % (self._begin_comment, scope_name, self._end_comment))

    # Public API

    def enable_whitespace(self):
        self._indent_char = ' '
        self._newline_char = '\n'

    def disable_whitespace(self):
        self._indent_char = ''
        self._newline_char = ''

    def get_source(self):
        """Returns a unicode string containing the source code."""
        return self._data.getvalue()

    def get_encoded_source(self):
        """Returns a utf-8 encoded bytes object containing the source code."""
        return self._data.getvalue().encode('utf-8')

    def write_newline(self):
        self._data.write('%s' % (self._newline_char))

    def _write_data(self, data, line='', indent=True, do_escape=False):
        if isinstance(line, bytes):
            line = line.decode('utf-8')
        assert isinstance(line, str)
        if do_escape:
            line = escape(line)
        if indent:
            data.write('%s%s' % (self._indent_char * self._indent,
                                            line))
        else:
            data.write('%s' % (line))

    def write_source(self, line='', indent=True, do_escape=False):
        self._write_data(self._data, line, indent, do_escape)

    def write_line(self, line='', indent=True, do_escape=False):
        self.write_source(line, indent, do_escape)
        self.write_newline()

    def write_comment(self, text):
        lines = text.splitlines()
        if len(lines) == 1:
            self.write_line('%s%s%s' % (self._begin_comment, text, self._end_comment,))
        else:
            self.write_line(self._begin_comment)
            for line in lines:
                self.write_line('%s%s' % (self._middle_comment, line,))
            if self._end_comment != "":
                self.write_source(self._end_comment)
            else:
                self.write_source(self._begin_comment)
            self.write_newline() 

    def push_scope(self, scope_name, attributes=None):
        if attributes is None:
            attributes = []
        self._open_scope(scope_name, attributes)
        self._scope_stack.append(scope_name)
        self._indent += self._indent_unit

    def pop_scope(self):
        self._indent -= self._indent_unit
        scope_name = self._scope_stack.pop()
        self._close_scope(scope_name)
        return scope_name

    @contextmanager
    def scopecontext(self, scope_name, attributes=None):
        self.push_scope(scope_name, attributes)
        try:
            yield
        finally:
            self.pop_scope()

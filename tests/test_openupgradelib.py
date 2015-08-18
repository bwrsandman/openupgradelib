#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
test_openupgradelib
----------------------------------

Tests for `openupgradelib` module.
"""
import sys
import unittest
import mock
import sqlite3
import re

RE_PSQL_FORMAT = re.compile("(^|[^%])%[s]")

# Store original __import__
orig_import = __import__
# This will be the openerp module
openerp_mock = mock.Mock()


def import_mock(name, *args):
    if name == 'openerp' or name.startswith("openerp."):
        return openerp_mock
    return orig_import(name, *args)

if sys.version_info[0] == 3:
    import builtins  # flake8: noqa (F401)
    import_str = 'builtins.__import__'
else:
    import_str = '__builtin__.__import__'

with mock.patch(import_str, side_effect=import_mock):
    from openupgradelib import openupgrade


class PsycopgCrMock():
    def __init__(self):
        connection = sqlite3.connect(":memory:")
        self.sqlite_cr = connection.cursor()
        self.close = self.sqlite_cr.close

    def execute(self, query, *a, **kw):
        return self.sqlite_cr.execute(
            RE_PSQL_FORMAT.sub(r'\1?', query), *a, **kw
        )

    @property
    def rowcount(self):
        return self.sqlite_cr.rowcount


class TestOpenupgradelib(unittest.TestCase):

    def setUp(self):
        self.cr = PsycopgCrMock()
        # Declare mock databases entries
        self.tables = {
        }
        # Declare test data in mock database
        self.data = {
        }
        self._create_mock_database_tables(self.tables)
        self._insert_mock_database_entries(self.data)

    def _create_mock_database_tables(self, table_spec):
        for table, columns in table_spec.items():
            self.cr.execute("CREATE TABLE %(table)s(%(columns)s)" % {
                "table": table,
                "columns": ", ".join(columns),
            })

    def _insert_mock_database_entries(self, data_spec):
        for table, rows in data_spec.items():
            for row in rows:
                columns, entries = zip(*row.items())
                self.cr.sqlite_cr.execute("""\
INSERT INTO %(table)s (%(columns)s)
VALUES (%(entries)s)
""" % {
                    "table": table,
                    "columns": ", ".join(columns),
                    "entries": ", ".join(["?"] * len(entries))
                }, entries)

    def test_something(self):
        pass

    def tearDown(self):
        self.cr.close()

if __name__ == '__main__':
    unittest.main()

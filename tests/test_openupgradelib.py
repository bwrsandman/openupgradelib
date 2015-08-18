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

from collections import namedtuple

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
            "ir_module_module": ["name"],
            "ir_model_data": ["name", "module", "model"],
            "ir_module_module_dependency": ["name"],
            "ir_translation": ["module"],
        }
        # Declare test data in mock database
        self.data = {
            "ir_module_module": [
                {"name": "old_module_name"},
                {"name": "other_module_name"},
            ],
            "ir_model_data": [
                {
                    "module": "base",
                    "name": "module_old_module_name",
                    "model": "ir.module.module",
                },
                {
                    "module": "base",
                    "name": "module_other_module_name",
                    "model": "ir.module.module",
                },
                {
                    "module": "old_module_name",
                    "name": "some_xid1",
                    "model": "a_model",
                },
                {
                    "module": "old_module_name",
                    "name": "some_xid2",
                    "model": "a_model",
                },
                {
                    "module": "other_module_name",
                    "name": "some_xid",
                    "model": "a_model",
                },
            ],
            "ir_module_module_dependency": [
                {"name": "old_module_name"},
                {"name": "other_module_name"},
            ],
            "ir_translation": [
                {"module": "old_module_name"},
                {"module": "other_module_name"},
            ],
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

    def test_update_module_names(self):
        namespec = [("old_module_name", "new_module_name")]
        CompSpec = namedtuple(
            "CompSpec",
            ["table", "module_field", "where", "name_modifier", "size_comp"]
        )

        def assert_entry_counts(compspecs, pre=False):
            """Helper function to do assertions using a named tuple

            Performs SELECT COUNT(*) on tables and a WHERE clause it builds
            It then compares the result to supplied expected results in
            `size_comp`

            The purpose of this function is to reduce the amount of repeated
            asserts and SQL queries

            :param compsecs: list of CompSpecs which list various attributes to
                             help test know which assertions to make:
                             `table`: Name of the table to select on
                             `module_field`: Helps build where clause. This
                                             field is the one compared with the
                                             name of the module before and
                                             after `update_module_names` is
                                             called
                             `where`: Additional where clause. Function will
                                      take care of joining to generated where
                                      clause with an "AND". This argument must
                                      be writen like it was in a WHERE clause.
                                      ex: "field_A='value' AND field_B='val'"
                                      Use None if there is nothing to add.
                             `name_modifier`: lambda for modify the name of the
                                              module. Use None if there is
                                              nothing to perform
                             `size_comp`: list of two elements. They represent
                                          the expected result of the query
                                          after running `update_module_names`
                                          These should be aligned with
                                          `namespec`: [from, to]
            :param pre: bool indicating if this is testing prior of after
                        running `update_module_names`. The function takes care
                        of reversing the expected results
            """
            for cs in compspecs:
                for modulename, numentries in zip(
                    namespec[0],
                    cs.size_comp if not pre else reversed(cs.size_comp)
                ):
                    if cs.where:
                        where = " AND %s" % cs.where
                    else:
                        where = ""
                    if cs.name_modifier:
                        name = cs.name_modifier(modulename)
                    else:
                        name = modulename

                    query = """\
SELECT COUNT(*)
FROM %(table)s
WHERE %(module_field)s=?%(where)s""" % {
                        "table": cs.table,
                        "where": where,
                        "module_field": cs.module_field
                    }
                    res = self.cr.execute(query, (name, )).fetchone()[0]
                    self.assertEqual(
                        res, numentries, """\
Unexpected number of entries in table "%s" associated with module "%s"
Query:
%s
Arg:
%s""" % (cs.table, modulename, query, name))

        # Declaring expected results
        compspecs = [
            CompSpec(
                table="ir_module_module",
                module_field='name',
                where=None,
                name_modifier=None,
                size_comp=[0, 1],
            ),
            CompSpec(
                table="ir_model_data",
                module_field='module',
                where=None,
                name_modifier=None,
                size_comp=[0, 2],
            ),
            CompSpec(
                table="ir_model_data",
                module_field='name',
                where="module='base' AND model='ir.module.module'",
                name_modifier=lambda n: "module_%s" % n,
                size_comp=[0, 1],
            ),
            CompSpec(
                table="ir_translation",
                module_field='module',
                where=None,
                name_modifier=None,
                size_comp=[0, 1],
            ),
        ]

        # Pre test assertion
        assert_entry_counts(compspecs, pre=True)
        # Run function to test
        openupgrade.update_module_names(self.cr, namespec)
        # Post test assertion
        assert_entry_counts(compspecs, pre=False)

    def tearDown(self):
        self.cr.close()

if __name__ == '__main__':
    unittest.main()

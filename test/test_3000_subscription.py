#------------------------------------------------------------------------------
# Copyright (c) 2017, 2020, Oracle and/or its affiliates. All rights reserved.
#------------------------------------------------------------------------------

"""
3000 - Module for testing subscriptions
"""

import base

import cx_Oracle as oracledb
import threading

class SubscriptionData(object):

    def __init__(self, num_messages_expected):
        self.condition = threading.Condition()
        self.num_messages_expected = num_messages_expected
        self.num_messages_received = 0
        self.table_operations = []
        self.row_operations = []
        self.rowids = []

    def CallbackHandler(self, message):
        if message.type != oracledb.EVENT_DEREG:
            table, = message.tables
            self.table_operations.append(table.operation)
            for row in table.rows:
                self.row_operations.append(row.operation)
                self.rowids.append(row.rowid)
            self.num_messages_received += 1
        if message.type == oracledb.EVENT_DEREG or \
                self.num_messages_received == self.num_messages_expected:
            self.condition.acquire()
            self.condition.notify()
            self.condition.release()


class TestCase(base.BaseTestCase):

    def test_3000_subscription(self):
        "3000 - test Subscription for insert, update, delete and truncate"

        # skip if running on the Oracle Cloud, which does not support
        # subscriptions currently
        if self.is_on_oracle_cloud():
            message = "Oracle Cloud does not support subscriptions currently"
            self.skipTest(message)

        # truncate table in order to run test in known state
        self.cursor.execute("truncate table TestTempTable")

        # expected values
        table_operations = [
            oracledb.OPCODE_INSERT,
            oracledb.OPCODE_UPDATE,
            oracledb.OPCODE_INSERT,
            oracledb.OPCODE_DELETE,
            oracledb.OPCODE_ALTER | oracledb.OPCODE_ALLROWS
        ]
        row_operations = [
            oracledb.OPCODE_INSERT,
            oracledb.OPCODE_UPDATE,
            oracledb.OPCODE_INSERT,
            oracledb.OPCODE_DELETE
        ]
        rowids = []

        # set up subscription
        data = SubscriptionData(5)
        connection = base.get_connection(threaded=True, events=True)
        sub = connection.subscribe(callback=data.CallbackHandler,
                                   timeout=10, qos=oracledb.SUBSCR_QOS_ROWIDS)
        sub.registerquery("select * from TestTempTable")
        connection.autocommit = True
        cursor = connection.cursor()

        # insert statement
        cursor.execute("""
                insert into TestTempTable (IntCol, StringCol)
                values (1, 'test')""")
        cursor.execute("select rowid from TestTempTable where IntCol = 1")
        rowids.extend(r for r, in cursor)

        # update statement
        cursor.execute("""
                update TestTempTable set
                    StringCol = 'update'
                where IntCol = 1""")
        cursor.execute("select rowid from TestTempTable where IntCol = 1")
        rowids.extend(r for r, in cursor)

        # second insert statement
        cursor.execute("""
                insert into TestTempTable (IntCol, StringCol)
                values (2, 'test2')""")
        cursor.execute("select rowid from TestTempTable where IntCol = 2")
        rowids.extend(r for r, in cursor)

        # delete statement
        cursor.execute("delete TestTempTable where IntCol = 2")
        rowids.append(rowids[-1])

        # truncate table
        cursor.execute("truncate table TestTempTable")

        # wait for all messages to be sent
        data.condition.acquire()
        data.condition.wait(10)

        # verify the correct messages were sent
        self.assertEqual(data.table_operations, table_operations)
        self.assertEqual(data.row_operations, row_operations)
        self.assertEqual(data.rowids, rowids)

        # test string format of subscription object is as expected
        fmt = "<cx_Oracle.Subscription on <cx_Oracle.Connection to %s@%s>>"
        expected = fmt % (base.get_main_user(), base.get_connect_string())
        self.assertEqual(str(sub), expected)

if __name__ == "__main__":
    base.run_test_cases()
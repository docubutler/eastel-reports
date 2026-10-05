import argparse
import csv
import importlib.util
import re
import sqlite3
import tempfile
import unittest
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch


BASE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("postgres_cdr_details", BASE / "generate_report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def sqlite_query(query):
    # The query's CASE/NULL/LIKE logic is unchanged; only driver syntax differs.
    return re.sub(r"%\((\w+)\)s", r":\1", query).replace("%%", "%")


class CategorySQLTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("ATTACH DATABASE ':memory:' AS public")
        self.db.execute("""CREATE TABLE public.usage_log (
            usage_log_id INTEGER PRIMARY KEY, usage_start_time TEXT,
            rat_type TEXT, roaming_destination_id INTEGER, rating_group TEXT,
            service_type_sub_cd TEXT, opposite_number TEXT, msisdn TEXT,
            imsi TEXT, act_usage_unit NUMERIC)""")
        self.params = {
            "start_date": "2026-09-30 00:00:00",
            "end_date_exclusive": "2026-10-01 00:00:00",
            "msisdn_a": "060100000001",
        }

    def tearDown(self):
        self.db.close()

    def usage(self, record_id, **overrides):
        row = dict(usage_log_id=record_id, usage_start_time="2026-09-30 12:00:00",
                   rat_type="4G", roaming_destination_id=87, rating_group="OFFNET",
                   service_type_sub_cd="MO", opposite_number="60123456789",
                   msisdn="060100000001", imsi="001234567890123", act_usage_unit=123)
        row.update(overrides)
        self.db.execute("INSERT INTO public.usage_log VALUES (?,?,?,?,?,?,?,?,?,?)", tuple(row.values()))

    def usage_rows(self, subscriber=False, positive=False):
        query = report.build_usage_query("public.usage_log", subscriber, positive)
        return list(self.db.execute(sqlite_query(query), self.params))

    def test_usage_categories_and_first_match_precedence(self):
        self.usage(1)
        self.usage(2, rat_type="5G")
        self.usage(3, rat_type="SM", opposite_number="441234567890")
        self.usage(4, rat_type="VO", rating_group="ONNET")
        self.usage(5, rat_type="VO")
        self.usage(6, rat_type="VO", opposite_number="441234567890")
        self.usage(8, roaming_destination_id=88)
        self.usage(9, rat_type="VO", roaming_destination_id=88, service_type_sub_cd="MT")
        self.usage(10, rat_type="VO", roaming_destination_id=88, opposite_number="441234567890")
        self.usage(11, rat_type="SM", roaming_destination_id=88, service_type_sub_cd="MT")
        self.usage(12, rat_type="VO", rating_group="ONNET", opposite_number="600380008000")
        self.usage(13, rat_type="VO", opposite_number="60130012345")
        self.usage(14, rat_type="VO", opposite_number="601300123456")
        self.usage(15, rating_group="500003")
        self.usage(16, rat_type="VO", service_type_sub_cd="MT")
        self.usage(17, rat_type="UNKNOWN")
        rows = self.usage_rows()
        actual = {r["source_record_id"]: r["category_no"] for r in rows}
        self.assertEqual(actual, {1: 1, 2: 2, 3: 3, 4: 4, 5: 5, 6: 6,
                                  8: 8, 9: 9, 10: 10, 11: 11, 12: 12, 13: 12, 14: 5})
        self.assertEqual(len(rows), len(actual))
        self.assertEqual([r["category_no"] for r in rows], sorted(r["category_no"] for r in rows))

    def test_null_semantics_match_mongo(self):
        self.usage(1, rating_group=None)
        self.usage(2, roaming_destination_id=None)
        self.usage(3, rat_type="VO", opposite_number=None)
        self.usage(4, rat_type="VO", roaming_destination_id=None, opposite_number=None)
        self.assertEqual({r["source_record_id"]: r["category_no"] for r in self.usage_rows()},
                         {1: 1, 2: 8, 3: 6, 4: 10})

    def test_inclusive_day_subscriber_and_positive_filters(self):
        self.usage(1, usage_start_time="2026-09-30 00:00:00")
        self.usage(2, usage_start_time="2026-09-30 23:59:59.999999")
        self.usage(3, usage_start_time="2026-09-29 23:59:59.999999")
        self.usage(4, usage_start_time="2026-10-01 00:00:00")
        self.usage(5, msisdn="60100000001")
        self.usage(6, act_usage_unit=0)
        self.usage(7, act_usage_unit=-1)
        self.usage(8, act_usage_unit=None)
        self.assertEqual({r["source_record_id"] for r in self.usage_rows()}, {1, 2, 5, 6, 7, 8})
        self.assertEqual({r["source_record_id"] for r in self.usage_rows(True, True)}, {1, 2})

class RuntimeTests(unittest.TestCase):
    def test_identifier_injection_is_rejected(self):
        self.assertEqual(report.quote_identifier("public.usage_log"), '"public"."usage_log"')
        for name in ["usage_log; DROP TABLE x", "public.x--", "a.b.c", "", "a\"b"]:
            with self.assertRaises(ValueError):
                report.quote_identifier(name)

    def test_smsc_matches_existing_mongo_category_rules_and_scope(self):
        mongo_path = BASE.parent.parent / "report-generation-mongo/3-OneDay-CDR-Details/generate_report.py"
        mongo_spec = importlib.util.spec_from_file_location("original_mongo_cdr", mongo_path)
        original = importlib.util.module_from_spec(mongo_spec)
        mongo_spec.loader.exec_module(original)
        start, end = report.date_window("2026-09-30", "2026-09-30")
        for msisdn in ["", "060100000001"]:
            actual = report.build_smsc_pipeline(start, end, msisdn)
            expected = original.build_smsc_pipeline(
                start.replace(tzinfo=original.timezone.utc),
                end.replace(tzinfo=original.timezone.utc), msisdn or None,
            )
            self.assertEqual(actual[:3], expected[:3])
            self.assertEqual(actual[-1], expected[-1])

    def test_date_validation_and_inclusive_end(self):
        self.assertEqual(report.date_window("2026-09-30", "2026-09-30"),
                         (datetime(2026, 9, 30), datetime(2026, 10, 1)))
        with self.assertRaises(ValueError):
            report.date_window("2026-10-01", "2026-09-30")
        with self.assertRaises(ValueError):
            report.date_window("2026-09-30T00:00:00+08:00", "2026-09-30")

    def test_csv_preserves_decimal_precision_identifiers_and_microseconds(self):
        row = dict(category_no=1, event_time=datetime(2026, 9, 30, 1, 2, 3, 456789),
                   usage_value=Decimal("12345678901234567890.1250000000000000"),
                   msisdn_a="060123456789", msisdn_b=None, imsi="001234567890123",
                   source_record_id=Decimal("99999999999999999999"), postgres_record_id=Decimal("99999999999999999999"))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.csv"
            total, counts = report.write_rows_to_csv(output, [(iter([row]), "public.usage_log")])
            with output.open(newline="", encoding="utf-8") as handle:
                exported = list(csv.DictReader(handle))
            self.assertEqual(total, 1)
            self.assertEqual(counts, {"Domestic Data 4G": 1})
            self.assertEqual(exported[0][report.OUTPUT_HEADERS[4]], "12345678901234567890.1250000000000000")
            self.assertEqual(exported[0]["MSISDN A#"], "060123456789")
            self.assertEqual(exported[0]["IMSI"], "001234567890123")
            self.assertEqual(exported[0]["Postgres Record ID"], "99999999999999999999")
            self.assertEqual(exported[0]["Event/Call Start Date Time"], "2026-09-30T01:02:03.456789")

    def test_failed_cursor_preserves_existing_report(self):
        def failing_cursor():
            yield {"category_no": 1}
            raise RuntimeError("source failed")
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "report.csv"
            output.write_text("previous complete report", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "source failed"):
                report.write_rows_to_csv(output, [(failing_cursor(), "public.usage_log")])
            self.assertEqual(output.read_text(), "previous complete report")
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_connection_enforces_read_only_snapshot_and_closes(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yml"
            config.write_text("variables:\n  start_date: '2026-09-30'\n  end_date: '2026-09-30'\n", encoding="utf-8")
            args = argparse.Namespace(config=str(config), start_date="", end_date="", msisdn_a=None,
                                      usage_table="", smsc_collection="", output="", include_smsc=False, dry_run=False)
            connection = MagicMock()
            connection.__enter__.return_value = connection
            cursor = connection.cursor.return_value.__enter__.return_value
            cursor.__iter__.return_value = iter([])
            with patch.object(report, "parse_args", return_value=args), patch.object(report, "connect_postgres", return_value=connection):
                report.main()
            connection.set_session.assert_called_once_with(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)
            connection.close.assert_called_once()
            executed = [call.args[0] for call in cursor.execute.call_args_list]
            self.assertEqual(len(executed), 2)
            self.assertTrue(executed[0].startswith("SELECT set_config"))
            self.assertIn("SELECT * FROM categorized", executed[1])

    def test_default_export_routes_a2p_to_mongo_and_preserves_source_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.yml"
            config.write_text("variables:\n  start_date: '2026-09-30'\n  end_date: '2026-09-30'\n", encoding="utf-8")
            args = argparse.Namespace(config=str(config), start_date="", end_date="", msisdn_a=None,
                                      usage_table="", smsc_collection="", output="", include_smsc=None, dry_run=False)
            connection = MagicMock()
            connection.__enter__.return_value = connection
            pg_cursor = connection.cursor.return_value.__enter__.return_value
            pg_cursor.__iter__.return_value = iter([{"category_no": 1, "source_record_id": 42, "postgres_record_id": 42}])
            mongo = MagicMock()
            mongo.__enter__.return_value = mongo
            collection = mongo["eastel-data"]["smsc_cdrs"]
            mongo_cursor = MagicMock()
            mongo_cursor.__iter__.return_value = iter([
                {"category_no": 13, "source_database": "MongoDB", "source_record_id": "message-a", "mongo_record_id": "mongo-a"},
                {"category_no": 14, "source_database": "MongoDB", "source_record_id": "message-b", "mongo_record_id": "mongo-b"},
            ])
            collection.aggregate.return_value = mongo_cursor
            with patch.object(report, "parse_args", return_value=args), patch.object(report, "connect_postgres", return_value=connection), patch.object(report, "connect_mongo", return_value=mongo):
                report.main()
            with (Path(directory) / "3-OneDay-CDR-Details-output.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual([r["Category No."] for r in rows], ["1", "13", "14"])
            self.assertEqual([r["Source Database"] for r in rows], ["PostgreSQL", "MongoDB", "MongoDB"])
            self.assertEqual(rows[0]["Postgres Record ID"], "42")
            self.assertEqual(rows[0]["Mongo Record ID"], "")
            self.assertEqual(rows[1]["Postgres Record ID"], "")
            self.assertEqual(rows[1]["Mongo Record ID"], "mongo-a")
            self.assertEqual(rows[1]["Source Table / Collection"], "smsc_cdrs")
            self.assertEqual(rows[1][report.OUTPUT_HEADERS[4]], "")
            collection.aggregate.assert_called_once()
            mongo_cursor.close.assert_called_once()
            connection.set_session.assert_called_once_with(readonly=True, isolation_level="REPEATABLE READ", autocommit=False)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

# Import config-dependent modules after overriding environment/data path.


class ParserTests(unittest.TestCase):
    def test_parse_status_and_ignore_unselected_store(self):
        import apple_monitor

        payload = {
            "head": {"status": "200"},
            "body": {"stores": [
                {
                    "storeNumber": "R706",
                    "partsAvailability": {
                        "MK244AH/A": {"pickupDisplay": "available"},
                        "MK254AH/A": {"pickupDisplay": "unavailable"},
                    },
                },
                {
                    "storeNumber": "R785",
                    "partsAvailability": {
                        "MK244AH/A": {"pickupDisplay": "available"},
                    },
                },
            ]},
        }
        result = apple_monitor.parse_pickup_response(payload)
        self.assertEqual(result[("R706", "MK244AH/A")], True)
        self.assertEqual(result[("R706", "MK254AH/A")], False)
        self.assertNotIn(("R785", "MK244AH/A"), result)

    def test_unknown_is_not_unavailable(self):
        import apple_monitor

        payload = {
            "head": {"status": "200"},
            "body": {"stores": [{
                "storeNumber": "R706",
                "partsAvailability": {
                    "MK244AH/A": {"pickupDisplay": "temporarily unavailable"},
                },
            }]},
        }
        result = apple_monitor.parse_pickup_response(payload)
        self.assertIsNone(result[("R706", "MK244AH/A")])


class DatabaseTests(unittest.TestCase):
    def test_transition_history_and_duration(self):
        import database

        with tempfile.TemporaryDirectory() as tmp:
            temp_db = Path(tmp) / "monitor.sqlite3"
            with patch.object(database, "DATABASE_PATH", temp_db), patch.object(database, "DATA_DIR", Path(tmp)):
                database.init_db()
                start = datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc).isoformat()
                end = (datetime(2026, 11, 23, 8, 12, tzinfo=timezone.utc)).isoformat()
                self.assertIsNone(database.record_observation("R706", "MK244AH/A", False, start))
                event_id = database.record_observation("R706", "MK244AH/A", True, start)
                self.assertIsNotNone(event_id)
                self.assertEqual(len(database.get_pending_notifications()), 1)
                database.mark_notification_sent(event_id)
                self.assertEqual(database.get_pending_notifications(), [])
                database.record_observation("R706", "MK244AH/A", False, end)
                history = database.get_latest_events(10)
                sold_out = next(x for x in history if x["event_type"] == "unavailable")
                self.assertEqual(sold_out["duration_seconds"], 720)


if __name__ == "__main__":
    unittest.main()

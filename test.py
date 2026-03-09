import sys
import unittest
from unittest.mock import MagicMock

# Mock heavy dependencies that are not available in all environments
# before importing scheduler so module-level code doesn't fail
sys.modules.setdefault("pdf2image", MagicMock())
sys.modules.setdefault("PIL", MagicMock())
sys.modules.setdefault("PIL.Image", MagicMock())
sys.modules.setdefault("google", MagicMock())
sys.modules.setdefault("google.genai", MagicMock())
sys.modules.setdefault("tkinter", MagicMock())

from scheduler import is_valid_event, parse_json  # noqa: E402

print(sys.executable)


class TestIsValidEvent(unittest.TestCase):

    def _valid(self):
        return {
            "day": "Monday",
            "start_time": "09:00",
            "end_time": "10:00",
            "title": "Linear Algebra",
            "slot": "L10",
            "venue": "A102",
        }

    def test_valid_event_accepted(self):
        self.assertTrue(is_valid_event(self._valid()))

    def test_valid_event_without_slot_accepted(self):
        event = self._valid()
        del event["slot"]
        self.assertTrue(is_valid_event(event))

    def test_missing_required_field_rejected(self):
        for field in ["day", "start_time", "end_time", "title", "venue"]:
            event = self._valid()
            del event[field]
            self.assertFalse(is_valid_event(event), f"Expected False when '{field}' is missing")

    def test_null_required_field_rejected(self):
        for field in ["day", "start_time", "end_time", "title", "venue"]:
            event = self._valid()
            event[field] = None
            self.assertFalse(is_valid_event(event), f"Expected False when '{field}' is None")

    def test_empty_string_required_field_rejected(self):
        for field in ["day", "start_time", "end_time", "title", "venue"]:
            event = self._valid()
            event[field] = ""
            self.assertFalse(is_valid_event(event), f"Expected False when '{field}' is empty string")

    def test_whitespace_only_required_field_rejected(self):
        for field in ["day", "start_time", "end_time", "title", "venue"]:
            event = self._valid()
            event[field] = "   "
            self.assertFalse(is_valid_event(event), f"Expected False when '{field}' is whitespace")

    def test_null_slot_does_not_reject_event(self):
        event = self._valid()
        event["slot"] = None
        self.assertTrue(is_valid_event(event))

    def test_empty_event_rejected(self):
        self.assertFalse(is_valid_event({}))

    def test_non_string_required_field_rejected(self):
        for field in ["day", "start_time", "end_time", "title", "venue"]:
            event = self._valid()
            event[field] = 0
            self.assertFalse(is_valid_event(event), f"Expected False when '{field}' is a non-string type")


class TestParseJson(unittest.TestCase):

    def test_parses_valid_json_array(self):
        text = '[{"day": "Monday", "start_time": "09:00", "end_time": "10:00", "title": "Math", "venue": "A1"}]'
        result = parse_json(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["day"], "Monday")

    def test_returns_empty_list_when_no_json(self):
        self.assertEqual(parse_json("No JSON here"), [])

    def test_extracts_json_embedded_in_text(self):
        text = 'Some text before [{"day": "Tuesday", "start_time": "10:00", "end_time": "11:00", "title": "Physics", "venue": "B2"}] and after'
        result = parse_json(text)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["day"], "Tuesday")


if __name__ == "__main__":
    unittest.main()

import unittest

from request_utils import parse_json_payload


class ParseJsonPayloadTests(unittest.TestCase):
    def test_returns_dict_for_valid_json(self):
        data = parse_json_payload('{"signal":"BUY","symbol":"ETHUSD","entry":2363.66}')
        self.assertEqual(data["signal"], "BUY")
        self.assertEqual(data["symbol"], "ETHUSD")

    def test_raises_value_error_for_invalid_json(self):
        with self.assertRaises(ValueError):
            parse_json_payload('not-json')

    def test_raises_value_error_for_non_object_json(self):
        with self.assertRaises(ValueError):
            parse_json_payload('[1,2,3]')


if __name__ == "__main__":
    unittest.main()

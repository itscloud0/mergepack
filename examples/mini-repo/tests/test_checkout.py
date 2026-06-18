import unittest

from src.checkout import checkout


class CheckoutTests(unittest.TestCase):
    def test_save10_coupon(self):
        self.assertEqual(checkout([{"price": 100}], "SAVE10")["total"], 90)


if __name__ == "__main__":
    unittest.main()

import tempfile
import unittest
from pathlib import Path
from csv_guard import inspect, report


class GuardTests(unittest.TestCase):
    def check_csv(self, text):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'input.csv'
            path.write_text(text, encoding='utf-8')
            return inspect(path)

    def test_demo(self):
        result = inspect(Path(__file__).parent / 'examples/orders.csv')
        self.assertEqual(result['rows'], 8)
        self.assertEqual([(i['line'], i['field']) for i in result['issues']],
                         [(4, 'total'), (5, 'order_id'), (6, 'date'), (7, 'quantity'), (8, 'unit_price')])

    def test_decimal_arithmetic(self):
        self.assertEqual(self.check_csv('order_id,date,quantity,unit_price,total\na,2026-10-01,3,0.10,0.30\n')['issues'], [])

    def test_duplicate_and_missing_headers(self):
        self.assertEqual(len(self.check_csv('order_id,order_id\na,b\n')['issues']), 2)

    def test_width_and_nonfinite(self):
        result = self.check_csv('order_id,date,quantity,unit_price,total\na,2026-10-01,1,Infinity,0\nb,2026-10-01,1\n')
        self.assertEqual([i['field'] for i in result['issues']], ['unit_price', 'schema'])

    def test_html_is_escaped(self):
        html = report({'rows': 0, 'issues': [{'line': 1, 'field': '<script>', 'message': '<img onerror=x>'}]})
        self.assertNotIn('<script>', html)
        self.assertNotIn('<img onerror', html)


if __name__ == '__main__':
    unittest.main()

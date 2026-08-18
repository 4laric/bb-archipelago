def example(self, rows):
    self.assertEqual([], rows)
    self.assertTrue(all(row.valid for row in rows))
    self.assertFalse(any(row.invalid for row in rows))

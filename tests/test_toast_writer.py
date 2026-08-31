from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent.parent
SOURCE = (ROOT / "tools/bb_toast_writer/Program.cs").read_text(encoding="utf-8")


class ToastWriterContractTests(unittest.TestCase):
    def test_writer_is_double_gated_and_refuses_inert_plans(self):
        self.assertIn('args[6] != "--probe-confirmed"', SOURCE)
        self.assertIn('args[7] != "--apply"', SOURCE)
        self.assertIn('if (!plan.Enabled)', SOURCE)

    def test_writer_asserts_popup_shape_and_claimed_ranges(self):
        self.assertIn('"yesNoDialogMessageId"', SOURCE)
        self.assertIn('"isOnlyOne"', SOURCE)
        self.assertIn("900000", SOURCE)
        self.assertIn("900999", SOURCE)

    def test_writer_round_trips_both_outputs_before_success(self):
        self.assertIn("Verify(plan, outputGameparam", SOURCE)
        self.assertIn("BND4.Read(msgbndPath)", SOURCE)
        self.assertIn("FMG omitted or changed", SOURCE)

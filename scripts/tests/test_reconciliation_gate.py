import unittest

from scripts.reconciliation_gate import evaluate


class ReconciliationGateTest(unittest.TestCase):
    def test_accepts_idempotent_zero_difference_report(self):
        report={"mode":"dry-run","patients":{"source":2,"inserted":0,"existing":2,"rejected":0},"patient_demographic_reconciliation":{"missing_patient_pids":[],"typed_fields":{"fname":{"records":2,"matches":2,"mismatch_pids":[]}},"legacy_payload_fields":{}}}
        self.assertEqual(evaluate(report)["status"],"passed")

    def test_rejects_pending_rows_rejections_and_demographic_drift(self):
        report={"mode":"dry-run","patients":{"source":3,"inserted":1,"existing":1,"rejected":1},"patient_demographic_reconciliation":{"missing_patient_pids":[3],"typed_fields":{"fname":{"records":2,"matches":1,"mismatch_pids":[2]}},"legacy_payload_fields":{}}}
        result=evaluate(report)
        self.assertEqual(result["status"],"failed");self.assertGreaterEqual(len(result["failures"]),4)

    def test_requires_explicit_exact_rejection_allowance(self):
        report={"mode":"dry-run","documents":{"source":1,"inserted":0,"existing":0,"rejected":1},"patient_demographic_reconciliation":{"missing_patient_pids":[],"typed_fields":{},"legacy_payload_fields":{}}}
        self.assertEqual(evaluate(report,{"documents":1})["status"],"passed")
        self.assertEqual(evaluate(report,{"documents":2})["status"],"failed")


if __name__=="__main__":unittest.main()

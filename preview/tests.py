from django.test import TestCase
from preview.services import analyze_csv, ImportFormatError


class HRISImportServiceTests(TestCase):

    def test_duplicate_identities(self):
        """Verify that ALL rows sharing a duplicate employee_id or email are marked invalid."""
        csv_data = (
            "employee_id,employee_name,email,manager_id,manager_email,department\n"
            "E1,John,john@example.com,,,\n"
            "E1,Jane,jane@example.com,,,\n"
            "E2,Bob,john@example.com,,,\n"
            "E3,Alice,alice@example.com,,,\n"
        ).encode("utf-8")

        result = analyze_csv(csv_data)

        self.assertEqual(result.source_row_count, 4)

        self.assertEqual(len(result.accepted_employees), 1)
        self.assertEqual(result.accepted_employees[0].employee_id, "E3")

        error_rows = [err.source_row for err in result.errors]
        self.assertIn(2, error_rows)
        self.assertIn(3, error_rows)
        self.assertIn(4, error_rows)

    def test_manager_resolution_cases(self):
        """Test manager resolution: ID-only, email-only, agreeing, conflicting, missing manager, self-management."""
        csv_data = (
            "employee_id,employee_name,email,manager_id,manager_email,department\n"
            "E1,CEO,ceo@example.com,,,\n"
            "E2,Manager 1,mgr1@example.com,E1,,\n"
            "E3,Manager 2,mgr2@example.com,,ceo@example.com,\n"
            "E4,Employee 4,emp4@example.com,E1,ceo@example.com,\n"
            "E5,Employee 5,emp5@example.com,E1,mgr1@example.com,\n"
            "E6,Employee 6,emp6@example.com,E999,,\n"
            "E7,Employee 7,emp7@example.com,,missing@example.com,\n"
            "E8,Self Manager,self@example.com,E8,self@example.com,\n"
        ).encode("utf-8")

        result = analyze_csv(csv_data)

        self.assertEqual(len(result.accepted_employees), 8)

        self.assertEqual(len(result.roots), 1)
        self.assertEqual(result.roots[0].employee_id, "E1")

        direct_reports = {
            item.manager.employee_id: item.direct_reports_count
            for item in result.manager_direct_report_counts
        }
        self.assertEqual(direct_reports.get("E1"), 3)

        error_rows = {err.source_row: err.message for err in result.errors}
        self.assertTrue(any("refer to different employees" in msg for msg in error_rows.values()))
        self.assertTrue(any("could not be found" in msg for msg in error_rows.values()))
        self.assertTrue(any("cannot manage themselves" in msg for msg in error_rows.values()))

    def test_roots_and_direct_reports(self):
        """Test simple root detection and direct report count aggregation."""
        csv_data = (
            "employee_id,employee_name,email,manager_id,manager_email,department\n"
            "E1,Alice,alice@example.com,,,\n"
            "E2,Bob,bob@example.com,E1,,\n"
            "E3,Carol,carol@example.com,E1,,\n"
        ).encode("utf-8")

        result = analyze_csv(csv_data)

        self.assertEqual(len(result.roots), 1)
        self.assertEqual(result.roots[0].employee_id, "E1")
        self.assertEqual(len(result.manager_direct_report_counts), 1)
        self.assertEqual(result.manager_direct_report_counts[0].manager.employee_id, "E1")
        self.assertEqual(result.manager_direct_report_counts[0].direct_reports_count, 2)

    def test_cycle_detection_with_downstream_employee(self):
        """Test cycle detection graph: E1 -> E2 -> E3 -> E1, and E4 -> E1."""
        csv_data = (
            "employee_id,employee_name,email,manager_id,manager_email,department\n"
            "E1,Emp 1,e1@example.com,E2,,\n"
            "E2,Emp 2,e2@example.com,E3,,\n"
            "E3,Emp 3,e3@example.com,E1,,\n"
            "E4,Emp 4,e4@example.com,E1,,\n"
        ).encode("utf-8")

        result = analyze_csv(csv_data)

        cyclic_ids = {emp.employee_id for emp in result.cyclic_employees}
        self.assertEqual(cyclic_ids, {"E1", "E2", "E3"})
        self.assertNotIn("E4", cyclic_ids)

    def test_utf8_bom_headers_and_whitespace_normalization(self):
        """Test UTF-8 BOM encoding, whitespace normalization, and email lowercasing."""
        bom_csv = (
            "\ufeff employee_id , employee_name , email , manager_id , manager_email , department \n"
            " E001 , Alice Smith , ALICE@EXAMPLE.COM , , , Engineering \n"
            " e001 , Bob Jones , BOB@EXAMPLE.COM , E001 , alice@example.com , Engineering \n"
        ).encode("utf-8-sig")

        result = analyze_csv(bom_csv)

        self.assertEqual(len(result.accepted_employees), 2)

        e1 = next(emp for emp in result.accepted_employees if emp.employee_id == "E001")
        self.assertEqual(e1.email, "alice@example.com")
        self.assertEqual(e1.employee_name, "Alice Smith")

        e2 = next(emp for emp in result.accepted_employees if emp.employee_id == "e001")
        self.assertEqual(e2.email, "bob@example.com")
        self.assertEqual(e2.manager_id, "E001")

    def test_malformed_uploads(self):
        """Test empty file and missing header exceptions."""
        with self.assertRaises(ImportFormatError) as ctx1:
            analyze_csv(b"")
        self.assertIn("empty", str(ctx1.exception).lower())

        with self.assertRaises(ImportFormatError) as ctx2:
            analyze_csv(b"employee_id,email\nE1,e1@example.com")
        self.assertIn("Missing required CSV headers", str(ctx2.exception))

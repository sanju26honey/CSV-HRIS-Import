from dataclasses import dataclass, field
import io
import csv
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Any


class ImportFormatError(Exception):
    """Raised when the CSV file itself is malformed or invalid."""
    pass


@dataclass
class Employee:
    employee_id: str
    employee_name: str
    email: str
    manager_id: str
    manager_email: str
    department: str
    source_row: int


@dataclass
class ValidationError:
    source_row: int
    message: str


@dataclass
class ManagerReportSummary:
    manager: Employee
    direct_reports_count: int


@dataclass
class ImportResult:
    source_row_count: int
    accepted_employees: List[Employee] = field(default_factory=list)
    errors: List[ValidationError] = field(default_factory=list)
    roots: List[Employee] = field(default_factory=list)
    manager_direct_report_counts: List[ManagerReportSummary] = field(default_factory=list)
    cyclic_employees: List[Employee] = field(default_factory=list)


REQUIRED_HEADERS = {
    "employee_id",
    "employee_name",
    "email",
    "manager_id",
    "manager_email",
    "department",
}


def analyze_csv(file_input: Any) -> ImportResult:
    """
    Parses and analyzes an uploaded CSV file containing employee HRIS data.
    Performs decoding, normalization, identity validation, manager resolution,
    direct report counting, and stack-safe iterative cycle detection.
    """
    if file_input is None:
        raise ImportFormatError("Please select a CSV file.")

    # File decoding and content extraction
    try:
        if isinstance(file_input, (bytes, bytearray)):
            raw_bytes = file_input
        elif hasattr(file_input, "read"):
            raw_bytes = file_input.read()
        else:
            raw_bytes = str(file_input).encode("utf-8")
    except Exception as e:
        raise ImportFormatError(f"Failed to read upload file: {e}")

    if not raw_bytes or not raw_bytes.strip():
        raise ImportFormatError("The uploaded CSV is empty.")

    try:
        text_content = raw_bytes.decode("utf-8-sig").lstrip("\ufeff")
    except UnicodeDecodeError:
        raise ImportFormatError("The uploaded file must be UTF-8 encoded.")

    if not text_content.strip():
        raise ImportFormatError("The uploaded CSV is empty.")

    # Header validation
    csv_file = io.StringIO(text_content, newline="")
    try:
        reader = csv.DictReader(csv_file)
    except Exception as e:
        raise ImportFormatError(f"Invalid CSV format: {e}")

    if not reader.fieldnames:
        raise ImportFormatError("The uploaded CSV has no headers.")

    # Clean header whitespace
    raw_headers = reader.fieldnames or []
    cleaned_headers = [h.strip() if h else "" for h in raw_headers]
    actual_headers = set(cleaned_headers)

    missing = REQUIRED_HEADERS - actual_headers
    if missing:
        missing_sorted = sorted(list(missing))
        raise ImportFormatError(f"Missing required CSV headers: {', '.join(missing_sorted)}")

    # Read & Normalize rows
    raw_records = []
    source_row = 2 
    for row in reader:
        # Normalize
        clean_row = { (k.strip() if k else ""): (v or "") for k, v in row.items() }
        emp_id = clean_row.get("employee_id", "").strip()
        emp_name = clean_row.get("employee_name", "").strip()
        email = clean_row.get("email", "").strip().lower()
        mgr_id = clean_row.get("manager_id", "").strip()
        mgr_email = clean_row.get("manager_email", "").strip().lower()
        dept = clean_row.get("department", "").strip()

        raw_records.append(
            Employee(
                employee_id=emp_id,
                employee_name=emp_name,
                email=email,
                manager_id=mgr_id,
                manager_email=mgr_email,
                department=dept,
                source_row=source_row,
            )
        )
        source_row += 1

    source_row_count = len(raw_records)

    # validation (Two-pass)
    employee_id_counts = Counter(
        rec.employee_id for rec in raw_records if rec.employee_id
    )
    email_counts = Counter(
        rec.email for rec in raw_records if rec.email
    )

    accepted_employees: List[Employee] = []
    errors: List[ValidationError] = []

    for rec in raw_records:
        row_errors = []
        if not rec.employee_id:
            row_errors.append("Missing mandatory field: employee_id.")
        elif employee_id_counts[rec.employee_id] > 1:
            row_errors.append(f"Duplicate employee_id '{rec.employee_id}'.")

        if not rec.email:
            row_errors.append("Missing mandatory field: email.")
        elif email_counts[rec.email] > 1:
            row_errors.append(f"Duplicate email '{rec.email}'.")

        if row_errors:
            for err_msg in row_errors:
                errors.append(ValidationError(source_row=rec.source_row, message=err_msg))
        else:
            accepted_employees.append(rec)

    # indexes for O(1) lookups
    employees_by_id: Dict[str, Employee] = {
        emp.employee_id: emp for emp in accepted_employees
    }
    employees_by_email: Dict[str, Employee] = {
        emp.email: emp for emp in accepted_employees
    }

    # Manager resolution & hierarchy building
    roots: List[Employee] = []
    manager_by_employee_id: Dict[str, str] = {}
    direct_report_counts: Dict[str, int] = defaultdict(int)

    for emp in accepted_employees:
        mgr_id = emp.manager_id
        mgr_email = emp.manager_email

        if not mgr_id and not mgr_email:
            roots.append(emp)
            continue

        resolved_manager: Optional[Employee] = None

        if mgr_id and not mgr_email:
            resolved_manager = employees_by_id.get(mgr_id)
            if not resolved_manager:
                errors.append(
                    ValidationError(
                        source_row=emp.source_row,
                        message=f"Manager with employee_id '{mgr_id}' could not be found.",
                    )
                )

        elif not mgr_id and mgr_email:
            resolved_manager = employees_by_email.get(mgr_email)
            if not resolved_manager:
                errors.append(
                    ValidationError(
                        source_row=emp.source_row,
                        message=f"Manager with email '{mgr_email}' could not be found.",
                    )
                )

        else:
            mgr_by_id = employees_by_id.get(mgr_id)
            mgr_by_email = employees_by_email.get(mgr_email)

            if not mgr_by_id or not mgr_by_email:
                errors.append(
                    ValidationError(
                        source_row=emp.source_row,
                        message="Manager references could not be resolved.",
                    )
                )
            elif mgr_by_id.employee_id != mgr_by_email.employee_id:
                errors.append(
                    ValidationError(
                        source_row=emp.source_row,
                        message=f"manager_id '{mgr_id}' and manager_email '{mgr_email}' refer to different employees.",
                    )
                )
            else:
                resolved_manager = mgr_by_id
        
        if resolved_manager:
            if resolved_manager.employee_id == emp.employee_id:
                errors.append(
                    ValidationError(
                        source_row=emp.source_row,
                        message="Employee cannot manage themselves.",
                    )
                )
            else:
                manager_by_employee_id[emp.employee_id] = resolved_manager.employee_id
                direct_report_counts[resolved_manager.employee_id] += 1
    
    manager_summaries: List[ManagerReportSummary] = []
    for emp in accepted_employees:
        if emp.employee_id in direct_report_counts:
            manager_summaries.append(
                ManagerReportSummary(
                    manager=emp,
                    direct_reports_count=direct_report_counts[emp.employee_id],
                )
            )

    # cycle detection
    state: Dict[str, int] = {}
    cyclic_ids = set()

    for emp in accepted_employees:
        start_id = emp.employee_id
        if state.get(start_id) == 2:
            continue

        current: Optional[str] = start_id
        path: List[str] = []
        path_index: Dict[str, int] = {}

        while current is not None and state.get(current, 0) != 2:
            if current in path_index:
                cycle_start = path_index[current]
                cyclic_ids.update(path[cycle_start:])
                break

            path_index[current] = len(path)
            path.append(current)

            current = manager_by_employee_id.get(current)

        for node_id in path:
            state[node_id] = 2

    cyclic_employees: List[Employee] = [
        emp for emp in accepted_employees if emp.employee_id in cyclic_ids
    ]

    # Sort
    errors.sort(key=lambda x: x.source_row)
    accepted_employees.sort(key=lambda x: x.source_row)
    roots.sort(key=lambda x: x.source_row)
    manager_summaries.sort(key=lambda x: x.manager.source_row)
    cyclic_employees.sort(key=lambda x: x.source_row)

    return ImportResult(
        source_row_count=source_row_count,
        accepted_employees=accepted_employees,
        errors=errors,
        roots=roots,
        manager_direct_report_counts=manager_summaries,
        cyclic_employees=cyclic_employees,
    )

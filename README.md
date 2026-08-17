# Diversio HRIS Import Preview

An in-memory Django web application for uploading, parsing, validating, and analyzing HRIS employee CSV data without database persistence.

## Overview

The **Diversio HRIS Import Preview** application allows users to upload a CSV file containing employee records, validate identity uniqueness and manager relationships, count direct reports, detect reporting cycles, and preview the resulting organizational hierarchy.

## Requirements

* Python 3.10+
* Django 4.2+ (tested with Django 6.1)

## Setup

1. Clone or extract the project repository.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

## Running the Application

Start the Django development server:

```bash
python manage.py runserver
```

Open your browser and navigate to `http://127.0.0.1:8000/`.

## Running Automated Tests

To execute the test suite (6 focused tests covering duplicate identities, manager resolution, root detection, cycle detection, UTF-8 BOM, and malformed uploads):

```bash
python manage.py test
```

---

## Architectural Decisions & Choice Evaluation

Per project requirements, three major architectural decisions were evaluated against alternatives prior to implementation:

### 1. Cycle Detection Algorithm
- **Option A (Recursive DFS)**: Standard recursive depth-first search. Rejected due to Python's call-stack limit (`sys.getrecursionlimit()` ~1000) which would trigger a `RecursionError` on large 100,000-node reporting chains.
- **Option B (Iterative Path-Tracking DFS)** *(CHOSEN)*: Explicit loop utilizing a `path` list and `path_index` hash map to detect cycles. Ensures $O(N)$ time and $O(N)$ space while remaining 100% stack-safe for 100,000 employees.
- **Option C (Degree-Reduction Graph Truncation)**: Iteratively remove zero in-degree nodes. Over-engineered for functional graphs (out-degree $\le 1$) and requires additional complexity to reconstruct exact cycle paths.

### 2. Project Directory Structure
- **Option A (Workspace-Root Django Layout)** *(CHOSEN)*: Place `manage.py`, `config/`, `preview/`, `requirements.txt`, and `README.md` in the workspace root. Enables direct command execution (`python manage.py runserver`) without nested directory navigation.
- **Option B (Nested Subfolder Layout)**: Place project inside `diversio-hris-preview/`. Added unnecessary path depth.
- **Option C (REST API + React SPA)**: Explicitly forbidden by non-negotiable constraints.

### 3. Identity Validation & Duplicate Exclusion
- **Option A (Two-Pass Counter Validation)** *(CHOSEN)*: Pass 1 calculates occurrence counts for `employee_id` and `email`. Pass 2 invalidates **all** members of duplicate groups and excludes them completely from manager lookup indexes.
- **Option B (First-Occurrence Retention)**: Retain the first duplicate row while rejecting subsequent occurrences. Violates specs requiring all duplicate rows to be invalid and excluded from hierarchy lookups.
- **Option C (Database Unique Constraints)**: Violates the constraint against database persistence.

---

## Architecture & Data Flow

```text
Uploaded File
      │
      ▼
UTF-8 / UTF-8-BOM Decoding & U+FEFF Stripping
      │
      ▼
CSV DictReader (Header Validation & Column Normalization)
      │
      ▼
Value Normalization (Strip Whitespace, Lowercase Emails, Case-Sensitive IDs)
      │
      ▼
Two-Pass Identity Validation (Missing / Duplicate ID & Email)
      │
      ├───────────────────────┬────────────────────────┐
      ▼                       ▼                        ▼
Invalid Rows           Accepted Employees     Lookup Indexes (O(1))
(Validation Errors)           │
                              ▼
                     Manager Resolution
         (Blank=Root, ID, Email, Both Agreeing/Conflicting, Self-Mgmt)
                              │
                              ▼
                     Hierarchy Analysis
            (Direct Report Counts & Cycle Detection)
                              │
                              ▼
                     In-Memory ImportResult
                              │
                              ▼
                     Rendered HTML View
```

## Complexity Analysis

- **Parsing & Normalization**: $O(N)$ time — each CSV row is read and trimmed once.
- **Identity Validation**: $O(N)$ time — two linear passes over the parsed records using hash maps.
- **Manager Lookups**: $O(N)$ average time — $O(1)$ average dictionary lookups per employee.
- **Direct Report Counting**: $O(N)$ time — constant-time increments per valid relationship.
- **Cycle Detection**: $O(N)$ time & $O(N)$ space — each employee and relationship link is visited at most twice during iterative path tracking.

Overall Time Complexity: **$O(N)$**  
Overall Space Complexity: **$O(N)$** (where $N$ is the number of rows in the CSV file).

---

## Edge Case Handling

1. **UTF-8 with BOM**: Uses `utf-8-sig` decoding and `.lstrip('\ufeff')` to handle single and double BOM markers.
2. **Whitespace Normalization**: Trims all header keys and data values.
3. **Case Sensitivity**: Lowercases all email addresses (`email`, `manager_email`) while preserving case-sensitivity for `employee_id` and `manager_id`.
4. **Header Reordering**: Dynamically matches required fields regardless of CSV column order.
5. **Duplicate Identities**: Invalidates all occurrences of duplicate IDs or emails, removing them from hierarchy lookup targets to prevent ambiguous relationships.
6. **Conflicting Manager References**: Reports validation errors if `manager_id` and `manager_email` resolve to different employees.
7. **Malformed Uploads**: Catches empty CSVs, missing header columns, non-UTF-8 encodings, and malformed files gracefully without throwing 500 server errors.

---

## AI Usage

- **AI Tools Used**: Antigravity Assistant (powered by Google Gemini 3.6 Flash High).
- **Usage**: Architecture design, iterative cycle detection algorithm selection, edge-case analysis, and test suite generation.
- **Key Modification**: The initial naive recommendation suggested recursive DFS for cycle detection. This was changed to an **iterative path-tracking traversal with a path index hash map** to ensure stack safety when processing datasets approaching 100,000 employees.

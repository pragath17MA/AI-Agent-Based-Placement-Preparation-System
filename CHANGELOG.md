# Changelog: AI Interview Platform Upgrade

This file documents all structural modifications, feature expansions, and hotfixes applied during the production-ready upgrade.

---

## [1.2.0] - 2026-07-05

### Added
- **Dynamic Seeding Engine**: Upgraded `backend/seed.py` to seed 510 unique technical and behavioral problems, with example cases, constraints, tags, hints, optimal complexities, editorials, and starter code configurations for Python, Java, C, C++, and JavaScript.
- **Self-Healing Column Migrations**: Embedded automated text-wrapped `ALTER TABLE` checks into `backend/app/main.py` and `backend/seed.py` to automatically register 9 new columns for the `problems` table on SQLite/PostgreSQL startup.
- **SSE Streaming Support**: Added a `/api/v1/chat/message/stream` endpoint returning a real-time chunked typing feed for assistant responses.

### Changed
- **Subprocess Memory Constraints (Windows Fix)**: Refactored `CodeExecutor._run_command_with_limits` to recursively inspect child processes and aggregate RSS memory usage. This corrects constraint limits detection under virtual environment python launchers.
- **Frontend Stream Consumption**: Upgraded `handleSendMessage` in `frontend/app/chat/page.tsx` to read chunked data feeds progressively using a web stream reader.
- **Memory Unit Tests**: Adjusted `test_python_executor_memory_limit` to mutate allocated array pages in a loop and sleep briefly to guarantee reliable `MEMORY_LIMIT_EXCEEDED` detections.

### Fixed
- **SQLAlchemy 2.0 Textual Expressions**: Fixed `ArgumentError` by wrapping all raw database query strings with `text()` inside migrations and database seeding scripts.

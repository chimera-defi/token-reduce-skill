# Architecture

- Parent/orchestrator prepares a strict task envelope.
- Cheap worker (Kimi) executes bounded task.
- Output validator enforces required sections/format.
- Fallback path handles timeout/schema/provider failures.
- Telemetry captures savings, quality, and fallback behavior.

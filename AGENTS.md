# Project rules

- The project is a production-quality responsive workout-tracking application.
- The frontend will use React and TypeScript.
- The backend will use Python and FastAPI.
- PostgreSQL will be the database.
- All database changes must use migrations.
- Never commit passwords, tokens, connection strings, or other secrets.
- Add tests for every implemented feature.
- Add concise comments for business rules and non-obvious technical decisions.
- Do not copy source code, visual design, icons, wording, or assets from existing fitness applications.
- Only one write-capable agent may modify files at a time.
- Do not claim that tests passed unless they were actually executed.
- Please make sure you add necessary code commenting in each files, if necessary please explain the code as well. 

# Agent coordination

The main session coordinates assignments and exclusive writer ownership. This
single-writer rule includes the main session, developer, and test engineer, even
when they would edit different files. Serialize edits and commands that generate
or modify files; complete the current writer's handoff before another starts.
Read-only planning and review may run concurrently.

- `product_planner`: Return requirements, architecture plans, user stories, risks,
  and acceptance criteria without modifying files. Proposals require user approval
  before implementation.
- `developer`: Implement approved requirements inside the repository, add tests
  and useful comments, and run formatting, type checking, and relevant tests.
  Never weaken tests to make them pass.
- `test_engineer`: Modify only test files and test-only fixtures or helpers.
  Never modify production code. Cover normal behavior, error handling, boundary
  cases, database behavior, responsive design, and accessibility. Report exact
  commands and results; hand production defects to the developer.
- `reviewer`: Review without modifying files. Report correctness, security, data
  integrity, performance, accessibility, maintainability, and missing-test findings
  with severity, evidence, affected files, and recommended corrections.

Agent files intentionally omit model settings to inherit the main session's
selected model. Report unavailable checks and blockers honestly; proposed checks
are not executed tests.

# Agently Stage Runtime Examples Coverage Design

Status: approved direction, awaiting written-spec review

Date: 2026-07-11

## 1. Purpose

The runtime implementation and tests cover substantially more behavior than
the current public examples. The examples directory currently contains one
combined smoke scenario and a notebook that repeats it. This change adds a
small, independently runnable example suite for the common runtime decisions a
user must make.

These are low-level runtime capability examples. They do not need a model call
because they demonstrate executor, event-loop, settlement, stream, channel,
listener, and process-exit behavior rather than a model-owned application
decision.

## 2. Organization Decision

Use one self-contained Python script per capability group.

Alternatives considered:

- one large cookbook script was rejected because scenarios would share state,
  users could not copy one pattern cleanly, and failures would be harder to
  locate;
- README-only snippets were rejected because they are not independently
  executable or continuously verified;
- independent scripts are selected because each script can state its contract,
  stable output, and failure boundary without introducing a new framework
  abstraction or shared example helper.

The notebook remains a compact quickstart. It does not duplicate every example.
README provides the scenario index and links to the scripts.

## 3. Example Matrix

Create or revise these examples:

1. `basic_sync_async.py`
   - synchronous callable execution;
   - asynchronous callable execution;
   - concurrent async roots on the shared Stage loop;
   - `async_get()` and `async_close()` from `asyncio.run()`.
2. `body_result_and_background_drain.py`
   - body result becomes available before a retained descendant finishes;
   - `wait_settled()` waits for the descendant;
   - the descendant represents provider transport/meta drain, not business
     abort policy.
3. `generation_and_pinned_context.py`
   - a plain Stage crosses finite generations after becoming idle;
   - `with Stage()` preserves loop affinity while its lease is open.
4. `callbacks_errors_and_cancellation.py`
   - ordered success/error/finally observers;
   - body errors remain body errors;
   - callback errors become settlement errors;
   - cancellation remains a runtime cancellation, not a business abort.
5. `tunnel_broadcast.py`
   - external writes and close;
   - independent sync and async replay readers;
   - terminal failure after accepted values;
   - one reader does not consume another reader's cursor.
6. `stage_stream.py`
   - async generator execution;
   - read-only sync and async replay;
   - lazy source start;
   - source failure delivery and settlement observation.
7. `event_emitter.py`
   - sync and async listeners;
   - `once` atomic behavior;
   - `wait=False` returns handles;
   - listener failure isolation;
   - emitter close drains pending work.
8. `automatic_process_exit.py`
   - no explicit Stage close or application shutdown hook;
   - the body returns first;
   - retained background work finishes before interpreter exit;
   - the example must not use daemon threads or `atexit`.

The existing `runtime_foundation.py` remains the short combined overview.
Compatibility names such as `StageDispatch` are documented but do not receive
recommended examples because new code should use the canonical APIs.

## 4. Output And Error Rules

Every script must:

- run directly on Python 3.10+ from the repository root;
- include an `Expected key output from a real local run` comment;
- print stable semantic facts rather than elapsed-time thresholds or thread
  identities;
- use assertions for owned structural invariants;
- catch only the expected typed error when the scenario intentionally fails;
- close explicit application scopes except in the automatic-process-exit
  example;
- avoid sleeps as correctness grace periods; sleeps may only represent
  asynchronous work after synchronization has established ordering;
- use no private runtime API; the generation example uses public
  `generation_id` and returned loop identity only.

## 5. Verification

Add a parameterized subprocess test that runs every public example with a
finite safety timeout, requires exit code zero, and checks its documented key
output lines. Exact checks are allowed here because the examples demonstrate
framework-owned deterministic structure rather than model-owned semantics.

Acceptance requires:

- every script passes independently under Python 3.10;
- the full test suite, Pyright, and pre-commit hooks pass;
- README links and descriptions match the executable files;
- the notebook executes without warnings;
- `automatic_process_exit.py` completes without destroyed-task, unclosed-loop,
  daemon-thread, or interpreter-shutdown warnings;
- no example recommends a compatibility facade as the default API.

## 6. Scope Boundaries

This work changes examples, example verification, README navigation, and the
quickstart notebook only. It does not change Stage runtime behavior, add public
APIs, alter compatibility policy, or begin Agently integration. If an example
cannot honestly demonstrate a claimed capability, implementation stops and the
runtime gap is reported rather than hidden in example-specific logic.

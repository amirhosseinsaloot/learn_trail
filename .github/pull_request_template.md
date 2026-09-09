<!--
Pull request title equals the ticket title. Fill every heading below
(docs/rebuild/IMPLEMENTATION.md section 4.6); quote command output and exit
codes rather than describing them. Reviewers add: Boundary check,
Architecture check, Security check, Reliability check, Impact check, Verdict.
-->

## Ticket

NU-0nn Title

## Files changed

- path (inside the ticket's Files boundary)

## Commands run

```text
$ make check
exit 0
```

## Results

```text
(pasted tails of test output, including counts)
```

## Acceptance criteria

- criterion: how it was verified

## Limitations

- anything not done or not verified

## Follow-up risks

- what the next ticket should watch

## Handoff

- the information the ticket's Handoff field asks for

## Preflight

```text
(run `make preflight` on the branch head and paste graphify-out/preflight.md:
baseline status, changed and affected nodes, communities, god nodes, conflicts)
```

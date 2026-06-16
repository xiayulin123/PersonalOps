# Operating Systems — Deadlock

Deadlock occurs when four conditions hold simultaneously:

1. **Mutual exclusion** — at least one resource is non-sharable.
2. **Hold and wait** — a process holds resources while waiting for others.
3. **No preemption** — resources cannot be forcibly taken away.
4. **Circular wait** — a cycle exists in the resource allocation graph.

## Prevention strategies

- Break hold-and-wait by requiring processes to request all resources at once.
- Break circular wait by ordering resources and acquiring in order.
- Use the Banker's algorithm for avoidance when resource counts are known.

## Example

If process P1 holds a printer and waits for a scanner, while P2 holds the scanner and waits for the printer, neither can proceed.

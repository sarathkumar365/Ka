---
name: flow-docs
description: Write or update a Ka flow doc in context/flows/. Use whenever a change touches a source file listed under a flow in context/index.md, or when a flow is added or split.
---

# Flow docs

One doc per flow serves the coding agent and the owner (learning, interviews). Update it in the same commit as the code; show the doc diff next to the code diff.

## Template (`context/flows/<flow>.md`)
1. 3-sentence summary the owner could say in an interview.
2. Mermaid diagram.
3. One worked example traced step by step with file and function names; explain each technology inline where used.
4. Failure cases.
5. Link to `<flow>.interview.md` (interview questions live only there).

## Rules
- Explain why, never what. Skip anything the code already makes obvious.
- Add a short "why this way" note only where a real alternative was considered: concept, what was used, alternatives and why they lost.
- About 500 to 700 words. If longer, make a folder: `<flow>/index.md` (short overview, diagram, links) plus sub-docs (details, worked example, failure cases; no pitch or questions). Link each sub-doc at its step with a 1-2 sentence summary.
- Splitting or adding a doc also updates `context/index.md`.
- Never load `*.interview.md` files when writing or reading code.

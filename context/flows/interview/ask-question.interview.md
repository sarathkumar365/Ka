# Interview questions: ask a question

1. Why a hard cap of 10 tool calls, and what happens to the call that hits it?
2. How does the loop survive a model that returns invalid JSON arguments?
3. Why is the system prompt rebuilt each turn instead of stored?
4. What breaks if an assistant message with tool calls has no tool results, and how do you repair it?
5. How would you add streaming without changing `run_turn`? (events callback)
6. Where does prompt injection through tool results get contained, and where can it not be?

# Interview questions: import statement

1. Why parse by word position instead of regex on extracted text? What did the real data show?
2. How do you know an import is correct before writing anything? Name the four checks.
3. Why is the running balance, not the printed column, the source of truth for direction?
4. How do you stop the same statement from being imported twice? What if the process dies halfway?
5. Why is money `Decimal` and not `float`? Give a concrete rounding failure.
6. A returned payment to a loan comes back as money in. How do you avoid counting it as new borrowing?
7. Why keep an interface (`FinanceStore`) with only one implementation today?
8. What stops personal data from reaching the public code repo?

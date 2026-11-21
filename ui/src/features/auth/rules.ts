/** The onboarding steps, account first. SignupPage shows step 1; OnboardingPage shows the rest. */
export const STEPS = ['Account', 'Basics', 'Documents', 'Sources', 'Memory', 'Send']

/** The server's rules, from /api/auth/status, so the form never drifts from them. */
export type Rules = { min_password: number; username_rule: string }

/** Why the form cannot be sent yet, or null. Checked on submit so the button never looks dead. */
export function setupProblem(rules: Rules, username: string, password: string, again: string): string | null {
  if (!username.trim()) return 'Choose a username.'
  if (!new RegExp(rules.username_rule).test(username.trim()))
    return 'The username needs 3 to 32 letters, numbers, - or _, starting with a letter.'
  if (password.length < rules.min_password) return `The password needs ${rules.min_password} characters or more.`
  if (again !== password) return 'The two passwords differ.'
  return null
}

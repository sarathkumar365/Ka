const NAMES: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  openrouter: 'OpenRouter',
  ollama: 'Ollama (on this machine)',
}

export function providerName(id: string | undefined): string {
  if (!id) return 'your model provider'
  return NAMES[id] ?? id
}

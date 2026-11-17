import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// Raw HTML is never enabled (no rehype-raw) and react-markdown's default URL transform drops
// javascript: links, so model or tool output stays inert text.
export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        disallowedElements={['img']} // an image URL would send data to whoever hosts it
        unwrapDisallowed
        components={{
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer noopener">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="tablewrap">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  )
}

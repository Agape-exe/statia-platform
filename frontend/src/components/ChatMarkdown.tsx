import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export function ChatMarkdown({ children }: { children: string }) {
  return (
    <div className="chat-markdown">
      <Markdown
        remarkPlugins={[remarkGfm]}
        skipHtml
        components={{
          table: ({ children }) => (
            <div
              className="table-scroll"
              tabIndex={0}
              role="region"
              aria-label="Tabla del mensaje"
            >
              <table>{children}</table>
            </div>
          ),
          a: ({ href, children }) =>
            href && /^(https?:|mailto:)/i.test(href) ? (
              <a href={href} target="_blank" rel="noopener noreferrer">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            ),
        }}
      >
        {children}
      </Markdown>
    </div>
  )
}

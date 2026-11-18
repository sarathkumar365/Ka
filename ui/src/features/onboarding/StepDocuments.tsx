import { useRef } from 'react'

const ACCEPT = '.pdf,.docx,.odt,.rtf,.html,.htm,.txt,.md'

export function StepDocuments({ files, onChange }: { files: File[]; onChange: (f: File[]) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const pick = (list: FileList | null) => list && onChange([...files, ...Array.from(list)].slice(0, 5))
  return (
    <div className="step">
      <h1>Add your documents</h1>
      <p className="lead">
        A resume or anything that describes your work. Bank statements go through the statement import, not here.
      </p>
      <button
        className="dropzone"
        onClick={() => input.current?.click()}
        onDragOver={(e) => e.preventDefault()}
        onDrop={(e) => {
          e.preventDefault()
          pick(e.dataTransfer.files)
        }}
      >
        Drop files here, or choose them
      </button>
      <input
        ref={input}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          pick(e.target.files)
          e.target.value = '' // so choosing the same file again still fires
        }}
      />
      {files.length === 0 ? (
        <div className="sub">No files yet. You can skip this and add them later.</div>
      ) : (
        <ul className="lines">
          {files.map((f, i) => (
            <li key={`${i}-${f.name}`} className="row" style={{ justifyContent: 'space-between' }}>
              <span>{f.name}</span>
              <button className="linkbtn" onClick={() => onChange(files.filter((_, j) => j !== i))}>
                Remove
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="sub">Nothing is sent yet. You send everything together on the last step.</div>
    </div>
  )
}

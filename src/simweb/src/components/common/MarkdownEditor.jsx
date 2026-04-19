import { useState } from 'react';
import Markdown from 'react-markdown';

export default function MarkdownEditor({ label, value, onChange, disabled, rows = 10 }) {
  const [preview, setPreview] = useState(false);

  return (
    <div className="md-editor">
      <div className="md-editor-header">
        {label && <span className="md-editor-label">{label}</span>}
        <button
          type="button"
          className={`md-tab ${!preview ? 'md-tab-active' : ''}`}
          onClick={() => setPreview(false)}
          disabled={disabled}
        >Éditer</button>
        <button
          type="button"
          className={`md-tab ${preview ? 'md-tab-active' : ''}`}
          onClick={() => setPreview(true)}
          disabled={disabled}
        >Aperçu</button>
      </div>

      {preview
        ? (
          <div className="md-preview">
            {value?.trim()
              ? <Markdown>{value}</Markdown>
              : <p className="md-empty">— vide —</p>}
          </div>
        )
        : (
          <textarea
            rows={rows}
            value={value ?? ''}
            onChange={onChange}
            disabled={disabled}
            className="md-textarea"
            placeholder="Markdown…"
          />
        )
      }
    </div>
  );
}

import { useState, useEffect } from 'react';

export default function JsonEditor({ value, onChange, disabled, rows = 16 }) {
  const [text, setText] = useState('');
  const [parseError, setParseError] = useState(null);

  useEffect(() => {
    setText(value != null ? JSON.stringify(value, null, 2) : '');
    setParseError(null);
  }, [value]);

  const handleChange = (e) => {
    const raw = e.target.value;
    setText(raw);
    try {
      const parsed = JSON.parse(raw);
      setParseError(null);
      onChange(parsed);
    } catch (err) {
      setParseError(err.message);
    }
  };

  const handleFormat = () => {
    try {
      const parsed = JSON.parse(text);
      const formatted = JSON.stringify(parsed, null, 2);
      setText(formatted);
      setParseError(null);
      onChange(parsed);
    } catch (err) {
      setParseError(err.message);
    }
  };

  return (
    <div className="json-editor">
      <div className="json-editor-toolbar">
        <span className="json-editor-label">JSON</span>
        {parseError
          ? <span className="json-editor-error">{parseError}</span>
          : <span className="json-editor-ok">✓ valide</span>
        }
        <button type="button" className="btn-secondary json-editor-fmt"
          onClick={handleFormat} disabled={disabled}>
          Formater
        </button>
      </div>
      <textarea
        rows={rows}
        value={text}
        onChange={handleChange}
        disabled={disabled}
        spellCheck={false}
        className={`json-editor-textarea ${parseError ? 'json-editor-invalid' : ''}`}
        placeholder="{}"
      />
    </div>
  );
}

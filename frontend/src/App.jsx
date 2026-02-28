import { useState } from 'react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export default function App() {
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const askGemini = async () => {
    setLoading(true)
    setError('')
    setResult('')

    try {
      const response = await fetch(`${API_BASE}/api/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt })
      })

      if (!response.ok) {
        const data = await response.json().catch(() => ({}))
        throw new Error(data.detail || 'Request failed')
      }

      const data = await response.json()
      setResult(data.text || '')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main style={{ maxWidth: 760, margin: '3rem auto', fontFamily: 'sans-serif', padding: '0 1rem' }}>
      <h1>Mount Madness</h1>
      <p>FastAPI + React + Gemini starter</p>
      <textarea
        style={{ width: '100%', minHeight: 120 }}
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="Ask Gemini something..."
      />
      <div style={{ marginTop: 12 }}>
        <button onClick={askGemini} disabled={!prompt.trim() || loading}>
          {loading ? 'Sending...' : 'Send'}
        </button>
      </div>
      {error && <p style={{ color: 'crimson' }}>Error: {error}</p>}
      {result && (
        <section>
          <h2>Result</h2>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{result}</pre>
        </section>
      )}
    </main>
  )
}

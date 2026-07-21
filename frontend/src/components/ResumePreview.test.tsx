import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { ResumePreview } from './ResumePreview'

describe('ResumePreview', () => {
  it('renders the name, a section heading, and inline bold', () => {
    render(<ResumePreview md={'# Jane Tan\nAI Engineer\n\n## Skills\n- **PyTorch** and RAG'} />)
    expect(screen.getByText('Jane Tan')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Skills' })).toBeInTheDocument()
    expect(screen.getByText('PyTorch').tagName).toBe('STRONG')
  })

  it('neutralizes a javascript: link href to #', () => {
    render(<ResumePreview md={'[click](javascript:alert(1))'} />)
    const a = screen.getByText('click')
    expect(a.tagName).toBe('A')
    expect(a.getAttribute('href')).toBe('#')
  })

  it('preserves a normal https link href', () => {
    render(<ResumePreview md={'[site](https://example.com)'} />)
    expect(screen.getByText('site').getAttribute('href')).toBe('https://example.com')
  })
})

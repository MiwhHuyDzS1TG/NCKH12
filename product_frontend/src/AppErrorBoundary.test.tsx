import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import AppErrorBoundary from './AppErrorBoundary'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

function BrokenResult(): never {
  throw new Error('private implementation detail')
}

test('unexpected render error becomes a safe recoverable screen', () => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
  render(<AppErrorBoundary><BrokenResult /></AppErrorBoundary>)
  expect(screen.getByRole('heading', { name: 'Something went wrong while opening this result.' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Back to Home' })).toHaveAttribute('href', '/')
  expect(screen.queryByText('private implementation detail')).not.toBeInTheDocument()
})

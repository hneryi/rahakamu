/**
 * Error boundary for generated UI. A malformed widget payload from the model
 * must never take down the whole chat — the widget silently disappears instead
 * (and the error is logged in development).
 */
import { Component, type ReactNode } from 'react';

type Props = { children: ReactNode; fallback?: ReactNode };
type State = { failed: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    if (__DEV__) console.warn('[widget] render failed', error);
  }

  render() {
    return this.state.failed ? (this.props.fallback ?? null) : this.props.children;
  }
}

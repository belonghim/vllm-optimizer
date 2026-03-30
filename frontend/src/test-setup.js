import "@testing-library/jest-dom";
import { server } from './mocks/server';

globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};

if (typeof globalThis.EventSource === 'undefined') {
  class EventSourceMock {
    static CONNECTING = 0;
    static OPEN = 1;
    static CLOSED = 2;

    constructor() {
      this.readyState = EventSourceMock.CONNECTING;
      this.onopen = null;
      this.onmessage = null;
      this.onerror = null;
    }

    close() {
      this.readyState = EventSourceMock.CLOSED;
    }
  }

  globalThis.EventSource = EventSourceMock;
}

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

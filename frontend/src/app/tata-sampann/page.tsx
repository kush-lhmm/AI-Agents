'use client';

import { useState, useRef, useEffect } from 'react';

type UsedResult = {
  sku_id?: string;
  title?: string;
  price_inr?: number;
  weight?: { value?: number; unit?: string };
  link?: string;
  section?: string;
  text?: string;
};

type ChatResp = {
  reply: string;
  used_results: UsedResult[];
  meta: Record<string, unknown>;
};

type Message = {
  role: 'user' | 'assistant';
  text: string;
  timestamp: number;
};

const BACKEND = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000';

export default function TataChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [products, setProducts] = useState<UsedResult[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Focus input on load
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const sendMessage = async () => {
    const msg = input.trim();
    if (!msg || loading) return;

    setError(null);
    setLoading(true);
    setInput('');
    setProducts([]);

    // Add user message with timestamp
    const userMessage: Message = {
      role: 'user',
      text: msg,
      timestamp: Date.now()
    };
    setMessages((prev) => [...prev, userMessage]);

    try {
      const res = await fetch(`${BACKEND}/api/tata/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: msg }),
      });

      if (!res.ok) {
        const text = await res.text().catch(() => 'Request failed');
        throw new Error(text || 'Request failed');
      }

      const data: ChatResp = await res.json();

      // Add assistant message with timestamp
      const assistantMessage: Message = {
        role: 'assistant',
        text: data.reply ?? '',
        timestamp: Date.now()
      };

      setMessages((prev) => [...prev, assistantMessage]);
      setProducts(Array.isArray(data.used_results) ? data.used_results : []);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Request failed';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const formatTimestamp = (timestamp: number) => {
    return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="flex flex-col min-h-screen max-w-4xl mx-auto px-4 py-6 md:py-8 font-sans bg-white">
      <header className="mb-6">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button
              onClick={() => window.location.href = "/"}
              className="flex items-center justify-center p-2 border mr-4 rounded-full hover:bg-gray-100 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
              aria-label="Go back"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-5 w-5 text-gray-600"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z"
                  clipRule="evenodd"
                />
              </svg>
            </button>

            <div className="flex flex-col">
              <h1 className="text-2xl md:text-3xl font-bold text-gray-800">Tata Sampann Product Assistant</h1>
              <p className="text-gray-600 mt-1">Get information about Tata Sampann products</p>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 flex flex-col">
        {/* Chat container */}
        <div className="flex-1 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden flex flex-col">
          {/* Messages area */}
          <div className="flex-1 p-4 overflow-y-auto">
            {messages.length === 0 ? (
              <div className="h-full flex items-center justify-center">
                <div className="text-center p-6 max-w-md">
                  <div className="text-gray-400 mb-2">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-10 w-10 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                    </svg>
                  </div>
                  <h3 className="text-lg font-medium text-gray-700 mb-1">Start a conversation</h3>
                  <p className="text-gray-500 text-sm">Try asking something like "What's the price of moong dal?" or "Show me Tata Sampann spices"</p>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                {messages.map((message, index) => (
                  <div
                    key={index}
                    className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[85%] md:max-w-[75%] rounded-lg p-3 ${message.role === 'user'
                        ? 'bg-blue-600 text-white rounded-br-none'
                        : 'bg-gray-100 text-gray-800 rounded-bl-none'}`}
                    >
                      <div className="whitespace-pre-wrap leading-relaxed">{message.text}</div>
                      <div className={`text-xs mt-1 ${message.role === 'user' ? 'text-blue-100' : 'text-gray-500'}`}>
                        {formatTimestamp(message.timestamp)}
                      </div>
                    </div>
                  </div>
                ))}
                {loading && (
                  <div className="flex justify-start">
                    <div className="bg-gray-100 text-gray-800 rounded-lg rounded-bl-none p-3 max-w-[75%]">
                      <div className="flex space-x-2">
                        <div className="w-2 h-2 rounded-full bg-gray-400 animate-bounce"></div>
                        <div className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                        <div className="w-2 h-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                      </div>
                    </div>
                  </div>
                )}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Input area */}
          <div className="border-t border-gray-200 p-4 bg-gray-50">
            {error && (
              <div className="mb-3 px-4 py-2 bg-red-50 text-red-600 rounded-md text-sm">
                {error}
              </div>
            )}
            <div className="flex gap-2">
              <input
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Type your message..."
                disabled={loading}
                className="flex-1 px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition disabled:bg-gray-100"
              />
              <button
                onClick={sendMessage}
                disabled={loading || !input.trim()}
                className={`px-5 py-3 rounded-lg font-medium transition-colors ${loading || !input.trim()
                  ? 'bg-gray-300 text-gray-500 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700 text-white cursor-pointer'
                  }`}
              >
                {loading ? (
                  <svg className="w-5 h-5 animate-spin" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-8.707l-3-3a1 1 0 00-1.414 1.414L10.586 9H7a1 1 0 100 2h3.586l-1.293 1.293a1 1 0 101.414 1.414l3-3a1 1 0 000-1.414z" clipRule="evenodd" />
                  </svg>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Products section */}
        {products.length > 0 && (
          <div className="mt-6 bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
            <div className="p-4 border-b border-gray-200">
              <h2 className="text-lg font-semibold text-gray-800">Products mentioned</h2>
            </div>
            <div className="grid gap-0 divide-y divide-gray-200">
              {products.map((product, idx) => (
                <div key={`${product.sku_id || idx}`} className="p-4 hover:bg-gray-50 transition-colors">
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
                    <div>
                      <h3 className="font-medium text-gray-900">
                        {product.title || 'Untitled Product'}
                      </h3>
                      <div className="text-sm text-gray-600 mt-1">
                        {typeof product.price_inr === 'number' && (
                          <span className="font-medium text-blue-600">₹{product.price_inr}</span>
                        )}
                        {product.weight?.value && (
                          <span className="ml-2">
                            {product.weight.value} {product.weight.unit || 'g'}
                          </span>
                        )}
                      </div>
                      {product.text && (
                        <p className="text-gray-700 text-sm mt-2 line-clamp-2">
                          {product.text}
                        </p>
                      )}
                    </div>
                    {product.link && (
                      <a
                        href={product.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="mt-2 md:mt-0 inline-flex items-center px-3 py-1.5 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                      >
                        View Product
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
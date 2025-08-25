"use client";

import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";

type Message = {
  id: string;
  text: string;
  sender: "user" | "bot";
};

type ChatResponse = { reply?: string };

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputValue, setInputValue] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL;

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const msg = inputValue.trim();
    if (!msg || isLoading) return;

    const userMessage = {
      id: Date.now().toString(),
      text: msg,
      sender: "user" as const,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputValue("");
    setIsLoading(true);
    setError(null);

    try {
      const res = await fetch(`${backendUrl}/api/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: msg,
          model: "gpt-4.1-nano",
        }),
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(text || `HTTP ${res.status}`);
      }

      const data: ChatResponse = await res.json();

      const botMessage = {
        id: Date.now().toString(),
        text: data.reply ?? "(no reply from server)",
        sender: "bot" as const,
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (err: any) {
      setError(typeof err?.message === "string" ? err.message : "Request failed");

      const errorMessage = {
        id: Date.now().toString(),
        text: "Sorry, I couldn't process that. Please try again.",
        sender: "bot" as const,
      };

      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-50 to-indigo-50 flex flex-col">
      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="sticky top-0 z-10 bg-white/90 backdrop-blur border-b border-gray-200 shadow-sm"
      >
        <div className="max-w-3xl mx-auto px-4 py-4 flex justify-between items-center">
          <Link
            href="/"
            className="flex items-center text-gray-600 hover:text-gray-900 transition-colors group"
          >
            <motion.div
              whileHover={{ x: -3 }}
              className="flex items-center"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                className="h-4 w-4 mr-1 group-hover:text-blue-500 transition-colors"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M9.707 16.707a1 1 0 01-1.414 0l-6-6a1 1 0 010-1.414l6-6a1 1 0 011.414 1.414L5.414 9H17a1 1 0 110 2H5.414l4.293 4.293a1 1 0 010 1.414z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="ml-1 group-hover:text-blue-500 transition-colors">Back</span>
            </motion.div>
          </Link>
          <motion.h1
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="text-xl font-semibold text-gray-800 flex items-center"
          >
            <span>
              🍎
            </span>
            <span className="ml-2">Nutrition Bot</span>
          </motion.h1>
          <div className="w-14"></div>
        </div>
      </motion.header>

      <main className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <AnimatePresence>
            {messages.length === 0 && !isLoading && !error && (
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className="text-center text-gray-500 py-16"
              >
                <motion.div
                  className="mb-4 text-7xl"
                  animate={{
                    rotate: [0, 10, -10, 0],
                    y: [0, -5, 0],
                    scale: [1, 1.1, 1]
                  }}
                  transition={{
                    duration: 4,
                    repeat: Infinity,
                    repeatType: "reverse",
                    ease: "anticipate"
                  }}
                  whileHover={{
                    scale: 1.3,
                    rotate: 360,
                    transition: { duration: 0.8 }
                  }}
                >
                  🍏
                </motion.div>
                <p className="text-lg">Ask me anything about nutrition!</p>
                <p className="text-sm mt-2">I can help with meal plans, food facts, and healthy eating tips.</p>
              </motion.div>
            )}
          </AnimatePresence>

          <div className="space-y-4 mb-6">
            <AnimatePresence>
              {messages.map((m) => (
                <motion.div
                  key={m.id}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3 }}
                  className={`flex ${m.sender === "user" ? "justify-end" : "justify-start"}`}
                >
                  <motion.div
                    whileHover={{ scale: 1.02 }}
                    className={`max-w-[90%] sm:max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed break-words shadow-sm ${m.sender === "user"
                      ? "bg-gradient-to-r from-blue-500 to-blue-600 text-white rounded-br-none"
                      : "bg-white border border-gray-200 text-gray-800 rounded-bl-none"
                      }`}
                  >
                    {m.sender === "bot" ? (
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          p: (props) => <p className="mb-3 last:mb-0" {...props} />,
                          ol: (props) => <ol className="list-decimal pl-5 space-y-1 mb-3" {...props} />,
                          ul: (props) => <ul className="list-disc pl-5 space-y-1 mb-3" {...props} />,
                          li: (props) => <li className="mb-1" {...props} />,
                          strong: (props) => <strong className="font-semibold" {...props} />,
                          a: (props) => (
                            <a className="underline text-blue-600 hover:text-blue-800" target="_blank" rel="noreferrer" {...props} />
                          ),
                          code: (props) => (
                            <code className="bg-gray-100 px-1.5 py-0.5 rounded text-sm font-mono" {...props} />
                          ),
                        }}
                      >
                        {m.text}
                      </ReactMarkdown>
                    ) : (
                      <p className="whitespace-pre-wrap">{m.text}</p>
                    )}
                  </motion.div>
                </motion.div>
              ))}
            </AnimatePresence>

            {isLoading && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="flex justify-start"
              >
                <div className="bg-white border border-gray-200 text-gray-800 rounded-2xl rounded-bl-none px-4 py-3 shadow-sm">
                  <div className="flex items-center gap-1.5">
                    <motion.span
                      animate={{ y: [-2, 2, -2] }}
                      transition={{ repeat: Infinity, duration: 0.8 }}
                      className="w-2.5 h-2.5 rounded-full bg-blue-500"
                    ></motion.span>
                    <motion.span
                      animate={{ y: [-2, 2, -2] }}
                      transition={{ repeat: Infinity, duration: 0.8, delay: 0.2 }}
                      className="w-2.5 h-2.5 rounded-full bg-blue-500"
                    ></motion.span>
                    <motion.span
                      animate={{ y: [-2, 2, -2] }}
                      transition={{ repeat: Infinity, duration: 0.8, delay: 0.4 }}
                      className="w-2.5 h-2.5 rounded-full bg-blue-500"
                    ></motion.span>
                  </div>
                </div>
              </motion.div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </main>

      <div className="sticky bottom-0 pt-10 pb-6">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
          <motion.form
            onSubmit={handleSubmit}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
            className="w-full bg-white border border-gray-300 rounded-xl p-4 shadow-lg"
          >
            <label htmlFor="message" className="sr-only">
              Type your message
            </label>
            <textarea
              id="message"
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask about nutrition, meal plans, or food facts..."
              className="w-full border border-gray-300 text-gray-900 placeholder-gray-400 rounded-lg px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent resize-none"
              rows={2}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSubmit(e);
                }
              }}
            />
            <div className="mt-3 flex items-center justify-between">
              <div className="text-xs text-gray-500">
                {error && (
                  <span className="text-red-500">{error}</span>
                )}
              </div>
              <motion.button
                type="submit"
                disabled={!inputValue.trim() || isLoading}
                whileHover={{ scale: !inputValue.trim() || isLoading ? 1 : 1.03 }}
                whileTap={{ scale: !inputValue.trim() || isLoading ? 1 : 0.97 }}
                className="inline-flex items-center justify-center bg-gradient-to-r from-blue-500 to-blue-600 hover:from-blue-600 hover:to-blue-700 text-white px-5 py-2.5 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-all shadow-md"
              >
                {isLoading ? (
                  <span className="flex items-center">
                    <svg className="animate-spin -ml-1 mr-2 h-4 w-4 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Sending...
                  </span>
                ) : (
                  <span className="flex items-center">
                    Send <svg xmlns="http://www.w3.org/2000/svg" className="ml-1 h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
                      <path fillRule="evenodd" d="M10.293 5.293a1 1 0 011.414 0l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414-1.414L12.586 11H5a1 1 0 110-2h7.586l-2.293-2.293a1 1 0 010-1.414z" clipRule="evenodd" />
                    </svg>
                  </span>
                )}
              </motion.button>
            </div>
          </motion.form>
        </div>
      </div>
      <motion.footer
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.4 }}
        className="py-4 text-center text-sm text-gray-600"
      >
        Made with ❤️ by Kush
      </motion.footer>

    </div>
  );
}
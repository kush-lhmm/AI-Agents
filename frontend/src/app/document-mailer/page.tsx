"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";

type MailResponse = {
  status: "sent";
  mode: "attachment" | "link";
  filename: string;
  size_bytes: number;
  message_id?: string;
  link_expires_seconds?: number;
};

const DocumentMailer = () => {
  const [email, setEmail] = useState("");
  const [requestId, setRequestId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<MailResponse | null>(null);

  const backendUrl =
    process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError("");
    setIsSuccess(false);
    setResult(null);

    try {
      if (!email || !requestId) {
        throw new Error("Please fill all fields");
      }

      const payload =
        requestId.trim().toLowerCase().endsWith(".pdf")
          ? { to: email.trim(), filename: requestId.trim() }
          : { to: email.trim(), code: requestId.trim() };

      const res = await fetch(`${backendUrl}/api/mail/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = (await res.json()) as MailResponse | { detail?: any };

      if (!res.ok) {

        const msg =
          typeof (data as any).detail === "string"
            ? (data as any).detail
            : JSON.stringify((data as any).detail || data);
        throw new Error(msg);
      }

      setResult(data as MailResponse);
      setIsSuccess(true);
    } catch (err: any) {
      setError(err?.message || "Request failed");
    } finally {
      setIsSubmitting(false);
    }
  };

  const resetForm = () => {
    setEmail("");
    setRequestId("");
    setIsSuccess(false);
    setError("");
    setResult(null);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-100 to-gray-200">
      <header className="sticky top-0 z-10 bg-white/80 backdrop-blur border-b border-gray-300">
        <div className="max-w-3xl mx-auto px-4 py-5 flex justify-between items-center">
          <Link
            href="/"
            className="flex items-center text-gray-600 hover:text-gray-900 transition-colors group"
          >
            <motion.div whileHover={{ x: -3 }} className="flex items-center">
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
              <span className="ml-1 group-hover:text-blue-500 transition-colors">
                Back
              </span>
            </motion.div>
          </Link>
          <motion.h1
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="text-xl font-semibold text-gray-800 flex items-center"
          >
            <span>📧</span>
            <span className="ml-2">Document Mailer</span>
          </motion.h1>
          <div className="w-14"></div>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="bg-white p-6 rounded-xl shadow-md border border-gray-300"
        >
          <AnimatePresence mode="wait">
            {!isSuccess ? (
              <motion.div
                key="form"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="space-y-6"
              >
                <div>
                  <h2 className="text-xl font-semibold text-gray-800 mb-2">
                    Request Documents
                  </h2>
                  <p className="text-gray-600">
                    Enter your email and a request code or filename.
                  </p>
                  <p className="text-xs text-gray-500 mt-1">
                    Codes: itc-food-policy, itc-2019, itc-2024-report, itc-sera,
                    itc-results-2024
                  </p>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label
                      htmlFor="email"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      Email Address
                    </label>
                    <input
                      type="email"
                      id="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 text-black rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder="your@email.com"
                      required
                    />
                  </div>

                  <div>
                    <label
                      htmlFor="requestId"
                      className="block text-sm font-medium text-gray-700 mb-1"
                    >
                      Request ID (code or filename)
                    </label>
                    <input
                      type="text"
                      id="requestId"
                      value={requestId}
                      onChange={(e) => setRequestId(e.target.value)}
                      className="w-full px-4 py-2 border border-gray-300 text-black rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                      placeholder="e.g. itc-food-policy OR itc-integrated-report-2019.pdf"
                      required
                    />
                  </div>

                  {error && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      className="text-sm text-red-600 bg-red-50 p-3 rounded-lg"
                    >
                      {error}
                    </motion.div>
                  )}

                  <motion.button
                    type="submit"
                    disabled={isSubmitting}
                    whileHover={!isSubmitting ? { scale: 1.02 } : {}}
                    whileTap={!isSubmitting ? { scale: 0.98 } : {}}
                    className={`w-full py-3 px-4 rounded-lg font-medium text-white ${isSubmitting
                        ? "bg-blue-400"
                        : "bg-blue-500 hover:bg-blue-600"
                      } transition-colors`}
                  >
                    {isSubmitting ? (
                      <span className="flex items-center justify-center">
                        <motion.span
                          animate={{ rotate: 360 }}
                          transition={{
                            repeat: Infinity,
                            duration: 1,
                            ease: "linear",
                          }}
                          className="inline-block h-5 w-5 mr-2 border-2 border-white border-t-transparent rounded-full"
                        />
                        Processing...
                      </span>
                    ) : (
                      "Request Documents"
                    )}
                  </motion.button>
                </form>
              </motion.div>
            ) : (
              <motion.div
                key="success"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="text-center py-8"
              >
                <motion.div
                  animate={{ scale: [1, 1.1, 1], rotate: [0, 5, -5, 0] }}
                  transition={{ duration: 0.8 }}
                  className="text-6xl mb-4"
                >
                  🎉
                </motion.div>
                <h2 className="text-2xl font-semibold text-gray-800 mb-2">
                  Documents Sent!
                </h2>
                <p className="text-gray-600 mb-2">
                  We emailed <span className="font-medium">{email}</span>.
                </p>
                {result && (
                  <p className="text-gray-600 mb-6 text-sm">
                    Mode: <b>{result.mode}</b> • File:{" "}
                    <b>{result.filename}</b>
                  </p>
                )}
                <motion.button
                  onClick={resetForm}
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="px-6 py-2 bg-indigo-500 text-white rounded-lg font-medium hover:bg-indigo-600 transition-colors"
                >
                  Make Another Request
                </motion.button>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="mt-8 bg-white p-6 rounded-xl shadow-md border border-gray-300"
        >
          <h2 className="text-lg font-semibold text-gray-800 mb-3">
            How it works
          </h2>
          <ul className="space-y-3">
            <motion.li
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.4 }}
              className="flex items-start"
            >
              <span className="bg-blue-100 text-blue-600 rounded-full py-1 px-3 mr-3">
                1
              </span>
              <span className="text-gray-700">
                Enter your email and request code/filename
              </span>
            </motion.li>
            <motion.li
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.5 }}
              className="flex items-start"
            >
              <span className="bg-blue-100 text-blue-600 rounded-full py-1 px-3 p-1 mr-3">
                2
              </span>
              <span className="text-gray-700">
                We'll send you attachment or secure link
              </span>
            </motion.li>
          </ul>
        </motion.div>
      </main>
    </div>
  );
};

export default DocumentMailer;